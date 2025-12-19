# C:\AceForge\cdmf_generation.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

import json
import os
import re
import time
import traceback

from flask import Blueprint, request, render_template_string, jsonify
from werkzeug.utils import secure_filename
from pydub import AudioSegment

import cdmf_state
import cdmf_tracks
from cdmf_paths import (
    APP_DIR,
    DEFAULT_OUT_DIR,
    TRAINING_DATA_ROOT,
    CUSTOM_LORA_ROOT,
    SEED_VIBES,
)

def _extract_first_json_object(text: str) -> Dict[str, Any]:
    """
    Try to recover the first JSON object from a text-generation response.

    Handles things like:
      ```json
      { "prompt": "...", "lyrics": "..." }
      ```
    or extra text before/after the JSON block.
    """
    if not isinstance(text, str):
        raise ValueError("Expected string from LLM, got %r" % (type(text),))

    cleaned = text.strip()

    # Strip ```json ... ``` fences if present
    if cleaned.startswith("```"):
        # Drop first line (``` or ```json)
        cleaned = re.sub(r"^```[a-zA-Z0-9_+-]*\s*", "", cleaned)
        # Drop trailing ```
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()

    # First try: maybe it's now clean JSON
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fallback: find the first {...} span by bracket counting
    start = cleaned.find("{")
    if start == -1:
        raise ValueError("No '{' found in LLM output; cannot extract JSON.")

    depth = 0
    end = None
    for i, ch in enumerate(cleaned[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        raise ValueError("Unbalanced braces in LLM output; cannot extract JSON.")

    snippet = cleaned[start:end]
    return json.loads(snippet)

def create_generation_blueprint(
    html_template: str,
    ui_defaults: Dict[str, Any],
    generate_track_ace: Callable[..., Dict[str, Any]],
) -> Blueprint:
    """
    Create a blueprint that defines:
      * "/"       -> index page
      * "/generate" -> ACE-Step generation endpoint
    """
    bp = Blueprint("cdmf_generation", __name__)

    UI_DEFAULT_TARGET_SECONDS = int(ui_defaults.get("target_seconds", 90))
    UI_DEFAULT_FADE_IN = float(ui_defaults.get("fade_in", 0.5))
    UI_DEFAULT_FADE_OUT = float(ui_defaults.get("fade_out", 0.5))
    UI_DEFAULT_STEPS = int(ui_defaults.get("steps", 55))
    UI_DEFAULT_GUIDANCE = float(ui_defaults.get("guidance_scale", 6.0))
    UI_DEFAULT_VOCAL_GAIN_DB = float(ui_defaults.get("vocal_gain_db", 0.0))
    UI_DEFAULT_INSTRUMENTAL_GAIN_DB = float(
        ui_defaults.get("instrumental_gain_db", 0.0)
    )

    @bp.route("/", methods=["GET"])
    def index():
        cdmf_state.reset_progress()

        tracks = cdmf_tracks.list_music_files()
        current_track = tracks[-1] if tracks else None
        presets = cdmf_tracks.load_presets()

        with cdmf_state.MODEL_LOCK:
            models_ready = cdmf_state.MODEL_STATUS["state"] == "ready"
            model_state = cdmf_state.MODEL_STATUS["state"]
            model_message = cdmf_state.MODEL_STATUS["message"]

        return render_template_string(
            html_template,
            # Let the frontend pick a random preset; start empty here.
            prompt="",
            negative_prompt="",
            target_seconds=UI_DEFAULT_TARGET_SECONDS,
            fade_in=UI_DEFAULT_FADE_IN,
            fade_out=UI_DEFAULT_FADE_OUT,
            vocal_gain_db=UI_DEFAULT_VOCAL_GAIN_DB,
            instrumental_gain_db=UI_DEFAULT_INSTRUMENTAL_GAIN_DB,
            steps=UI_DEFAULT_STEPS,
            guidance_scale=UI_DEFAULT_GUIDANCE,
            # Expose defaults explicitly to the template
            UI_DEFAULT_TARGET_SECONDS=UI_DEFAULT_TARGET_SECONDS,
            UI_DEFAULT_FADE_IN=UI_DEFAULT_FADE_IN,
            UI_DEFAULT_FADE_OUT=UI_DEFAULT_FADE_OUT,
            UI_DEFAULT_STEPS=UI_DEFAULT_STEPS,
            UI_DEFAULT_GUIDANCE=UI_DEFAULT_GUIDANCE,
            UI_DEFAULT_VOCAL_GAIN_DB=UI_DEFAULT_VOCAL_GAIN_DB,
            UI_DEFAULT_INSTRUMENTAL_GAIN_DB=UI_DEFAULT_INSTRUMENTAL_GAIN_DB,
            seed=0,
            out_dir=DEFAULT_OUT_DIR,
            basename="Candy Dreams",
            default_out_dir=DEFAULT_OUT_DIR,
            seed_vibe="any",
            seed_vibes=SEED_VIBES,
            message=None,
            short_message="",
            details="",
            error=False,
            tracks=tracks,
            current_track=current_track,
            autoplay_url="",
            instrumental=False,
            lyrics="",
            bpm=None,
            presets=presets,
            models_ready=models_ready,
            model_state=model_state,
            model_message=model_message,
            training_data_root=str(TRAINING_DATA_ROOT),
            lora_adapters=cdmf_tracks.list_lora_adapters(),
            lora_name_or_path="",
        )

    @bp.route("/generate", methods=["POST"])
    def generate():
        presets = cdmf_tracks.load_presets()

        with cdmf_state.MODEL_LOCK:
            models_ready = cdmf_state.MODEL_STATUS["state"] == "ready"
            model_state = cdmf_state.MODEL_STATUS["state"]
            model_message = cdmf_state.MODEL_STATUS["message"]

        prompt = request.form.get("prompt", "").strip()
        negative_prompt = ""  # ACE-Step v0.1 doesn't use negative prompt
        lyrics = request.form.get("lyrics", "").strip()
        instrumental = ("instrumental" in request.form)

        try:
            print(
                "[AceForge] GENERATE request\n"
                f"  Prompt:          {prompt!r}\n"
                "  Negative prompt: (disabled / empty)",
                flush=True,
            )
        except Exception:
            pass

        try:
            # --- Core knobs ----------------------------------------------------
            target_seconds = float(request.form.get("target_seconds", "90"))
            fade_in = float(request.form.get("fade_in", "0.5"))
            fade_out = float(request.form.get("fade_out", "0.5"))

            vocal_gain_raw = request.form.get("vocal_gain_db", "").strip()
            vocal_gain_db = UI_DEFAULT_VOCAL_GAIN_DB
            if vocal_gain_raw:
                try:
                    vocal_gain_db = float(vocal_gain_raw)
                except ValueError:
                    raise ValueError("Vocal level must be a number (dB).")

            inst_gain_raw = request.form.get("instrumental_gain_db", "").strip()
            instrumental_gain_db = UI_DEFAULT_INSTRUMENTAL_GAIN_DB
            if inst_gain_raw:
                try:
                    instrumental_gain_db = float(inst_gain_raw)
                except ValueError:
                    raise ValueError("Instrumental level must be a number (dB).")

            steps = int(request.form.get("steps", str(UI_DEFAULT_STEPS)))
            guidance_scale = float(
                request.form.get("guidance_scale", str(UI_DEFAULT_GUIDANCE))
            )

            bpm_raw = request.form.get("bpm", "").strip()
            bpm: Optional[float] = None
            if bpm_raw:
                try:
                    bpm = float(bpm_raw)
                except ValueError:
                    raise ValueError("Beats per minute must be a number.")

            # --- Advanced ACE-Step controls ------------------------------------
            scheduler_type = request.form.get("scheduler_type", "euler").strip() or "euler"
            cfg_type = request.form.get("cfg_type", "apg").strip() or "apg"

            omega_raw = request.form.get("omega_scale", "").strip()
            omega_scale = 5.0
            if omega_raw:
                try:
                    omega_scale = float(omega_raw)
                except ValueError:
                    raise ValueError("Omega scale must be a number.")

            guidance_interval_raw = request.form.get("guidance_interval", "").strip()
            guidance_interval = 0.75
            if guidance_interval_raw:
                try:
                    guidance_interval = float(guidance_interval_raw)
                except ValueError:
                    raise ValueError("Guidance interval must be a number.")

            guidance_decay_raw = request.form.get("guidance_interval_decay", "").strip()
            guidance_interval_decay = 0.0
            if guidance_decay_raw:
                try:
                    guidance_interval_decay = float(guidance_decay_raw)
                except ValueError:
                    raise ValueError("Guidance interval decay must be a number.")

            min_guidance_raw = request.form.get("min_guidance_scale", "").strip()
            min_guidance_scale = 7.0
            if min_guidance_raw:
                try:
                    min_guidance_scale = float(min_guidance_raw)
                except ValueError:
                    raise ValueError("Min guidance scale must be a number.")

            use_erg_tag = ("use_erg_tag" in request.form)
            use_erg_lyric = ("use_erg_lyric" in request.form)
            use_erg_diffusion = ("use_erg_diffusion" in request.form)

            oss_steps_raw = request.form.get("oss_steps", "").strip()
            oss_steps = oss_steps_raw or None

            task = request.form.get("task", "text2music").strip() or "text2music"

            repaint_start_raw = request.form.get("repaint_start", "").strip()
            repaint_start = 0.0
            if repaint_start_raw:
                try:
                    repaint_start = float(repaint_start_raw)
                except ValueError:
                    raise ValueError("Repaint start must be a number.")

            repaint_end_raw = request.form.get("repaint_end", "").strip()
            repaint_end = 0.0
            if repaint_end_raw:
                try:
                    repaint_end = float(repaint_end_raw)
                except ValueError:
                    raise ValueError("Repaint end must be a number.")

            retake_variance_raw = request.form.get("retake_variance", "").strip()
            retake_variance = 0.5
            if retake_variance_raw:
                try:
                    retake_variance = float(retake_variance_raw)
                except ValueError:
                    raise ValueError("Retake variance must be a number.")

            audio2audio_enable = ("audio2audio_enable" in request.form)

            ref_strength_raw = request.form.get("ref_audio_strength", "").strip()
            ref_audio_strength = 0.7
            if ref_strength_raw:
                try:
                    ref_audio_strength = float(ref_strength_raw)
                except ValueError:
                    raise ValueError("Reference audio strength must be a number.")

            # LoRA: uploaded file or manual path
            lora_name_or_path: Optional[str] = None

            uploaded_lora = request.files.get("lora_file")
            if uploaded_lora and uploaded_lora.filename:
                try:
                    safe_name = (
                        secure_filename(uploaded_lora.filename)
                        or "lora_adapter.safetensors"
                    )
                except Exception:
                    safe_name = uploaded_lora.filename or "lora_adapter.safetensors"

                base_name, ext = os.path.splitext(safe_name)
                if not ext:
                    ext = ".safetensors"

                reused_adapter_path: Optional[str] = None
                try:
                    data = uploaded_lora.read()
                    uploaded_lora.stream.seek(0)

                    if data:
                        import hashlib

                        new_hash = hashlib.sha256(data).hexdigest()

                        for adapter in cdmf_tracks.list_lora_adapters():
                            adapter_dir = Path(adapter["path"])
                            candidate = adapter_dir / "pytorch_lora_weights.safetensors"
                            if not candidate.is_file():
                                continue
                            try:
                                with candidate.open("rb") as f:
                                    existing_hash = hashlib.sha256(f.read()).hexdigest()
                            except Exception:
                                continue

                            if existing_hash == new_hash:
                                reused_adapter_path = str(adapter_dir)
                                print(
                                    "[AceForge] Uploaded LoRA matches existing "
                                    f"adapter; reusing {adapter_dir}",
                                    flush=True,
                                )
                                break
                except Exception as e:
                    print(
                        "[AceForge] WARNING: failed to hash uploaded LoRA for "
                        f"deduplication: {e}",
                        flush=True,
                    )

                if reused_adapter_path is not None:
                    lora_name_or_path = reused_adapter_path
                else:
                    adapter_name = base_name or "custom_lora_lora"

                    if adapter_name.lower() == "pytorch_lora_weights":
                        adapter_name = f"uploaded_lora_{int(time.time())}"

                    adapter_dir = CUSTOM_LORA_ROOT / adapter_name
                    adapter_dir.mkdir(parents=True, exist_ok=True)

                    lora_path = adapter_dir / "pytorch_lora_weights.safetensors"
                    try:
                        uploaded_lora.save(str(lora_path))
                        lora_name_or_path = str(adapter_dir)
                        print(
                            f"[AceForge] Saved uploaded LoRA weights to {lora_path}",
                            flush=True,
                        )
                    except Exception as e:
                        print(
                            f"[AceForge] WARNING: failed to save uploaded LoRA "
                            f"weights {uploaded_lora.filename}: {e}",
                            flush=True,
                        )

            if lora_name_or_path is None:
                manual_lora = request.form.get("lora_name_or_path", "").strip()
                if manual_lora:
                    ml_path = Path(manual_lora)

                    if ml_path.suffix.lower() in (".safetensors", ".bin", ".pt"):
                        lora_name_or_path = str(ml_path.parent)
                    elif any(sep in manual_lora for sep in ("/", "\\")):
                        lora_name_or_path = manual_lora
                    else:
                        lora_name_or_path = str(APP_DIR / "custom_lora" / manual_lora)

            lora_weight_raw = request.form.get("lora_weight", "").strip()
            lora_weight = 0.75
            if lora_weight_raw:
                try:
                    lora_weight = float(lora_weight_raw)
                except ValueError:
                    raise ValueError("LoRA weight must be a number.")

            # Misc / shared fields
            seed = int(request.form.get("seed", "0"))
            out_dir = (
                request.form.get("out_dir", DEFAULT_OUT_DIR).strip() or DEFAULT_OUT_DIR
            )
            basename = request.form.get("basename", "Candy Dreams").strip() or "Candy Dreams"
            seed_vibe = request.form.get("seed_vibe", "any").strip() or "any"

            preset_id = request.form.get("preset_id", "").strip()
            preset_category = request.form.get("preset_category", "").strip()

            target_seconds = max(1.0, target_seconds)

            if not prompt:
                raise ValueError("Genre / style prompt cannot be empty.")

            out_dir_path = Path(out_dir)
            out_dir_path.mkdir(parents=True, exist_ok=True)

            # Determine reference-audio path
            uploaded_ref = request.files.get("ref_audio_file")
            src_audio_path: Optional[str] = None
            if uploaded_ref and uploaded_ref.filename:
                try:
                    filename = secure_filename(uploaded_ref.filename)
                except Exception:
                    filename = uploaded_ref.filename or ""
                if not filename:
                    filename = f"ref_{int(time.time() * 1000)}.wav"

                name_root, ext = os.path.splitext(filename)
                ext = (ext or "").lower()

                ref_root = out_dir_path / "ref_audio"
                ref_root.mkdir(parents=True, exist_ok=True)

                tmp_path = ref_root / f"{name_root}_{int(time.time() * 1000)}{ext or '.wav'}"
                uploaded_ref.save(str(tmp_path))

                if ext != ".wav":
                    try:
                        wav_path = tmp_path.with_suffix(".wav")
                        audio = AudioSegment.from_file(str(tmp_path))
                        audio.export(str(wav_path), format="wav")
                        try:
                            tmp_path.unlink()
                        except OSError:
                            pass
                        src_audio_path = str(wav_path)
                    except Exception as e:
                        print(
                            f"[AceForge] Warning: failed to convert ref audio "
                            f"{tmp_path} to WAV: {e}",
                            flush=True,
                        )
                        src_audio_path = str(tmp_path)
                else:
                    src_audio_path = str(tmp_path)
            else:
                manual_path = request.form.get("src_audio_path", "").strip()
                src_audio_path = manual_path or None

            cdmf_state.reset_progress()
            with cdmf_state.PROGRESS_LOCK:
                cdmf_state.GENERATION_PROGRESS["current"] = 0.0
                cdmf_state.GENERATION_PROGRESS["total"] = 1.0
                cdmf_state.GENERATION_PROGRESS["stage"] = "ace_infer"
                cdmf_state.GENERATION_PROGRESS["done"] = False
                cdmf_state.GENERATION_PROGRESS["error"] = False

            summary = generate_track_ace(
                genre_prompt=prompt,
                lyrics=lyrics,
                instrumental=instrumental,
                negative_prompt=negative_prompt,
                target_seconds=target_seconds,
                fade_in_seconds=fade_in,
                fade_out_seconds=fade_out,
                seed=seed,
                out_dir=out_dir_path,
                basename=basename,
                seed_vibe=seed_vibe,
                bpm=bpm,
                steps=steps,
                guidance_scale=guidance_scale,
                scheduler_type=scheduler_type,
                cfg_type=cfg_type,
                omega_scale=omega_scale,
                guidance_interval=guidance_interval,
                guidance_interval_decay=guidance_interval_decay,
                min_guidance_scale=min_guidance_scale,
                use_erg_tag=use_erg_tag,
                use_erg_lyric=use_erg_lyric,
                use_erg_diffusion=use_erg_diffusion,
                oss_steps=oss_steps,
                task=task,
                repaint_start=repaint_start,
                repaint_end=repaint_end,
                retake_variance=retake_variance,
                audio2audio_enable=audio2audio_enable,
                ref_audio_strength=ref_audio_strength,
                src_audio_path=src_audio_path,
                lora_name_or_path=lora_name_or_path,
                lora_weight=lora_weight,
                vocal_gain_db=vocal_gain_db,
                instrumental_gain_db=instrumental_gain_db,
            )

            wav_path_raw = summary.get("wav_path")
            if isinstance(wav_path_raw, Path):
                wav_path = wav_path_raw
            else:
                wav_path = Path(str(wav_path_raw))
            summary["wav_path"] = wav_path

            # Update per-track metadata
            try:
                meta = cdmf_tracks.load_track_meta()
                entry: Dict[str, Any] = meta.get(wav_path.name, {})

                if "favorite" not in entry:
                    entry["favorite"] = False

                if preset_category and not entry.get("category"):
                    entry["category"] = preset_category

                try:
                    entry["seconds"] = float(summary.get("actual_seconds") or 0.0)
                except Exception:
                    entry["seconds"] = float(entry.get("seconds") or 0.0)

                if bpm is not None:
                    try:
                        entry["bpm"] = float(bpm)
                    except Exception:
                        pass

                if preset_id:
                    entry["preset_id"] = preset_id

                if not entry.get("created"):
                    entry["created"] = time.time()

                entry["prompt"] = prompt
                entry["lyrics"] = lyrics
                entry["instrumental"] = bool(instrumental)
                entry["seed"] = int(summary.get("seed", seed))
                entry["seed_vibe"] = seed_vibe
                entry["target_seconds"] = float(target_seconds)
                entry["fade_in"] = float(fade_in)
                entry["fade_out"] = float(fade_out)
                entry["vocal_gain_db"] = float(
                    summary.get("vocal_gain_db", vocal_gain_db)
                )
                entry["instrumental_gain_db"] = float(
                    summary.get("instrumental_gain_db", instrumental_gain_db)
                )
                entry["steps"] = int(steps)
                entry["guidance_scale"] = float(guidance_scale)
                entry["basename"] = basename
                entry["out_dir"] = str(out_dir_path)
                entry["negative_prompt"] = negative_prompt
                entry["preset_category"] = preset_category or entry.get("category", "")

                entry["scheduler_type"] = summary.get("scheduler_type")
                entry["cfg_type"] = summary.get("cfg_type")
                entry["omega_scale"] = summary.get("omega_scale")
                entry["guidance_interval"] = summary.get("guidance_interval")
                entry["guidance_interval_decay"] = summary.get("guidance_interval_decay")
                entry["min_guidance_scale"] = summary.get("min_guidance_scale")
                entry["use_erg_tag"] = summary.get("use_erg_tag")
                entry["use_erg_lyric"] = summary.get("use_erg_lyric")
                entry["use_erg_diffusion"] = summary.get("use_erg_diffusion")
                entry["oss_steps"] = summary.get("oss_steps")
                entry["task"] = summary.get("task")
                entry["repaint_start"] = summary.get("repaint_start")
                entry["repaint_end"] = summary.get("repaint_end")
                entry["retake_variance"] = summary.get("retake_variance")
                entry["audio2audio_enable"] = summary.get("audio2audio_enable")
                entry["ref_audio_strength"] = summary.get("ref_audio_strength")
                entry["src_audio_path"] = summary.get("src_audio_path")
                entry["lora_name_or_path"] = summary.get(
                    "lora_name_or_path", lora_name_or_path
                )
                entry["lora_weight"] = summary.get("lora_weight", lora_weight)

                meta[wav_path.name] = entry
                cdmf_tracks.save_track_meta(meta)
            except Exception as e:
                safe_name = getattr(wav_path, "name", repr(wav_path))
                print(
                    f"[AceForge] Failed to update track metadata for {safe_name}: {e}",
                    flush=True,
                )

            current_track = None
            if wav_path.parent.resolve() == Path(DEFAULT_OUT_DIR).resolve():
                current_track = wav_path.name

            with cdmf_state.PROGRESS_LOCK:
                cdmf_state.GENERATION_PROGRESS["current"] = 1.0
                cdmf_state.GENERATION_PROGRESS["total"] = 1.0
                cdmf_state.GENERATION_PROGRESS["stage"] = "done"
                cdmf_state.GENERATION_PROGRESS["done"] = True
                cdmf_state.GENERATION_PROGRESS["error"] = False
                if current_track:
                    cdmf_state.LAST_GENERATED_TRACK = current_track

            tracks = cdmf_tracks.list_music_files()
            autoplay_url = ""

            short_msg = (
                f"{wav_path.name} successfully generated "
                f"(≈{summary['actual_seconds']:.1f}s, seed {summary['seed']})."
            )

            detail_lines = [
                f"File: {wav_path}",
                f"Actual length: ≈{summary['actual_seconds']:.1f}s",
                f"Seed: {summary['seed']}",
                f"Instrumental: {summary.get('instrumental')}",
                f"Steps: {summary.get('steps')}",
                f"Guidance scale: {summary.get('guidance_scale')}",
                f"Scheduler: {summary.get('scheduler_type')}",
                f"CFG type: {summary.get('cfg_type')}",
            ]
            details = "\n".join(str(x) for x in detail_lines if x)

            return render_template_string(
                html_template,
                prompt=prompt,
                negative_prompt=negative_prompt,
                target_seconds=target_seconds,
                fade_in=fade_in,
                fade_out=fade_out,
                vocal_gain_db=vocal_gain_db,
                instrumental_gain_db=instrumental_gain_db,
                steps=steps,
                guidance_scale=guidance_scale,
                UI_DEFAULT_TARGET_SECONDS=UI_DEFAULT_TARGET_SECONDS,
                UI_DEFAULT_FADE_IN=UI_DEFAULT_FADE_IN,
                UI_DEFAULT_FADE_OUT=UI_DEFAULT_FADE_OUT,
                UI_DEFAULT_STEPS=UI_DEFAULT_STEPS,
                UI_DEFAULT_GUIDANCE=UI_DEFAULT_GUIDANCE,
                UI_DEFAULT_VOCAL_GAIN_DB=UI_DEFAULT_VOCAL_GAIN_DB,
                UI_DEFAULT_INSTRUMENTAL_GAIN_DB=UI_DEFAULT_INSTRUMENTAL_GAIN_DB,
                seed=summary["seed"],
                out_dir=str(out_dir_path),
                basename=basename,
                default_out_dir=DEFAULT_OUT_DIR,
                seed_vibe=seed_vibe,
                seed_vibes=SEED_VIBES,
                instrumental=instrumental,
                lyrics=lyrics,
                message=details,
                short_message=short_msg,
                details=details,
                error=False,
                tracks=tracks,
                current_track=current_track,
                autoplay_url=autoplay_url,
                bpm=bpm,
                presets=presets,
                models_ready=models_ready,
                model_state=model_state,
                model_message=model_message,
                training_data_root=str(TRAINING_DATA_ROOT),
                lora_adapters=cdmf_tracks.list_lora_adapters(),
                lora_name_or_path=lora_name_or_path or "",
            )
        except Exception:
            tb = traceback.format_exc()
            msg = f"Error during ACE-Step generation:\n{tb}"

            print(msg, flush=True)

            tracks = cdmf_tracks.list_music_files()
            current_track = tracks[-1] if tracks else None

            with cdmf_state.PROGRESS_LOCK:
                cdmf_state.GENERATION_PROGRESS["error"] = True
                cdmf_state.GENERATION_PROGRESS["done"] = True
                cdmf_state.GENERATION_PROGRESS["stage"] = "error"

            return render_template_string(
                html_template,
                prompt=prompt,
                negative_prompt=negative_prompt,
                target_seconds=request.form.get("target_seconds", "90"),
                fade_in=request.form.get("fade_in", "0.5"),
                fade_out=request.form.get("fade_out", "0.5"),
                vocal_gain_db=request.form.get(
                    "vocal_gain_db", str(UI_DEFAULT_VOCAL_GAIN_DB)
                ),
                instrumental_gain_db=request.form.get(
                    "instrumental_gain_db",
                    str(UI_DEFAULT_INSTRUMENTAL_GAIN_DB),
                ),
                steps=request.form.get("steps", str(UI_DEFAULT_STEPS)),
                guidance_scale=request.form.get(
                    "guidance_scale", str(UI_DEFAULT_GUIDANCE)
                ),
                UI_DEFAULT_TARGET_SECONDS=UI_DEFAULT_TARGET_SECONDS,
                UI_DEFAULT_FADE_IN=UI_DEFAULT_FADE_IN,
                UI_DEFAULT_FADE_OUT=UI_DEFAULT_FADE_OUT,
                UI_DEFAULT_STEPS=UI_DEFAULT_STEPS,
                UI_DEFAULT_GUIDANCE=UI_DEFAULT_GUIDANCE,
                UI_DEFAULT_VOCAL_GAIN_DB=UI_DEFAULT_VOCAL_GAIN_DB,
                UI_DEFAULT_INSTRUMENTAL_GAIN_DB=UI_DEFAULT_INSTRUMENTAL_GAIN_DB,
                seed=request.form.get("seed", "0"),
                out_dir=request.form.get("out_dir", DEFAULT_OUT_DIR),
                basename=request.form.get("basename", "Candy Dreams"),
                default_out_dir=DEFAULT_OUT_DIR,
                seed_vibe=request.form.get("seed_vibe", "any"),
                seed_vibes=SEED_VIBES,
                instrumental=instrumental,
                lyrics=lyrics,
                message=msg,
                short_message="Generation failed. See details for traceback.",
                details=msg,
                error=True,
                tracks=tracks,
                current_track=current_track,
                autoplay_url="",
                bpm=request.form.get("bpm", ""),
                presets=presets,
                models_ready=models_ready,
                model_state=model_state,
                model_message=model_message,
                training_data_root=str(TRAINING_DATA_ROOT),
                lora_adapters=cdmf_tracks.list_lora_adapters(),
                lora_name_or_path=request.form.get("lora_name_or_path", ""),
            )

    @bp.route("/prompt_lyrics/generate", methods=["POST"])
    def prompt_lyrics_generate():
        """
        Generate ACE-Step-friendly prompt tags and/or lyrics from a short song concept.

        Expected JSON body:
          {
            "concept": "short description of the song / scene / mood",
            "do_prompt": true/false,
            "do_lyrics": true/false,
            "existing_prompt": "current prompt text (optional)",
            "existing_lyrics": "current lyrics text (optional)",
            "target_seconds": 90.0  # optional, used as a length hint
          }

        Returns JSON:
          {
            "ok": true,
            "prompt": "...",   # present if do_prompt
            "lyrics": "...",   # present if do_lyrics
            "title": "..."     # short song title suitable for basename
          }
        """
        try:
            payload = request.get_json(silent=True) or {}
            concept = (payload.get("concept") or "").strip()
            do_prompt = bool(payload.get("do_prompt", True))
            do_lyrics = bool(payload.get("do_lyrics", True))

            existing_prompt = (payload.get("existing_prompt") or "").strip()
            existing_lyrics = (payload.get("existing_lyrics") or "").strip()

            # Length hints for the lyric generator.
            raw_target_seconds = payload.get("target_seconds", None)
            try:
                if raw_target_seconds is None:
                    target_seconds = float(UI_DEFAULT_TARGET_SECONDS)
                else:
                    target_seconds = max(1.0, float(raw_target_seconds))
            except Exception:
                target_seconds = float(UI_DEFAULT_TARGET_SECONDS)

            # Estimate desired lyric length from existing lyrics if present.
            # Otherwise, approximate from target_seconds.
            stripped_lines = [
                ln for ln in existing_lyrics.splitlines() if ln.strip()
            ]
            target_lines = len(stripped_lines)
            if target_lines <= 0:
                # Very rough heuristic: ~1 short stanza per 10–12 seconds.
                target_lines = max(4, min(32, int(target_seconds // 10) * 4))

            target_chars = max(0, len(existing_lyrics))

            if not concept:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": "concept is required to generate prompt/lyrics",
                        }
                    ),
                    400,
                )

            # Defer to a dedicated helper module so you can swap in a real small LLM
            # later without touching the Flask/blueprint plumbing.
            from lyrics_prompt_model import generate_prompt_and_lyrics

            result = generate_prompt_and_lyrics(
                concept=concept,
                want_prompt=do_prompt,
                want_lyrics=do_lyrics,
                existing_prompt=existing_prompt,
                existing_lyrics=existing_lyrics,
                target_seconds=target_seconds,
                target_lines=target_lines,
                target_chars=target_chars,
            )

            if not isinstance(result, dict):
                result = {}

            new_prompt = (result.get("prompt") or existing_prompt or "").strip()
            new_lyrics = (result.get("lyrics") or existing_lyrics or "").strip()
            new_title = (result.get("title") or "").strip()

            # Debug: log what we are about to send back to the browser
            print(
                "[CDMF] /prompt_lyrics/generate returning:",
                {
                    "do_prompt": do_prompt,
                    "do_lyrics": do_lyrics,
                    "prompt": new_prompt,
                    "lyrics": new_lyrics,
                    "title": new_title,
                },
                flush=True,
            )

            return jsonify(
                {
                    "ok": True,
                    # Always return the newly generated values; the front-end
                    # decides which ones to apply.
                    "prompt": new_prompt,
                    "lyrics": new_lyrics,
                    "title": new_title,
                }
            )
        except Exception as exc:
            print(
                "[AceForge] Error during prompt/lyrics generation:",
                exc,
                flush=True,
            )
            return jsonify({"ok": False, "error": str(exc)}), 500

    return bp

