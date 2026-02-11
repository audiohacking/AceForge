"""
Generation API for new UI. Maps ace-step-ui GenerationParams to generate_track_ace();
job queue stored under get_user_data_dir(). No auth. Real implementation (no mocks).
"""

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file

def _uppercase_track_in_instruction(instruction):
    """Uppercase TRACK_NAME in 'Generate the X track ...' to match ACE-Step (cli.py _default_instruction_for_task)."""
    if not instruction or " track " not in instruction:
        return instruction
    m = re.search(r"(\bthe\s+)(\w+)(\s+track\b)", instruction, re.IGNORECASE)
    if m:
        return instruction[: m.start(2)] + m.group(2).upper() + instruction[m.end(2) :]
    return instruction

from cdmf_paths import get_output_dir, get_user_data_dir, get_models_folder, load_config
from cdmf_tracks import get_audio_duration, list_lora_adapters, load_track_meta, save_track_meta
from cdmf_generation_job import GenerationCancelled
import cdmf_state
from generate_ace import register_job_progress_callback, _resolve_lm_checkpoint_path

bp = Blueprint("api_generate", __name__)

# In-memory job store (key: jobId, value: { status, params, result?, error?, startTime, queuePosition? })
_jobs: dict = {}
_jobs_lock = threading.Lock()
# Queue order for queuePosition
_job_order: list = []
# One worker at a time (must use 'global _generation_busy' in any function that assigns to it)
_generation_busy = False
# Current running job id (for cancel); set by worker, read by cancel endpoint
_current_job_id: str | None = None
# Job ids for which cancel was requested (cooperative stop)
_cancel_requested: set = set()


def reset_generation_queue() -> None:
    """Clear the in-memory job queue and worker state. Call on app startup so each restart starts with an empty queue."""
    global _generation_busy, _current_job_id
    with _jobs_lock:
        _jobs.clear()
        _job_order.clear()
        _cancel_requested.clear()
        _generation_busy = False
        _current_job_id = None
    logging.info("[API generate] Generation queue reset (empty on startup).")


def _is_cancel_requested(job_id: str) -> bool:
    with _jobs_lock:
        return job_id in _cancel_requested


def _refs_dir() -> Path:
    d = get_user_data_dir() / "references"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _jobs_path() -> Path:
    return get_user_data_dir() / "generation_jobs.json"


def _resolve_audio_url_to_path(url: str) -> str | None:
    """Convert /audio/filename or /audio/refs/filename (or full URL) to absolute path."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    # Allow full-origin URLs from the UI (e.g. http://127.0.0.1:5056/audio/refs/xxx)
    if "://" in url and "/audio/" in url:
        url = "/audio/" + url.split("/audio/", 1)[-1]
    if url.startswith("/audio/refs/"):
        name = url.replace("/audio/refs/", "", 1).split("?")[0]
        path = _refs_dir() / name
        return str(path) if path.is_file() else None
    if url.startswith("/audio/"):
        name = url.replace("/audio/", "", 1).split("?")[0]
        path = Path(get_output_dir()) / name
        return str(path) if path.is_file() else None
    return None


def _on_job_progress(
    fraction: float,
    stage: str,
    steps_current: int | None,
    steps_total: int | None,
    eta_seconds: float | None,
) -> None:
    """Update current job's progress (called from generate_ace tqdm wrapper). Uses thread-local job id so parallel workers update the correct job."""
    with _jobs_lock:
        jid = cdmf_state.get_current_generation_job_id()
        if jid is None:
            return
        job = _jobs.get(jid)
        if not job:
            return
        job["progressPercent"] = round(fraction * 100.0, 1)
        if steps_total is not None:
            job["progressSteps"] = f"{steps_current or 0}/{steps_total}"
        if eta_seconds is not None:
            job["progressEta"] = round(eta_seconds, 1)
        job["progressStage"] = stage or ""


# Register so generate_ace's tqdm wrapper reports progress into the current job
register_job_progress_callback(_on_job_progress)


