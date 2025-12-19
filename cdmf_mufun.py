# C:\AceForge\cdmf_mufun.py

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, Any, List

from flask import Blueprint, request, jsonify

from mufun_model_setup import (
    ensure_mufun_model,
    mufun_model_present,
    mufun_analyze_file,
    merge_base_and_mufun_tags,
)
from cdmf_paths import TRAINING_DATA_ROOT
import cdmf_state


def _download_mufun_worker() -> None:
    """
    Background worker that runs ensure_mufun_model() so the Flask request
    thread can return immediately while the large download proceeds.
    """

    def _progress_cb(fraction: float) -> None:
        try:
            frac = max(0.0, min(1.0, float(fraction)))
        except Exception:
            frac = 0.0
        with cdmf_state.MUFUN_LOCK:
            cdmf_state.MUFUN_STATUS["state"] = "downloading"
            cdmf_state.MUFUN_STATUS["message"] = (
                "Downloading MuFun-ACEStep model… "
                "check the console window for detailed progress."
            )

    try:
        ensure_mufun_model(progress_cb=_progress_cb)
        with cdmf_state.MUFUN_LOCK:
            cdmf_state.MUFUN_STATUS["state"] = "ready"
            cdmf_state.MUFUN_STATUS["message"] = "MuFun-ACEStep model is present on disk."
    except Exception as exc:
        print("[CDMF] Failed to download MuFun-ACEStep model:", exc, flush=True)
        with cdmf_state.MUFUN_LOCK:
            cdmf_state.MUFUN_STATUS["state"] = "error"
            cdmf_state.MUFUN_STATUS["message"] = (
                f"Failed to download MuFun-ACEStep model: {exc}"
            )


