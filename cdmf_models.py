# C:\AceForge\cdmf_models.py

from __future__ import annotations

import threading
from flask import Blueprint, jsonify

from ace_model_setup import ensure_ace_models, ace_models_present
import cdmf_state


def _download_models_worker() -> None:
    """
    Background worker that runs ensure_ace_models() so the Flask request
    thread can return immediately while the large download proceeds.
    """
    # Reset and announce that we're downloading the ACE model.
    cdmf_state.reset_progress()
    with cdmf_state.PROGRESS_LOCK:
        cdmf_state.GENERATION_PROGRESS["stage"] = "ace_model_download"
        cdmf_state.GENERATION_PROGRESS["done"] = False
        cdmf_state.GENERATION_PROGRESS["error"] = False
        cdmf_state.GENERATION_PROGRESS["current"] = 0.0
        cdmf_state.GENERATION_PROGRESS["total"] = 1.0

    try:
        ensure_ace_models(progress_cb=cdmf_state.model_download_progress_cb)
        with cdmf_state.MODEL_LOCK:
            cdmf_state.MODEL_STATUS["state"] = "ready"
            cdmf_state.MODEL_STATUS["message"] = "ACE-Step model is present."

        # Snap to 100% on success.
        with cdmf_state.PROGRESS_LOCK:
            cdmf_state.GENERATION_PROGRESS["current"] = 1.0
            cdmf_state.GENERATION_PROGRESS["total"] = 1.0
            cdmf_state.GENERATION_PROGRESS["stage"] = "done"
            cdmf_state.GENERATION_PROGRESS["done"] = True
            cdmf_state.GENERATION_PROGRESS["error"] = False
    except Exception as exc:
        with cdmf_state.MODEL_LOCK:
            cdmf_state.MODEL_STATUS["state"] = "error"
            cdmf_state.MODEL_STATUS["message"] = f"Failed to download ACE-Step model: {exc}"

        # Mark the progress bar as errored.
        with cdmf_state.PROGRESS_LOCK:
            cdmf_state.GENERATION_PROGRESS["stage"] = "error"
            cdmf_state.GENERATION_PROGRESS["done"] = True
            cdmf_state.GENERATION_PROGRESS["error"] = True


def create_models_blueprint() -> Blueprint:
    bp = Blueprint("cdmf_models", __name__)

    @bp.route("/models/status", methods=["GET"])
    def models_status():
        """
        Report whether the ACE-Step model is available, and the current
        high-level state of any in-progress download.
        """
        # If we're not actively downloading or marked ready, re-sync from disk.
        with cdmf_state.MODEL_LOCK:
            state = cdmf_state.MODEL_STATUS["state"]

        if state not in ("downloading", "ready"):
            if ace_models_present():
                with cdmf_state.MODEL_LOCK:
                    cdmf_state.MODEL_STATUS["state"] = "ready"
                    cdmf_state.MODEL_STATUS["message"] = "ACE-Step model is present."
            else:
                with cdmf_state.MODEL_LOCK:
                    if cdmf_state.MODEL_STATUS["state"] == "unknown":
                        cdmf_state.MODEL_STATUS["state"] = "absent"
                        cdmf_state.MODEL_STATUS["message"] = (
                            "ACE-Step model has not been downloaded yet."
                        )

        with cdmf_state.MODEL_LOCK:
            state = cdmf_state.MODEL_STATUS["state"]
            message = cdmf_state.MODEL_STATUS["message"]

        ready = state == "ready"
        return jsonify({"ok": True, "ready": ready, "state": state, "message": message})

    @bp.route("/models/ensure", methods=["POST"])
    def models_ensure():
        """
        Trigger a background download of the ACE-Step model if it isn't present.
        This endpoint returns quickly; the browser can poll /models/status for
        updates while the download runs.
        """
        with cdmf_state.MODEL_LOCK:
            state = cdmf_state.MODEL_STATUS["state"]

            # If we're already ready, nothing to do.
            if state == "ready":
                return jsonify({"ok": True, "already_ready": True})

            # If a download is already in progress, just acknowledge it.
            if state == "downloading":
                return jsonify({"ok": True, "already_downloading": True})

            # If the files exist on disk, flip to ready immediately.
            if ace_models_present():
                cdmf_state.MODEL_STATUS["state"] = "ready"
                cdmf_state.MODEL_STATUS["message"] = "ACE-Step model is present."
                return jsonify({"ok": True, "already_ready": True})

            # Otherwise, mark as downloading and start the worker thread.
            cdmf_state.MODEL_STATUS["state"] = "downloading"
            cdmf_state.MODEL_STATUS["message"] = (
                "Downloading ACE-Step model from Hugging Face. This may take several minutes."
            )

        threading.Thread(target=_download_models_worker, daemon=True).start()
        return jsonify({"ok": True, "started": True})

    return bp
