# C:\AceForge\music_forge_ui.py

from __future__ import annotations

from pathlib import Path
import sys
import os

from flask import Flask

# ---------------------------------------------------------------------------
# Diffusers / ace-step compatibility shim (early)
# ---------------------------------------------------------------------------

try:
    import diffusers.loaders as _cdmf_dl  # type: ignore[import]

    if not hasattr(_cdmf_dl, "FromSingleFileMixin"):
        try:
            from diffusers.loaders.single_file import (  # type: ignore[import]
                FromSingleFileMixin as _CDMF_FSM,
            )
            _cdmf_dl.FromSingleFileMixin = _CDMF_FSM  # type: ignore[attr-defined]
            print(
                "[AceForge] Early-patched diffusers.loaders.FromSingleFileMixin "
                "for ace-step.",
                flush=True,
            )
        except Exception as _e:
            print(
                "[AceForge] WARNING: Could not expose "
                "diffusers.loaders.FromSingleFileMixin early: "
                f"{_e}",
                flush=True,
            )
except Exception as _e:
    print(
        "[AceForge] WARNING: Failed to import diffusers.loaders "
        f"for early compatibility patch: {_e}",
        flush=True,
    )

# ---------------------------------------------------------------------------
# ACE-Step generation + progress callback
# ---------------------------------------------------------------------------

from generate_ace import (
    generate_track_ace,
    DEFAULT_TARGET_SECONDS,
    DEFAULT_FADE_IN_SECONDS,
    DEFAULT_FADE_OUT_SECONDS,
    register_progress_callback,
)

from ace_model_setup import ace_models_present
from cdmf_template import HTML
import cdmf_paths
import cdmf_state
from cdmf_tracks import create_tracks_blueprint
from cdmf_models import create_models_blueprint
from cdmf_mufun import create_mufun_blueprint
from cdmf_training import create_training_blueprint
from cdmf_generation import create_generation_blueprint
from cdmf_lyrics import create_lyrics_blueprint

# Flask app
app = Flask(__name__)

# Wire ACE-Step's progress callback into our shared state
register_progress_callback(cdmf_state.ace_progress_callback)

# UI defaults (mirroring previous inline constants)
UI_DEFAULTS = {
    "target_seconds": int(DEFAULT_TARGET_SECONDS),
    "fade_in": DEFAULT_FADE_IN_SECONDS,
    "fade_out": DEFAULT_FADE_OUT_SECONDS,
    "steps": 55,
    "guidance_scale": 6.0,
}

# Initialize model status before first page render
cdmf_state.init_model_status()

# Register blueprints (no URL prefixes; routes match original paths)
app.register_blueprint(create_tracks_blueprint())
app.register_blueprint(create_models_blueprint())
app.register_blueprint(create_mufun_blueprint())
app.register_blueprint(create_training_blueprint())
app.register_blueprint(
    create_generation_blueprint(
        html_template=HTML,
        ui_defaults=UI_DEFAULTS,
        generate_track_ace=generate_track_ace,
    )
)
app.register_blueprint(create_lyrics_blueprint())



# ---------------------------------------------------------------------------
# Health + loading routes (simple, kept local)
# ---------------------------------------------------------------------------

@app.route("/healthz", methods=["GET"])
def healthz():
    """
    Simple health-check endpoint so the local loading page knows when
    the Flask server is ready.
    """
    return (
        "ok",
        200,
        {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.route("/loading", methods=["GET"])
def loading_page():
    """
    Simple loading screen that polls /healthz and redirects to the main UI
    once the server is responding.
    """
    return app.send_static_file("loading.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    from waitress import serve
    import webbrowser

    # Do not download the ACE-Step model here. Instead, let the UI trigger
    # a background download so the server can start quickly.
    if ace_models_present():
        print("[CDMF] ACE-Step model already present; skipping download.", flush=True)
        with cdmf_state.MODEL_LOCK:
            cdmf_state.MODEL_STATUS["state"] = "ready"
            cdmf_state.MODEL_STATUS["message"] = "ACE-Step model is present."
    else:
        print(
            "[CDMF] ACE-Step model is not downloaded yet.\n"
            "       You can download it from within the UI using the "
            '"Download Models" button before generating music.',
            flush=True,
        )
        with cdmf_state.MODEL_LOCK:
            if cdmf_state.MODEL_STATUS["state"] == "unknown":
                cdmf_state.MODEL_STATUS["state"] = "absent"
                cdmf_state.MODEL_STATUS["message"] = (
                    "ACE-Step model has not been downloaded yet."
                )

    print(
        "Starting AceForge (ACE-Step Edition v0.1) "
        "on http://127.0.0.1:5056/ ...",
        flush=True,
    )

    is_frozen = getattr(sys, "frozen", False)

    # macOS-focused: Use webbrowser to open loading page or main URL
    if is_frozen:
        try:
            static_root = Path(app.static_folder or (cdmf_paths.APP_DIR / "static"))
            loader_path = static_root / "loading.html"

            if loader_path.exists():
                try:
                    webbrowser.open(loader_path.as_uri())
                except Exception:
                    webbrowser.open("http://127.0.0.1:5056/")
            else:
                webbrowser.open("http://127.0.0.1:5056/")
        except Exception as e:
            print(
                f"[AceForge] Failed to open browser automatically: {e}",
                flush=True,
            )
            try:
                webbrowser.open("http://127.0.0.1:5056/")
            except Exception:
                pass

    # Start Flask (blocking)
    serve(app, host="127.0.0.1", port=5056)


if __name__ == "__main__":
    main()