def _run_generation(job_id: str) -> None:
    """Background: run generate_track_ace and update job."""
    global _generation_busy, _current_job_id
    try:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job or job.get("status") != "queued":
                return
            job["status"] = "running"
            job["progressPercent"] = 0.0
            job["progressSteps"] = None
            job["progressEta"] = None
            job["progressStage"] = ""
            _current_job_id = job_id

        cdmf_state.set_current_generation_job_id(job_id)
        cancel_check = lambda: _is_cancel_requested(job_id)
        from generate_ace import generate_track_ace

        params = job.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        # Map to ACE-Step params: task_type, reference_audio, src_audio, audio_cover_strength (Tutorial/INFERENCE.md)
        custom_mode = bool(params.get("customMode", False))
        task = (params.get("task_type") or params.get("taskType") or "text2music").strip().lower()
        allowed_tasks = ("text2music", "retake", "repaint", "extend", "cover", "audio2audio", "lego", "extract", "complete")
        if task not in allowed_tasks:
            task = "text2music"
        # Single style/caption field drives all text conditioning (ACE-Step caption).
        # Simple mode: songDescription. Advanced mode: style. Lego/extract/complete: instruction + caption only (no metas; source sets context).
        if task in ("lego", "extract", "complete"):
            instruction = (params.get("instruction") or "").strip()
            caption = (params.get("style") or "").strip()
            if not instruction and not caption:
                instruction = "Generate an instrument track based on the audio context:"
            prompt = None  # built below after we have duration/bpm/metas
        else:
            instruction = None
            caption = None
            prompt = (params.get("style") or "").strip() if custom_mode else (params.get("songDescription") or "").strip()
        key_scale = (params.get("keyScale") or "").strip()
        time_sig = (params.get("timeSignature") or "").strip()
        vocal_lang = (params.get("vocalLanguage") or "").strip().lower()
        extra_bits = []
        if task != "lego":
            if key_scale:
                extra_bits.append(f"key {key_scale}")
            if time_sig:
                extra_bits.append(f"time signature {time_sig}")
            if vocal_lang and vocal_lang not in ("unknown", ""):
                extra_bits.append(f"vocal language {vocal_lang}")
            if extra_bits:
                prompt = f"{prompt}, {', '.join(extra_bits)}" if prompt else ", ".join(extra_bits)
        # When user explicitly chose English, reinforce in caption so model conditions on it (skip for lego)
        if task != "lego" and vocal_lang == "en" and prompt:
            if not prompt.lower().startswith("english"):
                prompt = f"English vocals, {prompt}"
        if not prompt:
            # For cover/audio2audio, default encourages transformation while keeping structure; otherwise generic instrumental
            if task in ("cover", "audio2audio", "retake"):
                prompt = "transform style while preserving structure, re-interpret with new character"
            else:
                prompt = "instrumental background music"
        lyrics = (params.get("lyrics") or "").strip()
        instrumental = bool(params.get("instrumental", True))
        negative_prompt_str = (params.get("negativePrompt") or params.get("negative_prompt") or "").strip()
        try:
            d = params.get("duration")
            # Keep <=0 as "Auto" and pass through to the model path.
            duration = float(d if d is not None else -1)
        except (TypeError, ValueError):
            duration = -1
        # Guide: 65 steps + CFG 4.0 for best quality; low CFG reduces artifacts (see community guide).
        try:
            steps = int(params.get("inferenceSteps") or 65)
        except (TypeError, ValueError):
            steps = 65
        steps = max(1, min(100, steps))
        try:
            guidance_scale = float(params.get("guidanceScale") or 4.0)
        except (TypeError, ValueError):
            guidance_scale = 4.0
        # Base/SFT models benefit from higher guidance (docs: 5.0-9.0 typical)
        _dit = (load_config() or {}).get("ace_step_dit_model") or "turbo"
        if _dit in ("base", "sft") and guidance_scale < 5.0:
            guidance_scale = 5.0
        try:
            seed = int(params.get("seed") or 0)
        except (TypeError, ValueError):
            seed = 0
        random_seed = params.get("randomSeed", True)
        if random_seed:
            import random
            seed = random.randint(0, 2**31 - 1)
        bpm = params.get("bpm")
        if bpm is not None:
            try:
                bpm = float(bpm)
                if bpm <= 0:
                    bpm = None
            except (TypeError, ValueError):
                bpm = None
        # Lego/extract/complete: instruction (uppercase track) + caption appended with comma.
        # No metas — BPM/key/timesignature should match the input backing.
        if task in ("lego", "extract", "complete"):
            instruction = _uppercase_track_in_instruction(
                instruction or "Generate an instrument track based on the audio context:"
            )
            prompt = (instruction.rstrip(":").strip() + ", " + (caption or "").strip()).strip() if (instruction or caption) else instruction
            if not prompt:
                prompt = instruction or "Generate an instrument track based on the audio context"
        title = (params.get("title") or "Untitled").strip() or "Track"
        # reference_audio / src_audio per ACE-Step (paths or our URLs from library)
        reference_audio_url = (params.get("reference_audio") or params.get("referenceAudioUrl") or params.get("reference_audio_path") or "").strip()
        source_audio_url = (params.get("src_audio") or params.get("sourceAudioUrl") or params.get("source_audio_path") or "").strip()
        # Cover with two audios: source = structure/duration, reference = style (blend mode)
        cover_blend = task == "cover" and source_audio_url and reference_audio_url
        if cover_blend:
            source_path = _resolve_audio_url_to_path(source_audio_url)
            style_path = _resolve_audio_url_to_path(reference_audio_url)
            if not source_path or not style_path:
                raise ValueError("Cover blend requires both source and style audio to be resolvable (Library or Upload).")
            src_audio_path = style_path  # ref for conditioning = style
            cover_duration_path = source_path  # duration from source
        else:
            cover_duration_path = None
            # For cover/retake/lego use source-first (backing/song to cover); for style/reference use reference-first
            if task in ("cover", "retake", "lego"):
                resolved = _resolve_audio_url_to_path(source_audio_url) if source_audio_url else None
                src_audio_path = resolved or (_resolve_audio_url_to_path(reference_audio_url) if reference_audio_url else None)
            else:
                resolved = _resolve_audio_url_to_path(reference_audio_url) if reference_audio_url else None
                src_audio_path = resolved or (_resolve_audio_url_to_path(source_audio_url) if source_audio_url else None)

        # Cover: when duration not set (<=0), use source file length
        if task == "cover" and duration <= 0:
            path_for_duration = cover_duration_path if cover_blend else src_audio_path
            if path_for_duration:
                file_sec = get_audio_duration(Path(path_for_duration))
                if file_sec > 0:
                    duration = file_sec
        if duration <= 0:
            duration = 60
        duration = max(15, min(240, duration))

        # When reference/source audio is provided, enable Audio2Audio so ACE-Step uses it (cover/retake/repaint/lego).
        # Defaults aligned with ACE-Step-MCP (ref_audio_strength 0.5) and cover/retake UX (strong source → 0.8).
        # Lego/extract/complete: low ref_audio_strength so output follows prompt (new instrument), not copy of backing.
        # See docs/ACE-Step-INFERENCE.md: audio_cover_strength 1.0 = strong adherence; lower = more prompt influence.
        audio2audio_enable = bool(src_audio_path)
        ref_default = 0.8 if task in ("cover", "retake") else (0.5 if task == "audio2audio" else 0.7)
        if task in ("lego", "extract", "complete"):
            ref_default = 0.25  # low strength so output follows prompt (instrument) while matching backing timing
        # audio_cover_strength per ACE-Step; lego/cover blend use specific overrides when set
        ref_audio_strength = params.get("legoBackingInfluence") if task in ("lego", "extract", "complete") else None
        if ref_audio_strength is None and cover_blend:
            ref_audio_strength = params.get("coverBlendFactor") if params.get("coverBlendFactor") is not None else 0.5
        if ref_audio_strength is None:
            ref_audio_strength = (
                params.get("audio_cover_strength")
                or params.get("audioCoverStrength")
                or params.get("ref_audio_strength")
                or ref_default
            )
        ref_audio_strength = float(ref_audio_strength)
        ref_audio_strength = max(0.0, min(1.0, ref_audio_strength))

        # Repaint segment (for task=repaint); -1 means end of audio (converted to duration in generate_track_ace).
        try:
            repaint_start = float(params.get("repaintingStart") or params.get("repaint_start") or 0)
        except (TypeError, ValueError):
            repaint_start = 0.0
        try:
            repaint_end = float(params.get("repaintingEnd") or params.get("repaint_end") or -1)
        except (TypeError, ValueError):
            repaint_end = -1.0
        # -1 means "end of audio"; generate_track_ace converts to target duration

        # Retake/repaint variance (ACE-Step-MCP default 0.2)
        try:
            retake_variance = float(params.get("retake_variance") or params.get("retakeVariance") or 0.2)
        except (TypeError, ValueError):
            retake_variance = 0.2
        retake_variance = max(0.0, min(1.0, retake_variance))

        # LoRA adapter (optional): path or folder name under custom_lora
        lora_name_or_path = (params.get("loraNameOrPath") or params.get("lora_name_or_path") or "").strip()
        try:
            lora_weight = float(params.get("loraWeight") or params.get("lora_weight") or 0.75)
        except (TypeError, ValueError):
            lora_weight = 0.75
        lora_weight = max(0.0, min(2.0, lora_weight))

        # Thinking / LM / CoT (passed through so pipeline or future LM path can use them)
        thinking = bool(params.get("thinking", False))
        use_cot_metas = bool(params.get("useCotMetas", True))
        use_cot_caption = bool(params.get("useCotCaption", True))
        # Lego/extract/complete: instruction must stay verbatim ("Generate the X track based on the audio context:").
        # LM refinement would rephrase and can drop the track-type instruction, so disable CoT caption for these tasks.
        if task in ("lego", "extract", "complete"):
            use_cot_caption = False
        use_cot_language = bool(params.get("useCotLanguage", True))
        try:
            lm_temperature = float(params.get("lmTemperature") or params.get("lm_temperature") or 0.85)
        except (TypeError, ValueError):
            lm_temperature = 0.85
        lm_temperature = max(0.0, min(2.0, lm_temperature))
        try:
            lm_cfg_scale = float(params.get("lmCfgScale") or params.get("lm_cfg_scale") or 2.0)
        except (TypeError, ValueError):
            lm_cfg_scale = 2.0
        try:
            lm_top_k = int(params.get("lmTopK") or params.get("lm_top_k") or 0)
        except (TypeError, ValueError):
            lm_top_k = 0
        try:
            lm_top_p = float(params.get("lmTopP") or params.get("lm_top_p") or 0.9)
        except (TypeError, ValueError):
            lm_top_p = 0.9
        lm_negative_prompt = (params.get("lmNegativePrompt") or params.get("lm_negative_prompt") or "NO USER INPUT").strip()

        # Log model tag for quality tracking (from job or config)
        with _jobs_lock:
            j = _jobs.get(job_id)
            dit_tag = (j.get("dit_model") or "turbo") if j else "turbo"
            lm_tag = (j.get("lm_model") or "1.7B") if j else "1.7B"
        logging.info("[API generate] Using dit=%s, lm=%s", dit_tag, lm_tag)
        if src_audio_path:
            logging.info(
                "[API generate] Using reference audio: %s (task=%s, audio2audio=%s%s)",
                src_audio_path, task, audio2audio_enable,
                ", cover_blend=True" if cover_blend else "",
            )
        else:
            logging.info("[API generate] No reference audio; text2music only")

        out_dir_str = params.get("outputDir") or params.get("output_dir") or get_output_dir()
        out_dir = Path(out_dir_str)
        out_dir.mkdir(parents=True, exist_ok=True)

        # ACE-Step params aligned with docs/ACE-Step-INFERENCE.md:
        # caption/style, lyrics, src_audio (→ ref_audio_input for cover/retake), audio_cover_strength,
        # task, repainting_*; guidance_scale 7.0 when using reference improves adherence.
        summary = generate_track_ace(
            genre_prompt=prompt,
            lyrics=lyrics,
            instrumental=instrumental,
            negative_prompt=negative_prompt_str or "",
            target_seconds=duration,
            fade_in_seconds=0.5,
            fade_out_seconds=0.5,
            seed=seed,
            out_dir=out_dir,
            basename=title[:200],
            steps=steps,
            guidance_scale=guidance_scale,
            bpm=bpm,
            src_audio_path=src_audio_path,
            task=task,
            audio2audio_enable=audio2audio_enable,
            ref_audio_strength=ref_audio_strength,
            repaint_start=repaint_start,
            repaint_end=repaint_end,
            retake_variance=retake_variance,
            vocal_gain_db=0.0,
            instrumental_gain_db=0.0,
            lora_name_or_path=lora_name_or_path or None,
            lora_weight=lora_weight,
            cancel_check=cancel_check,
            vocal_language=vocal_lang or "",
            thinking=thinking,
            use_cot_metas=use_cot_metas,
            use_cot_caption=use_cot_caption,
            use_cot_language=use_cot_language,
            lm_temperature=lm_temperature,
            lm_cfg_scale=lm_cfg_scale,
            lm_top_k=lm_top_k,
            lm_top_p=lm_top_p,
            lm_negative_prompt=lm_negative_prompt,
        )

        wav_path = summary.get("wav_path")
        if isinstance(wav_path, Path):
            path = wav_path
        else:
            path = Path(str(wav_path))
        filename = path.name
        audio_url = f"/audio/{filename}"
        actual_seconds = float(summary.get("actual_seconds") or (duration if duration > 0 else 0))

        # Save title, lyrics, style to track metadata so they appear in the library (input params only; model does not return lyrics)
        try:
            meta = load_track_meta()
            job_title = (params.get("title") or "Untitled").strip() or "Track"
            job_lyrics = (params.get("lyrics") or "").strip()
            job_style = (params.get("style") or params.get("songDescription") or "").strip()
            entry = meta.get(filename, {})
            entry["title"] = job_title[:500]
            entry["lyrics"] = job_lyrics[:10000]
            entry["style"] = job_style[:500] if job_style else job_title[:500]
            entry["caption"] = entry["style"]
            entry["seconds"] = actual_seconds
            entry["created"] = time.time()
            if bpm is not None:
                entry["bpm"] = bpm
            if params.get("keyScale"):
                entry["key_scale"] = str(params.get("keyScale"))[:100]
            if params.get("timeSignature"):
                entry["time_signature"] = str(params.get("timeSignature"))[:50]
            meta[filename] = entry
            save_track_meta(meta)
        except Exception as meta_err:
            logging.warning("[API generate] Failed to save track metadata: %s", meta_err)

        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["status"] = "succeeded"
                job["result"] = {
                    "audioUrls": [audio_url],
                    "duration": int(actual_seconds),
                    "bpm": bpm,
                    "keyScale": params.get("keyScale"),
                    "timeSignature": params.get("timeSignature"),
                    "status": "succeeded",
                }
    except GenerationCancelled:
        logging.info("Generation job %s cancelled by user", job_id)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["status"] = "cancelled"
                job["error"] = "Cancelled by user"
    except Exception as e:
        logging.exception("Generation job %s failed", job_id)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["status"] = "failed"
                job["error"] = str(e)
    finally:
        cdmf_state.set_current_generation_job_id(None)
        _generation_busy = False
        with _jobs_lock:
            _current_job_id = None
            _cancel_requested.discard(job_id)
        # Start next queued job (skips cancelled: they are no longer "queued")
        with _jobs_lock:
            for jid in _job_order:
                j = _jobs.get(jid)
                if j and j.get("status") == "queued":
                    threading.Thread(target=_run_generation, args=(jid,), daemon=True).start()
                    break


