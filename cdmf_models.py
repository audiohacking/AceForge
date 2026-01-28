# C:\AceForge\cdmf_models.py

from __future__ import annotations

import threading
from flask import Blueprint, jsonify, request

from ace_model_setup import ensure_ace_models, ace_models_present
import cdmf_state
import cdmf_paths


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

    @bp.route("/models/folder", methods=["GET"])
    def models_folder_get():
        """
        Get the current models folder configuration.
        """
        models_folder = str(cdmf_paths.get_models_folder())
        return jsonify({"ok": True, "models_folder": models_folder})

    @bp.route("/models/folder", methods=["POST"])
    def models_folder_set():
        """
        Set the models folder path.
        """
        data = request.get_json() or {}
        new_path = data.get("path", "").strip()
        
        if not new_path:
            return jsonify({"ok": False, "error": "Path cannot be empty"}), 400
        
        success = cdmf_paths.set_models_folder(new_path)
        if success:
            return jsonify({
                "ok": True, 
                "models_folder": str(cdmf_paths.get_models_folder()),
                "message": "Models folder updated successfully. Restart the application for changes to take full effect."
            })
        else:
            return jsonify({
                "ok": False, 
                "error": "Failed to set models folder. Check that the path is valid and writable."
            }), 400

    # Stem splitting (Demucs) model status and ensure - only if stem splitting is available
    try:
        from cdmf_stem_splitting import stem_split_models_present, ensure_stem_split_models

        def _download_stem_split_models_worker() -> None:
            """Background worker to pre-download Demucs model."""
            cdmf_state.reset_progress()
            with cdmf_state.PROGRESS_LOCK:
                cdmf_state.GENERATION_PROGRESS["stage"] = "stem_split_model_download"
                cdmf_state.GENERATION_PROGRESS["done"] = False
                cdmf_state.GENERATION_PROGRESS["error"] = False
                cdmf_state.GENERATION_PROGRESS["current"] = 0.0
                cdmf_state.GENERATION_PROGRESS["total"] = 1.0
            try:
                def _progress(f: float) -> None:
                    with cdmf_state.PROGRESS_LOCK:
                        cdmf_state.GENERATION_PROGRESS["current"] = max(0.0, min(1.0, f))
                ensure_stem_split_models(progress_cb=_progress)
                with cdmf_state.STEM_SPLIT_LOCK:
                    cdmf_state.STEM_SPLIT_STATUS["state"] = "ready"
                    cdmf_state.STEM_SPLIT_STATUS["message"] = "Demucs model is present."
                with cdmf_state.PROGRESS_LOCK:
                    cdmf_state.GENERATION_PROGRESS["current"] = 1.0
                    cdmf_state.GENERATION_PROGRESS["stage"] = "done"
                    cdmf_state.GENERATION_PROGRESS["done"] = True
                    cdmf_state.GENERATION_PROGRESS["error"] = False
            except Exception as exc:
                with cdmf_state.STEM_SPLIT_LOCK:
                    cdmf_state.STEM_SPLIT_STATUS["state"] = "error"
                    cdmf_state.STEM_SPLIT_STATUS["message"] = f"Failed to download Demucs model: {exc}"
                with cdmf_state.PROGRESS_LOCK:
                    cdmf_state.GENERATION_PROGRESS["stage"] = "error"
                    cdmf_state.GENERATION_PROGRESS["done"] = True
                    cdmf_state.GENERATION_PROGRESS["error"] = True

        @bp.route("/models/stem_split/status", methods=["GET"])
        def models_stem_split_status():
            """Report whether the Demucs (stem splitting) model is available."""
            with cdmf_state.STEM_SPLIT_LOCK:
                state = cdmf_state.STEM_SPLIT_STATUS["state"]
            if state not in ("downloading", "ready"):
                if stem_split_models_present():
                    with cdmf_state.STEM_SPLIT_LOCK:
                        cdmf_state.STEM_SPLIT_STATUS["state"] = "ready"
                        cdmf_state.STEM_SPLIT_STATUS["message"] = "Demucs model is present."
                else:
                    with cdmf_state.STEM_SPLIT_LOCK:
                        if cdmf_state.STEM_SPLIT_STATUS["state"] == "unknown":
                            cdmf_state.STEM_SPLIT_STATUS["state"] = "absent"
                            cdmf_state.STEM_SPLIT_STATUS["message"] = (
                                "Demucs model has not been downloaded yet."
                            )
            with cdmf_state.STEM_SPLIT_LOCK:
                state = cdmf_state.STEM_SPLIT_STATUS["state"]
                message = cdmf_state.STEM_SPLIT_STATUS["message"]
            return jsonify({"ok": True, "ready": state == "ready", "state": state, "message": message})

        @bp.route("/models/stem_split/ensure", methods=["POST"])
        def models_stem_split_ensure():
            """Trigger a background download of the Demucs model if not present."""
            with cdmf_state.STEM_SPLIT_LOCK:
                state = cdmf_state.STEM_SPLIT_STATUS["state"]
            if state == "ready":
                return jsonify({"ok": True, "already_ready": True})
            if state == "downloading":
                return jsonify({"ok": True, "already_downloading": True})
            if stem_split_models_present():
                with cdmf_state.STEM_SPLIT_LOCK:
                    cdmf_state.STEM_SPLIT_STATUS["state"] = "ready"
                    cdmf_state.STEM_SPLIT_STATUS["message"] = "Demucs model is present."
                return jsonify({"ok": True, "already_ready": True})
            with cdmf_state.STEM_SPLIT_LOCK:
                cdmf_state.STEM_SPLIT_STATUS["state"] = "downloading"
                cdmf_state.STEM_SPLIT_STATUS["message"] = (
                    "Downloading Demucs model. This may take several minutes (first use only)."
                )
            import threading
            threading.Thread(target=_download_stem_split_models_worker, daemon=True).start()
            return jsonify({"ok": True, "started": True})
    except ImportError:
        pass

    # MIDI generation (basic-pitch) model status and ensure - only if MIDI generation is available
    try:
        from midi_model_setup import basic_pitch_models_present, ensure_basic_pitch_models
        import cdmf_state

        def _download_midi_models_worker() -> None:
            """Background worker to pre-download basic-pitch model."""
            cdmf_state.reset_progress()
            with cdmf_state.PROGRESS_LOCK:
                cdmf_state.GENERATION_PROGRESS["stage"] = "midi_model_download"
                cdmf_state.GENERATION_PROGRESS["done"] = False
                cdmf_state.GENERATION_PROGRESS["error"] = False
                cdmf_state.GENERATION_PROGRESS["current"] = 0.0
                cdmf_state.GENERATION_PROGRESS["total"] = 1.0
            try:
                def _progress(f: float) -> None:
                    with cdmf_state.PROGRESS_LOCK:
                        cdmf_state.GENERATION_PROGRESS["current"] = max(0.0, min(1.0, f))
                ensure_basic_pitch_models(progress_cb=_progress)
                with cdmf_state.MIDI_GEN_LOCK:
                    cdmf_state.MIDI_GEN_STATUS["state"] = "ready"
                    cdmf_state.MIDI_GEN_STATUS["message"] = "basic-pitch model is present."
                with cdmf_state.PROGRESS_LOCK:
                    cdmf_state.GENERATION_PROGRESS["current"] = 1.0
                    cdmf_state.GENERATION_PROGRESS["stage"] = "done"
                    cdmf_state.GENERATION_PROGRESS["done"] = True
                    cdmf_state.GENERATION_PROGRESS["error"] = False
            except Exception as exc:
                with cdmf_state.MIDI_GEN_LOCK:
                    cdmf_state.MIDI_GEN_STATUS["state"] = "error"
                    cdmf_state.MIDI_GEN_STATUS["message"] = f"Failed to download basic-pitch model: {exc}"
                with cdmf_state.PROGRESS_LOCK:
                    cdmf_state.GENERATION_PROGRESS["stage"] = "error"
                    cdmf_state.GENERATION_PROGRESS["done"] = True
                    cdmf_state.GENERATION_PROGRESS["error"] = True

        @bp.route("/models/midi_gen/status", methods=["GET"])
        def models_midi_gen_status():
            """Report whether the basic-pitch (MIDI generation) model is available."""
            with cdmf_state.MIDI_GEN_LOCK:
                state = cdmf_state.MIDI_GEN_STATUS["state"]
            if state not in ("downloading", "ready"):
                if basic_pitch_models_present():
                    with cdmf_state.MIDI_GEN_LOCK:
                        cdmf_state.MIDI_GEN_STATUS["state"] = "ready"
                        cdmf_state.MIDI_GEN_STATUS["message"] = "basic-pitch model is present."
                else:
                    with cdmf_state.MIDI_GEN_LOCK:
                        if cdmf_state.MIDI_GEN_STATUS["state"] == "unknown":
                            cdmf_state.MIDI_GEN_STATUS["state"] = "absent"
                            cdmf_state.MIDI_GEN_STATUS["message"] = (
                                "basic-pitch model has not been downloaded yet."
                            )
            with cdmf_state.MIDI_GEN_LOCK:
                state = cdmf_state.MIDI_GEN_STATUS["state"]
                message = cdmf_state.MIDI_GEN_STATUS["message"]
            return jsonify({"ok": True, "ready": state == "ready", "state": state, "message": message})

        @bp.route("/models/midi_gen/ensure", methods=["POST"])
        def models_midi_gen_ensure():
            """Trigger a background download of the basic-pitch model if not present."""
            with cdmf_state.MIDI_GEN_LOCK:
                state = cdmf_state.MIDI_GEN_STATUS["state"]
            if state == "ready":
                return jsonify({"ok": True, "already_ready": True})
            if state == "downloading":
                return jsonify({"ok": True, "already_downloading": True})
            if basic_pitch_models_present():
                with cdmf_state.MIDI_GEN_LOCK:
                    cdmf_state.MIDI_GEN_STATUS["state"] = "ready"
                    cdmf_state.MIDI_GEN_STATUS["message"] = "basic-pitch model is present."
                return jsonify({"ok": True, "already_ready": True})
            with cdmf_state.MIDI_GEN_LOCK:
                cdmf_state.MIDI_GEN_STATUS["state"] = "downloading"
                cdmf_state.MIDI_GEN_STATUS["message"] = (
                    "Downloading basic-pitch model. This may take several minutes (first use only)."
                )
            import threading
            threading.Thread(target=_download_midi_models_worker, daemon=True).start()
            return jsonify({"ok": True, "started": True})
    except ImportError:
        pass

    return bp