def create_mufun_blueprint() -> Blueprint:
    bp = Blueprint("cdmf_mufun", __name__)

    @bp.route("/mufun/status", methods=["GET"])
    def mufun_status():
        """
        Report whether the MuFun-ACEStep analysis model is available, and the
        current high-level state of any in-progress download.
        """
        with cdmf_state.MUFUN_LOCK:
            state = cdmf_state.MUFUN_STATUS.get("state", "unknown")
            message = cdmf_state.MUFUN_STATUS.get("message", "")

        if state == "unknown":
            if mufun_model_present():
                with cdmf_state.MUFUN_LOCK:
                    cdmf_state.MUFUN_STATUS["state"] = "ready"
                    cdmf_state.MUFUN_STATUS["message"] = (
                        "MuFun-ACEStep model is present on disk."
                    )
                    state = cdmf_state.MUFUN_STATUS["state"]
                    message = cdmf_state.MUFUN_STATUS["message"]
            else:
                with cdmf_state.MUFUN_LOCK:
                    cdmf_state.MUFUN_STATUS["state"] = "absent"
                    cdmf_state.MUFUN_STATUS["message"] = (
                        "MuFun-ACEStep model has not been downloaded yet."
                    )
                    state = cdmf_state.MUFUN_STATUS["state"]
                    message = cdmf_state.MUFUN_STATUS["message"]

        return jsonify({"ok": True, "state": state, "message": message})

    @bp.route("/mufun/ensure", methods=["POST"])
    def mufun_ensure():
        """
        Trigger a background download of the MuFun-ACEStep analysis model
        if it is not already present.
        """
        with cdmf_state.MUFUN_LOCK:
            state = cdmf_state.MUFUN_STATUS.get("state", "unknown")

            if state == "ready":
                return jsonify({"ok": True, "already_ready": True})

            if state == "downloading":
                return jsonify({"ok": True, "already_downloading": True})

            if mufun_model_present():
                cdmf_state.MUFUN_STATUS["state"] = "ready"
                cdmf_state.MUFUN_STATUS["message"] = (
                    "MuFun-ACEStep model is present on disk."
                )
                return jsonify({"ok": True, "already_ready": True})

            cdmf_state.MUFUN_STATUS["state"] = "downloading"
            cdmf_state.MUFUN_STATUS["message"] = (
                "Downloading MuFun-ACEStep model from Hugging Face. "
                "This may take several minutes."
            )

        threading.Thread(target=_download_mufun_worker, daemon=True).start()
        return jsonify({"ok": True, "started": True})

    @bp.route("/mufun/analyze_dataset", methods=["POST"])
    def mufun_analyze_dataset():
        """Run MuFun-ACEStep over all .mp3 / .wav files in a dataset folder.

        Expected JSON body:
          {
            "dataset_path": "C:\\path\\to\\folder",
            "overwrite": false,
            "dataset_base_prompt": "16-bit SNES-style chiptune, retro RPG BGM, looping instrumental, no vocals",
            "instrumental_only": true
          }
        """
        payload = request.get_json(silent=True) or {}
        dataset_path = (payload.get("dataset_path") or "").strip()
        overwrite = bool(payload.get("overwrite"))
        dataset_base_prompt = (payload.get("dataset_base_prompt") or "").strip()
        instrumental_only = bool(payload.get("instrumental_only"))

        if not dataset_path:
            return jsonify({"ok": False, "error": "dataset_path is required"}), 400

        ds_rel = Path(dataset_path)

        if ds_rel.is_absolute():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            "dataset_path must be a folder name / relative path under "
                            "the training_datasets directory, not an absolute path."
                        ),
                    }
                ),
                400,
            )

        ds_dir = (TRAINING_DATA_ROOT / ds_rel).resolve()

        try:
            training_root_real = TRAINING_DATA_ROOT.resolve()
        except Exception:
            training_root_real = TRAINING_DATA_ROOT

        if not str(ds_dir).startswith(str(training_root_real)):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            "Dataset folder must live under the "
                            "training_datasets directory."
                        ),
                    }
                ),
                400,
            )

        if not ds_dir.is_dir():
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": (
                            "Dataset folder does not exist or is not a directory: "
                            f"{ds_dir}"
                        ),
                    }
                ),
                400,
            )

        try:
            audio_files = sorted(
                [
                    p
                    for p in ds_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in (".mp3", ".wav")
                ],
                key=lambda p: p.name.lower(),
            )
        except Exception as exc:
            return (
                jsonify(
                    {"ok": False, "error": f"Failed to enumerate dataset folder: {exc}"}
                ),
                500,
            )

        if not audio_files:
            return jsonify(
                {
                    "ok": True,
                    "summary": {
                        "total_files": 0,
                        "processed": 0,
                        "skipped_existing": 0,
                        "errors": 0,
                    },
                    "results_text": "No .mp3 or .wav files found in dataset folder.",
                    "files": [],
                }
            )

        summary = {
            "total_files": len(audio_files),
            "processed": 0,
            "skipped_existing": 0,
            "errors": 0,
        }
        file_results: List[Dict[str, str]] = []
        lines: List[str] = []

        for audio_path in audio_files:
            stem = audio_path.stem
            prompt_path = ds_dir / f"{stem}_prompt.txt"
            lyrics_path = ds_dir / f"{stem}_lyrics.txt"

            rec: Dict[str, str] = {
                "file": audio_path.name,
                "prompt_file": str(prompt_path),
                "lyrics_file": str(lyrics_path),
                "status": "",
                "error": "",
            }

            if prompt_path.exists() and lyrics_path.exists() and not overwrite:
                summary["skipped_existing"] += 1
                rec["status"] = "skipped_existing"
                lines.append(
                    f"[SKIP] {audio_path.name} (prompt + lyrics already exist; not overwriting)."
                )
                file_results.append(rec)
                continue

            try:
                # If instrumental_only is True, force MuFun's lyrics to [inst]
                result = mufun_analyze_file(
                    str(audio_path), force_instrumental=instrumental_only
                )
            except Exception as exc:
                summary["errors"] += 1
                rec["status"] = "error"
                rec["error"] = str(exc)
                lines.append(f"[ERROR] {audio_path.name}: {exc}")
                file_results.append(rec)
                continue

            prompt_text = ""
            lyrics_text = ""
            raw_text = ""

            if isinstance(result, dict):
                prompt_text = str(result.get("prompt", "") or "").strip()
                lyrics_text = str(result.get("lyrics", "") or "").strip()
                raw_text = str(result.get("raw_text", "") or "").strip()
            else:
                prompt_text = ""
                lyrics_text = ""
                raw_text = str(result) if result is not None else ""

            # If MuFun didn't give us either prompt or lyrics, treat as an error
            if not prompt_text and not lyrics_text:
                summary["errors"] += 1
                rec["status"] = "error"
                rec["error"] = (
                    "MuFun-ACEStep did not return 'prompt' or 'lyrics' fields. "
                    "Raw response was captured in the log."
                )
                lines.append(
                    f"[ERROR] {audio_path.name}: MuFun did not return prompt/lyrics.\n"
                    f"  Raw response: {raw_text[:200]}..."
                )
                file_results.append(rec)
                continue

            # If the user marked this dataset as instrumental-only, override
            # any lyrics with [inst].
            if instrumental_only:
                lyrics_text = "[inst]"

            # Merge base prompt with MuFun tags.
            final_prompt = prompt_text
            if dataset_base_prompt:
                if final_prompt:
                    final_prompt = merge_base_and_mufun_tags(
                        dataset_base_prompt, final_prompt
                    )
                else:
                    final_prompt = dataset_base_prompt

            try:
                if final_prompt and (overwrite or not prompt_path.exists()):
                    prompt_path.write_text(final_prompt + "\n", encoding="utf-8")

                if lyrics_text and (overwrite or not lyrics_path.exists()):
                    lyrics_path.write_text(lyrics_text + "\n", encoding="utf-8")
            except Exception as exc:
                summary["errors"] += 1
                rec["status"] = "error"
                rec["error"] = f"Failed to write prompt/lyrics files: {exc}"
                lines.append(
                    f"[ERROR] {audio_path.name}: Failed to write prompt/lyrics files: {exc}"
                )
                file_results.append(rec)
                continue

            summary["processed"] += 1
            rec["status"] = "processed"

            lines.append(f"[OK] {audio_path.name}")
            if final_prompt:
                lines.append(f"  prompt: {final_prompt}")
            if lyrics_text:
                preview_lines = [ln for ln in lyrics_text.splitlines() if ln.strip() ]
                if preview_lines:
                    preview = preview_lines[:3]
                    lines.append("  lyrics (preview):")
                    for pl in preview:
                        lines.append(f"    {pl}")
            lines.append("")

            file_results.append(rec)

        results_text = "\n".join(lines).rstrip()

        return jsonify(
            {
                "ok": True,
                "summary": summary,
                "results_text": results_text,
                "files": file_results,
            }
        )

    return bp