@bp.route("/lora_adapters", methods=["GET"])
def get_lora_adapters():
    """GET /api/generate/lora_adapters — list LoRA adapters (e.g. from Training or custom_lora)."""
    try:
        adapters = list_lora_adapters()
        return jsonify({"adapters": adapters})
    except Exception as e:
        logging.exception("[API generate] list_lora_adapters failed: %s", e)
        return jsonify({"adapters": []})


@bp.route("", methods=["POST"], strict_slashes=False)
@bp.route("/", methods=["POST"], strict_slashes=False)
def create_job():
    """POST /api/generate or /api/generate/ — enqueue generation job. Returns jobId, status, queuePosition."""
    global _generation_busy
    try:
        logging.info("[API generate] POST /api/generate received")
        raw = request.get_json(silent=True)
        # Ensure we always have a dict (get_json can return list or None; UI sends object)
        data = raw if isinstance(raw, dict) else {}
        logging.info("[API generate] Request body keys: %s", list(data.keys()) if data else [])

        def _str(v):
            return (v or "").strip() if isinstance(v, str) else ""

        task_raw = data.get("task_type") or data.get("taskType")
        task_for_validation = _str(task_raw).lower() if task_raw else "text2music"
        base_only_tasks = ("lego", "extract", "complete")
        audio_tasks = ("cover", "retake", "audio2audio", "repaint", "extend")

        # Only require songDescription for true "simple" mode: no customMode, no task context, no source/ref/style/prompt
        has_src = bool(_str(data.get("src_audio") or data.get("sourceAudioUrl") or data.get("source_audio_path")))
        has_ref = bool(_str(data.get("reference_audio") or data.get("referenceAudioUrl") or data.get("reference_audio_path")))
        has_style = bool(_str(data.get("style") or data.get("prompt")))
        has_song_desc = bool(_str(data.get("songDescription")))
        is_simple_mode = not data.get("customMode") and not has_song_desc
        # Allow without song description: custom mode, or any audio task, or has source/ref + style, or has style/prompt alone
        allow_without_song_desc = (
            data.get("customMode")
            or task_for_validation in audio_tasks
            or (has_src and has_style)
            or (has_ref and has_style)
            or has_src
            or has_ref
            or has_style
        )
        if is_simple_mode and not allow_without_song_desc:
            return jsonify({"error": "Song description required for simple mode"}), 400

        if task_for_validation in base_only_tasks:
            src_audio = _str(data.get("src_audio") or data.get("sourceAudioUrl") or data.get("source_audio_path"))
            instruction = _str(data.get("instruction"))
            style = _str(data.get("style"))
            if not src_audio:
                return jsonify({"error": "Backing/source audio required for Lego (and extract/complete)"}), 400
            if not instruction and not style:
                return jsonify({"error": "Describe the track (caption) or instruction required for Lego"}), 400
        elif task_for_validation in audio_tasks:
            src_audio = _str(data.get("src_audio") or data.get("sourceAudioUrl") or data.get("source_audio_path"))
            ref_audio = _str(data.get("reference_audio") or data.get("referenceAudioUrl") or data.get("reference_audio_path"))
            if not src_audio and not ref_audio:
                return jsonify({"error": "Source or reference audio required for Cover (and retake/audio2audio/repaint/extend)"}), 400
            style = _str(data.get("style") or data.get("prompt"))
            if task_for_validation == "cover" and not style:
                return jsonify({"error": "Cover style description required (e.g. jazz piano cover with swing rhythm)"}), 400
        # Custom mode: require at least one of style, lyrics, reference audio, or source audio
        if data.get("customMode"):
            style = (data.get("style") or "").strip()
            lyrics = (data.get("lyrics") or "").strip()
            ref_audio = (data.get("reference_audio") or data.get("referenceAudioUrl") or data.get("reference_audio_path") or "").strip()
            src_audio = (data.get("src_audio") or data.get("sourceAudioUrl") or data.get("source_audio_path") or "").strip()
            if not style and not lyrics and not ref_audio and not src_audio:
                return jsonify({"error": "Style, lyrics, or reference/source audio required for custom mode"}), 400

        job_id = str(uuid.uuid4())
        # Store a copy so we don't keep a reference to the request body
        try:
            params_copy = dict(data)
        except (TypeError, ValueError):
            params_copy = {}
        config = load_config()
        dit_tag = config.get("ace_step_dit_model") or params_copy.get("aceStepDitModel") or "turbo"
        lm_tag = config.get("ace_step_lm") or params_copy.get("aceStepLm") or "1.7B"
        with _jobs_lock:
            _jobs[job_id] = {
                "status": "queued",
                "params": params_copy,
                "result": None,
                "error": None,
                "startTime": time.time(),
                "queuePosition": len(_job_order) + 1,
                "progressPercent": None,
                "progressSteps": None,
                "progressEta": None,
                "progressStage": None,
                "dit_model": dit_tag,
                "lm_model": lm_tag,
            }
            _job_order.append(job_id)
            pos = _jobs[job_id]["queuePosition"]

        if not _generation_busy:
            _generation_busy = True
            threading.Thread(target=_run_generation, args=(job_id,), daemon=True).start()

        logging.info("[API generate] Job %s (dit=%s, lm=%s) queued at position %s", job_id, dit_tag, lm_tag, pos)
        return jsonify({
            "jobId": job_id,
            "status": "queued",
            "queuePosition": pos,
        })
    except Exception as e:
        logging.exception("[API generate] create_job failed: %s", e)
        raise


