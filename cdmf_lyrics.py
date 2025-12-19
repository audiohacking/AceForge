# C:\AceForge\cdmf_lyrics.py  (new file)

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from flask import Blueprint, jsonify, request

from lyrics_model_setup import (
    lyrics_model_present,
    ensure_lyrics_model,
    generate_prompt_and_lyrics,
)

# Simple in-process status tracking (similar spirit to MuFun)
_LYRICS_STATUS_LOCK = threading.Lock()
_LYRICS_STATUS: Dict[str, Any] = {
    "state": "unknown",  # "unknown" | "absent" | "downloading" | "ready" | "error"
    "message": "",
}

def _set_lyrics_status(state: str, message: str = "") -> None:
    with _LYRICS_STATUS_LOCK:
        _LYRICS_STATUS["state"] = state
        _LYRICS_STATUS["message"] = message


def _get_lyrics_status() -> Dict[str, Any]:
    with _LYRICS_STATUS_LOCK:
        return dict(_LYRICS_STATUS)


def _download_lyrics_worker() -> None:
    """
    Background worker: actually downloads the HF model using ensure_lyrics_model().
    """
    def _progress_cb(_fraction: float) -> None:
        # We don't get nice granular progress from HF anyway, just signal "downloading".
        _set_lyrics_status(
            "downloading",
            "Downloading lyrics LLM… check the console window for detailed progress.",
        )

    try:
        ensure_lyrics_model(progress_cb=_progress_cb)
        _set_lyrics_status(
            "ready",
            "Lyrics LLM is present on disk.",
        )
    except Exception as exc:
        print("[CDMF] Failed to download lyrics LLM:", exc, flush=True)
        _set_lyrics_status(
            "error",
            f"Failed to download lyrics LLM: {exc}",
        )


def create_lyrics_blueprint() -> Blueprint:
    bp = Blueprint("cdmf_lyrics", __name__)

    @bp.route("/lyrics/status", methods=["GET"])
    def lyrics_status():
        """
        Report whether the lyrics LLM is available, and the current
        high-level state of any in-progress download.
        """
        status = _get_lyrics_status()
        state = status.get("state", "unknown")

        if state == "unknown":
            if lyrics_model_present():
                _set_lyrics_status("ready", "Lyrics LLM is present on disk.")
            else:
                _set_lyrics_status(
                    "absent",
                    "Lyrics LLM has not been downloaded yet.",
                )
            status = _get_lyrics_status()

        return jsonify({"ok": True, **status})

    @bp.route("/lyrics/ensure", methods=["POST"])
    def lyrics_ensure():
        """
        Trigger a background download of the lyrics LLM if it is not ready.
        """
        status = _get_lyrics_status()
        state = status.get("state", "unknown")

        if state == "ready":
            return jsonify({"ok": True, "already_ready": True})

        if state == "downloading":
            return jsonify({"ok": True, "already_downloading": True})

        if lyrics_model_present():
            _set_lyrics_status("ready", "Lyrics LLM is present on disk.")
            return jsonify({"ok": True, "already_ready": True})

        # Kick off download
        _set_lyrics_status(
            "downloading",
            "Downloading lyrics LLM from Hugging Face. This may take several minutes.",
        )
        threading.Thread(target=_download_lyrics_worker, daemon=True).start()
        return jsonify({"ok": True, "started": True})

    @bp.route("/lyrics/generate", methods=["POST"])
    def lyrics_generate():
        """
        Generate ACE-Step-ready tags and/or lyrics from a short concept.

        Expected JSON body:
          {
            "concept": "short freeform concept text",
            "target_seconds": 90,
            "bpm": 0 or null,
            "want_prompt": true,
            "want_lyrics": true
          }
        """
        payload = request.get_json(silent=True) or {}

        concept = (payload.get("concept") or "").strip()
        if not concept:
            return jsonify(
                {"ok": False, "error": "concept is required"}
            ), 400

        want_prompt = bool(payload.get("want_prompt", True))
        want_lyrics = bool(payload.get("want_lyrics", True))

        if not want_prompt and not want_lyrics:
            return jsonify(
                {
                    "ok": False,
                    "error": "You must request at least prompt or lyrics.",
                }
            ), 400

        target_seconds_raw: Any = payload.get("target_seconds", 90)
        try:
            target_seconds = float(target_seconds_raw)
        except Exception:
            target_seconds = 90.0

        bpm_raw: Any = payload.get("bpm", None)
        bpm: Optional[float]
        if bpm_raw is None or bpm_raw == "":
            bpm = None
        else:
            try:
                bpm = float(bpm_raw)
            except Exception:
                bpm = None

        # Ensure the model is actually present
        if not lyrics_model_present():
            status = _get_lyrics_status()
            return jsonify(
                {
                    "ok": False,
                    "error": "Lyrics LLM is not downloaded yet.",
                    "needs_download": True,
                    "state": status.get("state", "absent"),
                    "message": status.get("message", ""),
                }
            ), 400

        try:
            result = generate_prompt_and_lyrics(
                concept=concept,
                target_seconds=target_seconds,
                bpm=bpm,
                want_prompt=want_prompt,
                want_lyrics=want_lyrics,
            )
        except Exception as exc:
            print("[CDMF] lyrics_generate error:", exc, flush=True)
            return jsonify(
                {
                    "ok": False,
                    "error": f"Lyrics generation failed: {exc}",
                }
            ), 500

        return jsonify(
            {
                "ok": True,
                "prompt": result.get("prompt", ""),
                "lyrics": result.get("lyrics", ""),
            }
        )

    return bp
