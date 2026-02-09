"""
Generation API for new UI. Maps ace-step-ui GenerationParams to generate_track_ace();
job queue stored under get_user_data_dir(). No auth. Real implementation (no mocks).
"""

import json
import logging
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

from cdmf_paths import get_output_dir, get_user_data_dir, get_models_folder, load_config, save_config
from cdmf_tracks import get_audio_duration, list_lora_adapters, load_track_meta, save_track_meta
from cdmf_generation_job import GenerationCancelled
import cdmf_state
from generate_ace import register_job_progress_callback

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


def _is_model_available(dit_tag: str) -> bool:
    """Return True if the given DiT model is installed and ready (no download needed). Used to promote pending_model jobs."""
    if not dit_tag or not isinstance(dit_tag, str):
        return False
    dit = dit_tag.strip().lower()
    DIT_15_FOLDERS = {
        "turbo": "acestep-v15-turbo",
        "base": "acestep-v15-base",
        "sft": "acestep-v15-sft",
        "turbo-shift1": "acestep-v15-turbo-shift1",
        "turbo-shift3": "acestep-v15-turbo-shift3",
        "turbo-continuous": "acestep-v15-turbo-continuous",
    }
    REQUIRED_SUBDIRS = ("music_dcae_f8c8", "music_vocoder", "ace_step_transformer", "umt5-base")
    folder = DIT_15_FOLDERS.get(dit)
    models_root = Path(get_models_folder()) / "checkpoints"
    if folder:
        candidate = models_root / folder
        if not candidate.exists():
            return False
        for sub in REQUIRED_SUBDIRS:
            if not (candidate / sub).exists():
                return False
        return True
    # Legacy v1
    try:
        from ace_model_setup import ace_models_present
        return ace_models_present()
    except Exception:
        return False


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


def _update_job_progress_from_log(
    percent: int, current: int, total: int, eta_seconds: float | None
) -> None:
    """Update current job progress from parsed tqdm log line (log handler runs in same thread as worker)."""
    with _jobs_lock:
        jid = cdmf_state.get_current_generation_job_id()
        if not jid:
            return
        job = _jobs.get(jid)
        if not job:
            return
        job["progressPercent"] = round(float(percent), 1)
        job["progressSteps"] = f"{current}/{total}"
        if eta_seconds is not None:
            job["progressEta"] = round(float(eta_seconds), 1)


def _run_generation(job_id: str) -> None:
    """Background: run generate_track_ace and update job."""
    global _generation_busy, _current_job_id
    prev_config = None
    config_switched = False
    try:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if not job or job.get("status") != "queued":
                return
            job_dit = job.get("dit_model") or "turbo"
        # If required model is not installed, leave job as pending_model so it runs after user installs it.
        if not _is_model_available(job_dit):
            logging.info("[API generate] Job %s waiting for model %s (not installed)", job_id, job_dit)
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job and job.get("status") == "queued":
                    job["status"] = "pending_model"
                    job["pendingReason"] = (
                        f"Model '{job_dit}' is not installed. Install it from Settings → Models to run this job."
                    )
            return
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
        cdmf_state.set_progress_updater(_update_job_progress_from_log)
        cancel_check = lambda: _is_cancel_requested(job_id)
        from generate_ace import generate_track_ace, clear_ace_pipeline

        # Use job's dit_model (e.g. base for cover). Temporarily switch config so pipeline loads the right model.
        with _jobs_lock:
            j = _jobs.get(job_id)
            job_dit = (j.get("dit_model") or "turbo") if j else "turbo"
        prev_config = load_config() or {}
        prev_config = dict(prev_config)
        config_switched = job_dit != (prev_config.get("ace_step_dit_model") or "turbo")
        if config_switched:
            save_config({**prev_config, "ace_step_dit_model": job_dit})
            clear_ace_pipeline()

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
            duration = float(d if d is not None else 60)
        except (TypeError, ValueError):
            duration = 60
        # UI may send duration=-1 or 0; for cover we may get duration from source file below
        if duration > 0:
            duration = max(15, min(240, duration))
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
        # Lego/extract/complete: instruction (uppercase track) + optional caption. Instruction is auto (e.g. "Generate the GUITAR track..."); caption is user style (key, BPM, tone).
        # No metas — BPM/key/timesignature should match the input backing.
        if task in ("lego", "extract", "complete"):
            instruction = _uppercase_track_in_instruction(
                instruction or "Generate an instrument track based on the audio context:"
            )
            cap = (caption or "").strip()
            if not cap:
                prompt = instruction.rstrip(":").strip()
            else:
                prompt = (instruction.rstrip(":").strip() + ", " + cap).strip()
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
        # Lego/extract/complete: default ref_audio_strength=1.0 to avoid MPS crash (batch dim mismatch when <1.0).
        # See https://github.com/ace-step/ACE-Step-1.5/issues/117 — lower values can improve "new instrument" feel but crash on Apple Silicon.
        # See docs/ACE-Step-INFERENCE.md: audio_cover_strength 1.0 = strong adherence; lower = more prompt influence.
        audio2audio_enable = bool(src_audio_path)
        ref_default = 0.8 if task in ("cover", "retake") else (0.5 if task == "audio2audio" else 0.7)
        if task in ("lego", "extract", "complete"):
            ref_default = 1.0  # 1.0 avoids MPS crash; user can lower via legoBackingInfluence if not on Apple Silicon
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

        # Shift (timestep): 3.0 recommended for lego/timing; 6.0 pipeline default for others. See ACE-Step-1.5 issue #117.
        try:
            shift_val = float(params.get("shift") or params.get("shiftFactor") or 0)
        except (TypeError, ValueError):
            shift_val = 0.0
        if shift_val <= 0:
            shift_val = 3.0 if task in ("lego", "extract", "complete") else 6.0
        shift_val = max(0.1, min(10.0, shift_val))

        # LoRA adapter (optional): path or folder name under custom_lora
        lora_name_or_path = (params.get("loraNameOrPath") or params.get("lora_name_or_path") or "").strip()
        try:
            lora_weight = float(params.get("loraWeight") or params.get("lora_weight") or 0.75)
        except (TypeError, ValueError):
            lora_weight = 0.75
        lora_weight = max(0.0, min(2.0, lora_weight))

        # Thinking / LM / CoT (passed through so pipeline or future LM path can use them).
        # Lego/extract/complete: force thinking=False so src_audio drives context; thinking=True overrides with LLM codes (issue #117).
        thinking = bool(params.get("thinking", False))
        if task in ("lego", "extract", "complete"):
            thinking = False
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
            shift=shift_val,
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
        actual_seconds = float(summary.get("actual_seconds") or duration)

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
        err_msg = str(e)
        # Keep job queued as pending_model when model is missing so it can run after user installs it.
        if "not installed" in err_msg.lower() or "Settings → Models" in err_msg:
            logging.info("[API generate] Job %s waiting for model: %s", job_id, err_msg[:120])
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job["status"] = "pending_model"
                    job["pendingReason"] = err_msg
                    job["error"] = None
        else:
            logging.exception("Generation job %s failed", job_id)
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job["status"] = "failed"
                    job["error"] = err_msg
    finally:
        cdmf_state.set_progress_updater(None)
        if config_switched and prev_config:
            save_config(prev_config)
            clear_ace_pipeline()
        cdmf_state.set_current_generation_job_id(None)
        _generation_busy = False
        with _jobs_lock:
            _current_job_id = None
            _cancel_requested.discard(job_id)
        # Promote pending_model jobs to queued when their model is now available; then start first queued job.
        with _jobs_lock:
            for jid in _job_order:
                j = _jobs.get(jid)
                if j and j.get("status") == "pending_model":
                    dit = j.get("dit_model") or "turbo"
                    if _is_model_available(dit):
                        j["status"] = "queued"
                        j["pendingReason"] = None
                        logging.info("[API generate] Job %s promoted to queued (model %s now available)", jid, dit)
            for jid in _job_order:
                j = _jobs.get(jid)
                if j and j.get("status") == "queued":
                    threading.Thread(target=_run_generation, args=(jid,), daemon=True).start()
                    break