@bp.route("/status/<job_id>", methods=["GET"])
def get_status(job_id: str):
    """GET /api/generate/status/:jobId — return job status and result when done."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    status = job.get("status", "unknown")
    progress_eta = job.get("progressEta")
    out = {
        "jobId": job_id,
        "status": status,
        "queuePosition": job.get("queuePosition"),
        "etaSeconds": int(progress_eta) if progress_eta is not None else None,
        "progressPercent": job.get("progressPercent"),
        "progressSteps": job.get("progressSteps"),
        "progressStage": job.get("progressStage"),
        "result": job.get("result"),
        "error": job.get("error"),
    }
    return jsonify(out)


@bp.route("/unstick", methods=["POST"])
def unstick_queue():
    """POST /api/generate/unstick — clear stuck worker state and start the next queued job (if any)."""
    global _generation_busy
    started = None
    with _jobs_lock:
        _generation_busy = False
        for jid in _job_order:
            j = _jobs.get(jid)
            if j and j.get("status") == "queued":
                _generation_busy = True
                threading.Thread(target=_run_generation, args=(jid,), daemon=True).start()
                started = jid
                break
    return jsonify({
        "ok": True,
        "message": "Queue unstick: worker cleared." + (" Next queued job started." if started else " No queued jobs."),
        "startedJobId": started,
    })


@bp.route("/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id: str):
    """POST /api/generate/cancel/:jobId — cancel a queued or running generation job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        status = job.get("status", "unknown")
        if status == "queued":
            job["status"] = "cancelled"
            job["error"] = "Cancelled by user"
            return jsonify({"cancelled": True, "jobId": job_id, "message": "Job removed from queue."})
        if status == "running":
            _cancel_requested.add(job_id)
            return jsonify({"cancelled": True, "jobId": job_id, "message": "Cancel requested; generation will stop after the current step."})
        # already succeeded, failed, or cancelled
        return jsonify({"cancelled": False, "jobId": job_id, "message": f"Job already {status}."})


