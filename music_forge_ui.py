# C:\AceForge\music_forge_ui.py

from __future__ import annotations

from pathlib import Path
import sys
import os
import threading
import queue
import logging
import time
from io import StringIO

from flask import Flask, Response, request

# ---------------------------------------------------------------------------
# Diffusers / ace-step compatibility shim (early)
# ---------------------------------------------------------------------------

try:
    import diffusers.loaders as _cdmf_dl  # type: ignore[import]
    
    # Force the lazy module to fully initialize if it's a LazyModule
    # This ensures our patches stick in frozen PyInstaller apps
    # Accessing __dict__ triggers the lazy loading mechanism (assignment to trigger side effect)
    _force_lazy_init = _cdmf_dl.__dict__

    # Patch FromSingleFileMixin if not available at top level
    if not hasattr(_cdmf_dl, "FromSingleFileMixin"):
        try:
            from diffusers.loaders.single_file import (  # type: ignore[import]
                FromSingleFileMixin as _CDMF_FSM,
            )
            # Patch both the module and sys.modules to handle lazy loading
            _cdmf_dl.FromSingleFileMixin = _CDMF_FSM  # type: ignore[attr-defined]
            if 'diffusers.loaders' in sys.modules:
                sys.modules['diffusers.loaders'].FromSingleFileMixin = _CDMF_FSM  # type: ignore[attr-defined]
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
    
    # Patch IP Adapter mixins if not available at top level (critical for frozen apps)
    if not hasattr(_cdmf_dl, "SD3IPAdapterMixin"):
        try:
            from diffusers.loaders.ip_adapter import (  # type: ignore[import]
                IPAdapterMixin as _CDMF_IPAM,
                SD3IPAdapterMixin as _CDMF_SD3IPAM,
                FluxIPAdapterMixin as _CDMF_FLUXIPAM,
            )
            # Patch both the module and sys.modules to handle lazy loading
            _cdmf_dl.IPAdapterMixin = _CDMF_IPAM  # type: ignore[attr-defined]
            _cdmf_dl.SD3IPAdapterMixin = _CDMF_SD3IPAM  # type: ignore[attr-defined]
            _cdmf_dl.FluxIPAdapterMixin = _CDMF_FLUXIPAM  # type: ignore[attr-defined]
            if 'diffusers.loaders' in sys.modules:
                sys.modules['diffusers.loaders'].IPAdapterMixin = _CDMF_IPAM  # type: ignore[attr-defined]
                sys.modules['diffusers.loaders'].SD3IPAdapterMixin = _CDMF_SD3IPAM  # type: ignore[attr-defined]
                sys.modules['diffusers.loaders'].FluxIPAdapterMixin = _CDMF_FLUXIPAM  # type: ignore[attr-defined]
            print(
                "[AceForge] Early-patched diffusers.loaders IP Adapter mixins "
                "(IPAdapterMixin, SD3IPAdapterMixin, FluxIPAdapterMixin) for ace-step.",
                flush=True,
            )
        except Exception as _e:
            print(
                "[AceForge] WARNING: Could not expose "
                "diffusers.loaders IP Adapter mixins early: "
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

# ---------------------------------------------------------------------------
# Log streaming infrastructure
# ---------------------------------------------------------------------------

# Queue to hold log messages for streaming to browser
LOG_QUEUE = queue.Queue(maxsize=1000)

class QueueHandler(logging.Handler):
    """Custom logging handler that puts messages into a queue for streaming"""
    def emit(self, record):
        try:
            msg = self.format(record)
            # Try to add to queue, drop if full
            try:
                LOG_QUEUE.put_nowait(msg)
            except queue.Full:
                pass  # Drop message if queue is full
        except Exception:
            self.handleError(record)

# Set up logging to capture stdout/stderr AND put into queue
log_handler = QueueHandler()
log_handler.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', 
                              datefmt='%Y-%m-%d %H:%M:%S')
log_handler.setFormatter(formatter)

# Get root logger and add our handler
root_logger = logging.getLogger()
root_logger.addHandler(log_handler)
root_logger.setLevel(logging.INFO)

# Also redirect stdout and stderr to logging
class StreamToLogger:
    """File-like object that redirects writes to a logger"""
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        # Handle partial writes by buffering until we get a newline
        temp_buf = self.linebuf + buf
        lines = temp_buf.splitlines(keepends=True)
        
        # Process complete lines (those ending with newline)
        for line in lines[:-1]:
            if line.endswith(('\n', '\r\n', '\r')):
                self.logger.log(self.log_level, line.rstrip())
        
        # Keep any incomplete line in buffer
        if lines and not lines[-1].endswith(('\n', '\r\n', '\r')):
            self.linebuf = lines[-1]
        else:
            self.linebuf = ''
    
    def flush(self):
        # Flush any remaining buffered content
        if self.linebuf:
            self.logger.log(self.log_level, self.linebuf.rstrip())
            self.linebuf = ''

# Redirect stdout and stderr to logging (for frozen app)
if getattr(sys, 'frozen', False):
    sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO)
    sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.ERROR)

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
# Log streaming and shutdown endpoints
# ---------------------------------------------------------------------------

@app.route("/logs/stream", methods=["GET"])
def stream_logs():
    """
    Server-Sent Events endpoint that streams log messages to the browser
    """
    def generate():
        # Send initial connection message
        yield f"data: [System] Log streaming connected\n\n"
        
        # Stream logs from the queue
        while True:
            try:
                # Wait for a log message (timeout every 30 seconds for keep-alive)
                msg = LOG_QUEUE.get(timeout=30)
                # Send the log message as SSE
                yield f"data: {msg}\n\n"
            except queue.Empty:
                # Send keep-alive comment
                yield ": keep-alive\n\n"
            except Exception as e:
                yield f"data: [Error] Log streaming error: {e}\n\n"
                break
    
    return Response(generate(), mimetype='text/event-stream',
                   headers={
                       'Cache-Control': 'no-cache',
                       'X-Accel-Buffering': 'no',
                   })


@app.route("/shutdown", methods=["POST"])
def shutdown_server():
    """
    Endpoint to gracefully shutdown the server
    """
    try:
        logging.info("[AceForge] Shutdown requested from UI")
        print("[AceForge] Shutting down server...", flush=True)
        
        # Use a thread to shutdown after responding
        def shutdown():
            import time
            time.sleep(1)  # Give time for response to be sent
            # Raise KeyboardInterrupt to trigger Waitress shutdown
            import signal
            os.kill(os.getpid(), signal.SIGINT)
        
        shutdown_thread = threading.Thread(target=shutdown)
        shutdown_thread.daemon = True
        shutdown_thread.start()
        
        return {"status": "ok", "message": "Server is shutting down..."}, 200
    except Exception as e:
        logging.error(f"[AceForge] Shutdown error: {e}")
        return {"status": "error", "message": str(e)}, 500


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
    try:
        main()
    except Exception as e:
        import traceback
        error_msg = (
            "[AceForge] FATAL ERROR during startup:\n"
            f"{traceback.format_exc()}\n"
            "\n"
            "The application will now exit.\n"
            "Please check the error message above for details."
        )
        print(error_msg, flush=True)
        
        # Log to a file if possible
        try:
            error_log = Path(__file__).parent / "error.log"
            with error_log.open("a", encoding="utf-8") as f:
                f.write(f"\n\n{'='*80}\n")
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n")
                f.write(error_msg)
        except Exception:
            pass
        
        sys.exit(1)