@bp.route("/model-download-status", methods=["GET"])
def get_model_download_status():
    """GET /api/generate/model-download-status — whether pipeline is loading (may be downloading model files)."""
    try:
        st = getattr(cdmf_state, "GENERATION_MODEL_LOADING", {})
        return jsonify({
            "in_progress": bool(st.get("in_progress")),
            "message": st.get("message") or "Preparing model (downloading if needed)...",
        })
    except Exception as e:
        logging.warning("[API generate] model-download-status failed: %s", e)
        return jsonify({"in_progress": False, "message": ""})


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
        # User override from Generation tab model selector takes precedence; else auto base for cover (per docs).
        task_for_dit = (params_copy.get("task_type") or params_copy.get("taskType") or "text2music").strip().lower()
        explicit_dit = (params_copy.get("aceStepDitModel") or params_copy.get("ace_step_dit_model") or "").strip()
        if explicit_dit:
            dit_tag = explicit_dit
        elif task_for_dit == "cover":
            dit_tag = "base"
        else:
            dit_tag = config.get("ace_step_dit_model") or "turbo"
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
        "pendingReason": job.get("pendingReason") if status == "pending_model" else None,
    }
    return jsonify(out)


@bp.route("/retry-pending", methods=["POST"])
def retry_pending():
    """POST /api/generate/retry-pending — promote pending_model jobs to queued if model is now available, start first queued job. Call after model download completes."""
    global _generation_busy
    promoted = 0
    started = None
    with _jobs_lock:
        for jid in _job_order:
            j = _jobs.get(jid)
            if j and j.get("status") == "pending_model":
                dit = j.get("dit_model") or "turbo"
                if _is_model_available(dit):
                    j["status"] = "queued"
                    j["pendingReason"] = None
                    promoted += 1
                    logging.info("[API generate] Job %s promoted to queued (model %s now available)", jid, dit)
        if not _generation_busy:
            for jid in _job_order:
                j = _jobs.get(jid)
                if j and j.get("status") == "queued":
                    _generation_busy = True
                    threading.Thread(target=_run_generation, args=(jid,), daemon=True).start()
                    started = jid
                    break
    return jsonify({
        "ok": True,
        "promoted": promoted,
        "startedJobId": started,
    })


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
        if status in ("queued", "pending_model"):
            job["status"] = "cancelled"
            job["error"] = "Cancelled by user"
            job["pendingReason"] = None
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


@bp.route("/format", methods=["POST"])
def format_input():
    """POST /api/generate/format — stub; return same payload."""
    data = request.get_json(silent=True) or {}
    return jsonify({
        "success": True,
        "caption": data.get("caption"),
        "lyrics": data.get("lyrics"),
        "bpm": data.get("bpm"),
        "duration": data.get("duration"),
        "key_scale": data.get("keyScale"),
        "time_signature": data.get("timeSignature"),
    })