def _reference_tracks_meta_path() -> Path:
    """Path to reference_tracks.json (shared with api.reference_tracks)."""
    return get_user_data_dir() / "reference_tracks.json"


def _append_to_reference_library(ref_id: str, filename: str, audio_url: str, file_path: Path) -> None:
    """Add an entry to reference_tracks.json so the file appears in 'From library' and in the main player."""
    meta_path = _reference_tracks_meta_path()
    records = []
    if meta_path.is_file():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            records = data if isinstance(data, list) else []
        except Exception:
            pass
    records.append({
        "id": ref_id,
        "filename": filename,
        "storage_key": filename,
        "audio_url": audio_url,
        "duration": None,
        "file_size_bytes": file_path.stat().st_size if file_path.is_file() else None,
        "tags": ["uploaded"],
    })
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


@bp.route("/upload-audio", methods=["POST"])
def upload_audio():
    """POST /api/generate/upload-audio — multipart file; save to references dir and add to library."""
    if "audio" not in request.files:
        return jsonify({"error": "Audio file is required"}), 400
    f = request.files["audio"]
    if not f.filename:
        return jsonify({"error": "No filename"}), 400
    ext = Path(f.filename).suffix.lower() or ".audio"
    ref_id = str(uuid.uuid4())
    name = f"{ref_id}{ext}"
    path = _refs_dir() / name
    f.save(str(path))
    url = f"/audio/refs/{name}"
    _append_to_reference_library(ref_id, name, url, path)
    return jsonify({"url": url, "key": name})


@bp.route("/audio", methods=["GET"])
def get_audio():
    """GET /api/generate/audio?path=... — serve file from output or references."""
    path_arg = request.args.get("path")
    if not path_arg:
        return jsonify({"error": "Path required"}), 400
    path_arg = path_arg.strip()
    if ".." in path_arg or path_arg.startswith("/"):
        path_arg = path_arg.lstrip("/")
    if path_arg.startswith("refs/"):
        local = _refs_dir() / path_arg.replace("refs/", "", 1)
    else:
        local = Path(get_output_dir()) / path_arg
    if not local.is_file():
        return jsonify({"error": "File not found"}), 404
    return send_file(local, as_attachment=False, download_name=local.name)


@bp.route("/history", methods=["GET"])
def get_history():
    """GET /api/generate/history — last 50 jobs."""
    with _jobs_lock:
        order = _job_order[-50:]
        order.reverse()
        jobs = [{"id": jid, **_jobs.get(jid, {})} for jid in order if jid in _jobs]
    return jsonify({"jobs": jobs})


@bp.route("/endpoints", methods=["GET"])
def get_endpoints():
    """GET /api/generate/endpoints."""
    return jsonify({"endpoints": {"provider": "acestep-local", "endpoint": "local"}})


@bp.route("/health", methods=["GET"])
def get_health():
    """GET /api/generate/health."""
    return jsonify({"healthy": True})


@bp.route("/debug/<task_id>", methods=["GET"])
def get_debug(task_id: str):
    """GET /api/generate/debug/:taskId — raw job info."""
    with _jobs_lock:
        job = _jobs.get(task_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"rawResponse": job})


def _format_with_lm(data: dict) -> tuple[dict | None, str | None]:
    """
    Best-effort input formatting via ACE-Step LM.
    Returns (response payload, unavailable_reason).
    - payload is not None when formatter executed (including success=False responses from LM).
    - unavailable_reason explains why LM formatting could not run at all.
    """
    caption = (data.get("caption") or "").strip()
    lyrics = (data.get("lyrics") or "").strip()
    if not caption and not lyrics:
        return None, "Please provide Style or Lyrics input to format."

    LLMHandler = None
    format_sample = None
    import_errors: list[str] = []
    try:
        from acestep.llm_inference import LLMHandler as _LLMHandler
        from acestep.inference import format_sample as _format_sample
        LLMHandler = _LLMHandler
        format_sample = _format_sample
    except Exception as e1:
        import_errors.append(f"acestep.llm_inference + acestep.inference.format_sample: {e1}")
    if LLMHandler is None or format_sample is None:
        try:
            from acestep.inference import LLMHandler as _LLMHandler  # type: ignore[attr-defined]
            from acestep.inference import format_sample as _format_sample
            LLMHandler = _LLMHandler
            format_sample = _format_sample
        except Exception as e2:
            import_errors.append(f"acestep.inference (LLMHandler, format_sample): {e2}")
    if LLMHandler is None or format_sample is None:
        reason = (
            "LM modules failed to import. "
            "This build likely has a non-1.5 ACE-Step package. "
            f"Tried: {' | '.join(import_errors)}"
        )
        logging.info("[API format] %s", reason)
        return None, reason

    cfg = load_config() or {}
    lm_id = str(cfg.get("ace_step_lm") or "1.7B").strip()
    if not lm_id or lm_id.lower() == "none":
        return None, "LM model is set to 'none' in Settings > Models."

    try:
        checkpoints_root = get_models_folder() / "checkpoints"
        lm_checkpoint_path = _resolve_lm_checkpoint_path(lm_id, checkpoints_root)
    except Exception as path_err:
        reason = f"Could not resolve LM checkpoint path: {path_err}"
        logging.info("[API format] %s", reason)
        return None, reason
    if not lm_checkpoint_path:
        return None, f"LM checkpoint for '{lm_id}' not found. Download it in Settings > Models."

    user_metadata: dict = {}
    try:
        bpm = data.get("bpm")
        if bpm is not None:
            bpm_i = int(float(bpm))
            if bpm_i > 0:
                user_metadata["bpm"] = bpm_i
    except Exception:
        pass
    try:
        duration = data.get("duration")
        if duration is not None:
            duration_f = float(duration)
            if duration_f > 0:
                user_metadata["duration"] = duration_f
    except Exception:
        pass
    key_scale = (data.get("keyScale") or data.get("key_scale") or "").strip()
    if key_scale:
        user_metadata["keyscale"] = key_scale
    time_sig = (data.get("timeSignature") or data.get("time_signature") or "").strip()
    if time_sig:
        user_metadata["timesignature"] = time_sig
    language = (data.get("language") or "").strip()
    if language and language.lower() not in ("unknown", "auto"):
        user_metadata["language"] = language

    try:
        temperature = float(data.get("temperature") or 0.85)
    except Exception:
        temperature = 0.85
    try:
        top_k = int(data.get("topK")) if data.get("topK") not in (None, "") else None
    except Exception:
        top_k = None
    try:
        top_p = float(data.get("topP")) if data.get("topP") not in (None, "") else None
    except Exception:
        top_p = None

    try:
        llm = LLMHandler()
        device = "cuda" if bool(os.environ.get("CUDA_VISIBLE_DEVICES")) else "cpu"
        lm_path = Path(str(lm_checkpoint_path))
        init_errors: list[str] = []
        init_ok = False
        init_attempts = [
            # Prefer explicit non-vLLM backends first, especially on CPU/MPS runs.
            {"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "backend": "pytorch", "device": device},
            {"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "backend": "transformers", "device": device},
            {"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "backend": "hf", "device": device},
            # ACE-Step 1.5 signature from docs (backend default)
            {"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "device": device},
            # Older/simple initialize signature
            {"checkpoint_dir": str(lm_path), "device": device},
            # Some variants accept direct lm_model_path only
            {"lm_model_path": str(lm_path), "device": device},
        ]
        if device == "cuda":
            init_attempts.append({"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "backend": "vllm", "device": device})
        for kwargs in init_attempts:
            try:
                llm.initialize(**kwargs)
                init_ok = True
                break
            except Exception as init_err:
                init_errors.append(f"{kwargs}: {init_err}")
        if not init_ok:
            raise RuntimeError("LLMHandler.initialize failed for all known signatures: " + " | ".join(init_errors))
        def _run_format():
            return format_sample(
                llm_handler=llm,
                caption=caption,
                lyrics=lyrics,
                user_metadata=user_metadata or None,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
            )

        result = _run_format()
        # Some ACE-Step builds return "LLM not initialized" without throwing.
        status_msg = str(getattr(result, "status_message", "") or "")
        if "llm not initialized" in status_msg.lower():
            retry_attempts = [
                {"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "backend": "pytorch", "device": device},
                {"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "backend": "transformers", "device": device},
                {"checkpoint_dir": str(lm_path.parent), "lm_model_path": lm_path.name, "backend": "hf", "device": device},
            ]
            for kwargs in retry_attempts:
                try:
                    llm.initialize(**kwargs)
                    result = _run_format()
                    status_msg = str(getattr(result, "status_message", "") or "")
                    if "llm not initialized" not in status_msg.lower():
                        break
                except Exception:
                    continue
        if result is None:
            return None, "LM formatter returned no result."
    except Exception as run_err:
        reason = f"LM inference failed: {run_err}"
        logging.warning("[API format] %s", reason)
        return None, reason

    success = bool(getattr(result, "success", True))
    return {
        "success": success,
        "caption": getattr(result, "caption", None),
        "lyrics": getattr(result, "lyrics", None),
        "bpm": getattr(result, "bpm", None),
        "duration": getattr(result, "duration", None),
        "key_scale": getattr(result, "keyscale", None),
        "language": getattr(result, "language", None),
        "time_signature": getattr(result, "timesignature", None),
        "status_message": getattr(result, "status_message", None),
        "error": getattr(result, "error", None),
    }, None


def _normalize_lyrics_sections(lyrics: str) -> str:
    text = (lyrics or "").strip()
    if not text:
        return text
    lines = [ln.rstrip() for ln in text.splitlines()]
    tag_re = re.compile(r"^\s*\[\s*([A-Za-z][A-Za-z0-9 _-]*?)\s*\]\s*$")
    has_any_tag = any(tag_re.match(ln) for ln in lines)

    def _clean_tag(tag: str) -> str:
        low = re.sub(r"\s+", " ", tag.strip().lower())
        mapping = {
            "intro": "Intro",
            "verse": "Verse",
            "chorus": "Chorus",
            "pre-chorus": "Pre-Chorus",
            "post-chorus": "Post-Chorus",
            "bridge": "Bridge",
            "outro": "Outro",
            "hook": "Hook",
            "refrain": "Refrain",
        }
        for k, v in mapping.items():
            if low == k or low.startswith(k + " "):
                suffix = low[len(k):].strip()
                return f"[{v}{(' ' + suffix) if suffix else ''}]"
        return f"[{tag.strip().title()}]"

    if has_any_tag:
        out: list[str] = []
        prev_blank = False
        for ln in lines:
            m = tag_re.match(ln)
            if m:
                out.append(_clean_tag(m.group(1)))
                prev_blank = False
                continue
            if not ln.strip():
                if not prev_blank:
                    out.append("")
                prev_blank = True
                continue
            out.append(ln.strip())
            prev_blank = False
        return "\n".join(out).strip()

    # No structure tags: split paragraphs and apply a simple song structure.
    paragraphs: list[str] = []
    cur: list[str] = []
    for ln in lines:
        if ln.strip():
            cur.append(ln.strip())
        else:
            if cur:
                paragraphs.append("\n".join(cur))
                cur = []
    if cur:
        paragraphs.append("\n".join(cur))
    if not paragraphs:
        return text

    labels = ["[Verse 1]", "[Chorus]", "[Verse 2]", "[Chorus]", "[Bridge]", "[Chorus]", "[Outro]"]
    out: list[str] = []
    verse_n = 3
    for i, block in enumerate(paragraphs):
        if i < len(labels):
            tag = labels[i]
        else:
            tag = f"[Verse {verse_n}]"
            verse_n += 1
        out.append(tag)
        out.append(block)
        out.append("")
    return "\n".join(out).strip()


def _infer_style_from_lyrics(lyrics: str) -> str:
    t = (lyrics or "").lower()
    if not t.strip():
        return "emotional vocal song with clear verse-chorus structure"
    if any(w in t for w in ("black days", "fate", "fear", "night", "blind", "fall")):
        return "dark alternative rock, melancholic grunge vibe, expressive male vocals, dynamic verse-chorus structure"
    if any(w in t for w in ("dance", "party", "club", "tonight", "bailando")):
        return "upbeat pop dance track, catchy hooks, energetic vocal delivery"
    if any(w in t for w in ("love", "heart", "tears", "alone", "broken")):
        return "emotional pop rock ballad, introspective lyrics, wide dynamic chorus"
    return "vocal alt-pop/rock song, emotional tone, clear verse-chorus form"


def _expand_style_prompt(caption: str, lyrics: str) -> str:
    cap = re.sub(r"\s+", " ", (caption or "").strip().strip(","))
    lyr = (lyrics or "").lower()
    low = f"{cap.lower()} {lyr}".strip()
    if not cap:
        return _infer_style_from_lyrics(lyrics)

    def has_any(words: tuple[str, ...]) -> bool:
        return any(w in low for w in words)

    additions: list[str] = []

    # Genre/style axis
    has_genre = has_any((
        "rock", "grunge", "metal", "pop", "dance", "edm", "house", "hip hop", "rap",
        "r&b", "soul", "jazz", "blues", "folk", "country", "acoustic", "orchestral",
        "cinematic", "ambient", "electronic", "alt", "alternative",
    ))
    if not has_genre:
        if has_any(("black days", "fear", "fate", "night", "blind", "fall", "dark")):
            additions.append("dark alternative rock with subtle grunge texture")
        elif has_any(("dance", "party", "club", "tonight", "bailando")):
            additions.append("upbeat pop dance production with modern electronic polish")
        elif has_any(("love", "heart", "alone", "tears", "broken")):
            additions.append("emotional pop-rock ballad character")
        else:
            additions.append("modern alt-pop/rock character")

    # Mood axis
    has_mood = has_any((
        "dark", "melanch", "moody", "sad", "brooding", "uplift", "happy", "energetic",
        "aggressive", "tender", "warm", "cinematic", "emotional", "introspective",
    ))
    if not has_mood:
        if has_any(("black days", "fear", "fate", "night", "blind", "fall", "empty")):
            additions.append("brooding, introspective mood")
        elif has_any(("dance", "party", "club", "celebrate")):
            additions.append("high-energy, hook-forward mood")
        else:
            additions.append("emotionally focused tone")

    # Instrumentation axis
    has_instruments = has_any((
        "guitar", "bass", "drum", "synth", "piano", "string", "pad", "808", "perc",
        "orchestra", "brass", "keys",
    ))
    if not has_instruments:
        if has_any(("rock", "grunge", "alt", "alternative", "black days")):
            additions.append("gritty electric guitars, driving bass, and punchy live drums")
        elif has_any(("dance", "edm", "house", "electronic", "club")):
            additions.append("tight electronic drums, deep bass, and bright synth hooks")
        else:
            additions.append("focused rhythm section with melodic lead layers")

    # Arrangement / structure axis
    has_structure = has_any(("verse", "chorus", "bridge", "drop", "build", "hook", "arrangement", "structure"))
    if not has_structure:
        additions.append("clear verse-chorus contrast with a stronger chorus lift")

    # Vocal direction axis
    has_vocal = has_any(("vocal", "voice", "sung", "singer", "male vocal", "female vocal", "duet", "harmony"))
    if lyrics.strip() and not has_vocal:
        additions.append("expressive lead vocals with natural phrasing")

    # Keep repeated clicks mostly idempotent.
    deduped = [a for a in additions if a.lower() not in cap.lower()]
    if not deduped:
        return cap
    return f"{cap}, {', '.join(deduped)}"


def _heuristic_format_input(data: dict, reason: str | None) -> dict:
    mode = str(data.get("mode") or "general").strip().lower()
    caption_in = (data.get("caption") or "").strip()
    lyrics_in = (data.get("lyrics") or "").strip()

    caption_out = caption_in
    lyrics_out = lyrics_in

    if mode in ("style", "general"):
        if not caption_out and lyrics_in:
            caption_out = _infer_style_from_lyrics(lyrics_in)
        elif caption_out:
            caption_out = _expand_style_prompt(caption_out, lyrics_in)

    if mode in ("lyrics", "general") and lyrics_in:
        lyrics_out = _normalize_lyrics_sections(lyrics_in)

    return {
        "success": True,
        "caption": caption_out,
        "lyrics": lyrics_out,
        "bpm": data.get("bpm"),
        "duration": data.get("duration"),
        "key_scale": data.get("keyScale"),
        "language": data.get("language"),
        "time_signature": data.get("timeSignature"),
        "status_message": f"LM formatter unavailable. Reason: {reason or 'unknown'}. Applied local heuristic formatting.",
    }


@bp.route("/format", methods=["POST"])
def format_input():
    """POST /api/generate/format — format caption/lyrics via ACE-Step LM when available."""
    data = request.get_json(silent=True) or {}
    lm_payload, unavailable_reason = _format_with_lm(data)
    if lm_payload is not None:
        return jsonify(lm_payload)
    return jsonify(_heuristic_format_input(data, unavailable_reason))
