# C:\AceForge\music_forge_ui.py

from __future__ import annotations

from pathlib import Path
import sys
import os
import threading
import queue
import logging
import time
import re
import socket
import webbrowser
from io import StringIO

# ---------------------------------------------------------------------------
# Environment setup to match CI execution (test-ace-generation.yml)
# ---------------------------------------------------------------------------
# Set PyTorch MPS memory management to match CI
# CI sets: PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
if 'PYTORCH_MPS_HIGH_WATERMARK_RATIO' not in os.environ:
    os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'] = '0.0'

from flask import Flask, Response, request, send_from_directory

# ---------------------------------------------------------------------------
# Early module imports for frozen app compatibility
# ---------------------------------------------------------------------------

# Import lzma early to ensure it's available for py3langid
# This is critical for frozen PyInstaller apps where the _lzma C extension
# might not be properly initialized if imported lazily
try:
    import lzma
    import _lzma  # C extension - ensure it's loaded
    # Test that lzma actually works
    try:
        # Quick test to ensure lzma is functional
        test_data = b"test"
        compressed = lzma.compress(test_data)
        decompressed = lzma.decompress(compressed)
        if decompressed == test_data:
            print("[AceForge] lzma module initialized successfully for py3langid.", flush=True)
        else:
            print("[AceForge] WARNING: lzma module test failed.", flush=True)
    except Exception as e:
        print(f"[AceForge] WARNING: lzma module test failed: {e}", flush=True)
except ImportError as e:
    print(f"[AceForge] WARNING: Failed to import lzma module: {e}", flush=True)
    print("[AceForge] Language detection may fail in frozen app.", flush=True)
except Exception as e:
    print(f"[AceForge] WARNING: Unexpected error initializing lzma: {e}", flush=True)

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
    
    # Patch LoRA loader mixins if not available at top level (critical for frozen apps)
    if not hasattr(_cdmf_dl, "SD3LoraLoaderMixin"):
        try:
            from diffusers.loaders.lora_pipeline import (  # type: ignore[import]
                SD3LoraLoaderMixin as _CDMF_SD3LOL,
            )
            # Patch both the module and sys.modules to handle lazy loading
            _cdmf_dl.SD3LoraLoaderMixin = _CDMF_SD3LOL  # type: ignore[attr-defined]
            if 'diffusers.loaders' in sys.modules:
                sys.modules['diffusers.loaders'].SD3LoraLoaderMixin = _CDMF_SD3LOL  # type: ignore[attr-defined]
            print(
                "[AceForge] Early-patched diffusers.loaders.SD3LoraLoaderMixin "
                "for ace-step.",
                flush=True,
            )
        except Exception as _e:
            print(
                "[AceForge] WARNING: Could not expose "
                "diffusers.loaders.SD3LoraLoaderMixin early: "
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
# Paths and TORCH_HOME (before any torch/torch.hub use)
# Demucs stem splitting uses torch.hub for model download; cache must be writable.
# ---------------------------------------------------------------------------
import cdmf_paths
from cdmf_paths import APP_VERSION, get_output_dir, get_user_data_dir
os.environ.setdefault("TORCH_HOME", str(cdmf_paths.get_models_folder()))

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
import cdmf_state
from cdmf_tracks import create_tracks_blueprint
from cdmf_models import create_models_blueprint
from cdmf_mufun import create_mufun_blueprint
from cdmf_training import create_training_blueprint
from cdmf_generation import create_generation_blueprint
from cdmf_lyrics import create_lyrics_blueprint
# Voice cloning import is optional - handled in blueprint registration below

# Global flag to prevent main() from running when imported
_MUSIC_FORGE_UI_IMPORTED = False

# Flask app - configure static folder for frozen apps
if getattr(sys, 'frozen', False):
    # In frozen app, static files are in Resources/static/
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller bundle
        static_folder = Path(sys._MEIPASS) / 'static'
        template_folder = Path(sys._MEIPASS) / 'static'  # Templates are also in static
    else:
        # Fallback
        static_folder = Path(__file__).parent / 'static'
        template_folder = Path(__file__).parent / 'static'
    app = Flask(__name__, static_folder=str(static_folder), template_folder=str(template_folder))
else:
    # Development mode - use default static folder
    app = Flask(__name__)

# Mark that this module has been imported (not run directly)
_MUSIC_FORGE_UI_IMPORTED = True

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
            
            # Additional filtering at the handler level
            msg_lower = msg.lower()
            
            # Filter out task queue warnings
            if 'task queue depth' in msg_lower:
                return
            
            # Filter out client disconnect messages
            if 'client disconnected while serving' in msg_lower:
                return
            
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
    """File-like object that redirects writes to a logger with filtering"""
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''
        self.last_progress = None  # Track last progress to avoid duplicates

    def _should_filter(self, line):
        """Filter out unwanted log messages"""
        line_lower = line.lower()
        
        # Filter out task queue depth warnings
        if 'task queue depth' in line_lower:
            return True
        
        # Filter out client disconnect messages (too noisy)
        if 'client disconnected while serving' in line_lower:
            return True
        
        return False
    
    def _parse_eta_seconds(self, time_info):
        """Parse tqdm time_info like '01:34<23:38, 94.54s/it' -> remaining seconds (23*60+38)."""
        if not time_info:
            return None
        # Match <MM:SS for remaining time
        m = re.search(r"<(\d+):(\d+)", time_info)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        return None

    def _extract_progress(self, line):
        """Extract progress bar information from tqdm output. Returns (display_msg, percent, current, total, eta_seconds) or None."""
        # Match tqdm: " 50%|#####     | 35/70 [05:13<00:52,  1.50s/it]" or "  6%|6         | 1/16 [01:34<23:38, 94.54s/it]"
        progress_pattern = r"(\d+)%\s*\|\s*[#\s\d]+\|\s*(\d+)/(\d+)\s+\[([^\]]+)\]"
        match = re.search(progress_pattern, line)
        if not match:
            return None
        percent = int(match.group(1))
        current = int(match.group(2))
        total = int(match.group(3))
        time_info = match.group(4)
        eta_seconds = self._parse_eta_seconds(time_info)
        display_msg = f"[Progress] {percent}% ({current}/{total} steps) - {time_info}"
        return (display_msg, percent, current, total, eta_seconds)

    def _prefix_job_id(self, msg):
        """If a generation job is active in this thread, prefix the message with job id."""
        try:
            job_id = cdmf_state.get_current_generation_job_id()
            if job_id:
                short_id = job_id[:8] if len(job_id) >= 8 else job_id
                return f"[{short_id}] {msg}"
        except Exception:
            pass
        return msg

    def write(self, buf):
        # Handle partial writes by buffering until we get a newline
        temp_buf = self.linebuf + buf
        lines = temp_buf.splitlines(keepends=True)
        
        # Process complete lines (those ending with newline)
        for line in lines[:-1]:
            if line.endswith(('\n', '\r\n', '\r')):
                line_clean = line.rstrip()
                
                # Skip empty lines
                if not line_clean:
                    continue
                
                # Filter unwanted messages
                if self._should_filter(line_clean):
                    continue
                
                # Try to extract progress bar info (returns (display_msg, percent, current, total, eta_seconds) or None)
                progress_data = self._extract_progress(line_clean)
                if progress_data:
                    display_msg, percent, current, total, eta_seconds = progress_data
                    if display_msg != self.last_progress:
                        self.logger.log(logging.INFO, self._prefix_job_id(display_msg))
                        self.last_progress = display_msg
                    try:
                        updater = cdmf_state.get_progress_updater()
                        if updater:
                            updater(percent, current, total, eta_seconds)
                    except Exception:
                        pass
                    continue
                
                # Log other messages normally (with optional job id prefix)
                self.logger.log(self.log_level, self._prefix_job_id(line_clean))
        
        # Keep any incomplete line in buffer
        if lines and not lines[-1].endswith(('\n', '\r\n', '\r')):
            self.linebuf = lines[-1]
        else:
            self.linebuf = ''
    
    def flush(self):
        # Flush any remaining buffered content
        if self.linebuf:
            line_clean = self.linebuf.rstrip()
            if line_clean and not self._should_filter(line_clean):
                progress_data = self._extract_progress(line_clean)
                if progress_data:
                    display_msg, percent, current, total, eta_seconds = progress_data
                    if display_msg != self.last_progress:
                        self.logger.log(logging.INFO, self._prefix_job_id(display_msg))
                        self.last_progress = display_msg
                    try:
                        updater = cdmf_state.get_progress_updater()
                        if updater:
                            updater(percent, current, total, eta_seconds)
                    except Exception:
                        pass
                else:
                    self.logger.log(self.log_level, self._prefix_job_id(line_clean))
            self.linebuf = ''

# Redirect stdout and stderr to logging (for frozen app)
if getattr(sys, 'frozen', False):
    sys.stdout = StreamToLogger(logging.getLogger('STDOUT'), logging.INFO)
    # Use WARNING level for stderr to avoid logging FutureWarning as ERROR
    sys.stderr = StreamToLogger(logging.getLogger('STDERR'), logging.WARNING)

# Wire ACE-Step's progress callback into our shared state
register_progress_callback(cdmf_state.ace_progress_callback)

# Wire stem splitting's progress callback into our shared state
try:
    from cdmf_stem_splitting import register_stem_split_progress_callback
    register_stem_split_progress_callback(cdmf_state.ace_progress_callback)
except (ImportError, Exception) as e:
    # Stem splitting is optional
    pass

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

# New UI (React SPA) build output; when present we serve it at / and skip legacy index
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _UI_DIST = Path(sys._MEIPASS) / "ui" / "dist"
else:
    _UI_DIST = Path(__file__).resolve().parent / "ui" / "dist"
_USE_NEW_UI = _UI_DIST.is_dir()

# ---------------------------------------------------------------------------
# New UI API (ace-step-ui compatibility). Register first so / can be overridden later by new UI SPA.
# ---------------------------------------------------------------------------
try:
    from api import (
        auth_bp,
        songs_bp,
        generate_bp,
        playlists_bp,
        users_bp,
        contact_bp,
        reference_tracks_bp,
        search_bp,
        preferences_bp,
        ace_step_models_bp,
    )
    from api.generate import reset_generation_queue
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(songs_bp, url_prefix="/api/songs")
    app.register_blueprint(generate_bp, url_prefix="/api/generate")
    reset_generation_queue()
    app.register_blueprint(playlists_bp, url_prefix="/api/playlists")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(contact_bp, url_prefix="/api/contact")
    app.register_blueprint(reference_tracks_bp, url_prefix="/api/reference-tracks")
    app.register_blueprint(search_bp, url_prefix="/api/search")
    app.register_blueprint(preferences_bp, url_prefix="/api/preferences")
    app.register_blueprint(ace_step_models_bp, url_prefix="/api/ace-step")
except ImportError as e:
    print(f"[AceForge] New UI API not available: {e}", flush=True)


# ---------------------------------------------------------------------------
# Global error handler: log 500s to app console and return JSON for /api/*
# ---------------------------------------------------------------------------
def _log_exception_and_return_response(error, status_code=500):
    """Log full traceback to root logger (so it appears in app console), then return response."""
    import traceback
    tb = traceback.format_exc()
    logging.getLogger().error("[AceForge] Server error (%s):\n%s", status_code, tb)
    try:
        path = request.path if request else ""
    except Exception:
        path = ""
    if path.startswith("/api/"):
        last_line = [l.strip() for l in tb.strip().split("\n") if l.strip()][-1] if tb else None
        return {"error": str(error), "detail": last_line}, status_code
    return None  # Let Flask use default HTML error page for non-API


@app.errorhandler(500)
def handle_500(error):
    resp = _log_exception_and_return_response(error, 500)
    if resp is not None:
        from flask import jsonify
        return jsonify(resp[0]), resp[1]
    raise error


@app.route("/audio/<path:filename>")
def serve_audio(filename: str):
    """Serve generated tracks and reference audio. /audio/<name> -> configured output dir; /audio/refs/<name> -> references dir."""
    if ".." in filename or filename.startswith("/"):
        return Response("Invalid path", status=400, mimetype="text/plain")
    if filename.startswith("refs/"):
        ref_name = filename[5:].lstrip("/")
        if not ref_name:
            return Response("Invalid path", status=400, mimetype="text/plain")
        directory = get_user_data_dir() / "references"
        path = directory / ref_name
        if not path.is_file():
            return Response("Not found", status=404, mimetype="text/plain")
        return send_from_directory(directory, ref_name)
    directory = Path(get_output_dir())
    path = directory / filename
    if not path.is_file():
        return Response("Not found", status=404, mimetype="text/plain")
    return send_from_directory(directory, filename)


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
        serve_index=not _USE_NEW_UI,
    )
)
app.register_blueprint(create_lyrics_blueprint())
# Register voice cloning blueprint (optional component)
try:
    from cdmf_voice_cloning_bp import create_voice_cloning_blueprint
    app.register_blueprint(create_voice_cloning_blueprint(html_template=HTML))
except (ImportError, Exception) as e:
    # Voice cloning is optional - if TTS library is not installed, skip it
    print(f"[AceForge] Voice cloning not available: {e}", flush=True)

# Register stem splitting blueprint (optional component)
try:
    from cdmf_stem_splitting_bp import create_stem_splitting_blueprint
    app.register_blueprint(create_stem_splitting_blueprint(html_template=HTML))
except (ImportError, Exception) as e:
    # Stem splitting is optional - if Demucs library is not installed, skip it
    print(f"[AceForge] Stem splitting not available: {e}", flush=True)

# Register MIDI generation blueprint (optional component)
try:
    from cdmf_midi_generation_bp import create_midi_generation_blueprint
    app.register_blueprint(create_midi_generation_blueprint(html_template=HTML))
except (ImportError, Exception) as e:
    # MIDI generation is optional - if basic-pitch library is not installed, skip it
    print(f"[AceForge] MIDI generation not available: {e}", flush=True)

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
# New UI SPA: serve React app at / when ui/dist exists (registered last for catch-all)
# ---------------------------------------------------------------------------
if _USE_NEW_UI:
    _NEW_UI_RESERVED = (
        "api/",
        "healthz",
        "loading",
        "logs",
        "shutdown",
        "audio/",
        "music/",
        "tracks",
        "progress",
        "user_presets",
    )

    def _send_new_ui_index():
        return send_from_directory(str(_UI_DIST), "index.html")

    @app.route("/")
    def new_ui_index():
        return _send_new_ui_index()

    @app.route("/assets/<path:filename>")
    def new_ui_assets(filename: str):
        assets_dir = _UI_DIST / "assets"
        if not assets_dir.is_dir():
            return Response("Not found", status=404, mimetype="text/plain")
        return send_from_directory(str(assets_dir), filename)

    @app.route("/<path:path>")
    def new_ui_spa_fallback(path: str):
        for prefix in _NEW_UI_RESERVED:
            if path == prefix or path.startswith(prefix + "/"):
                return Response("Not found", status=404, mimetype="text/plain")
        return _send_new_ui_index()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Legacy main function - only used when music_forge_ui.py is run directly.
    When imported by aceforge_app.py, this function should NOT be called.
    """
    # CRITICAL GUARD: Only execute if this file is run directly (not imported)
    # This prevents aceforge_app.py or any other importer from triggering window creation
    if __name__ != "__main__":
        return
    
    # Additional safety check: If this module was imported (not run directly), don't execute
    # The _MUSIC_FORGE_UI_IMPORTED flag is set when the module is imported
    if _MUSIC_FORGE_UI_IMPORTED and __name__ == "__main__":
        # This is a weird case - module was imported but then run directly
        # Still check if aceforge_app is loaded
        if 'aceforge_app' in sys.modules:
            return
    
    # Additional safety check: If aceforge_app is in sys.modules, we're being imported
    # by aceforge_app.py and should NOT create windows
    if 'aceforge_app' in sys.modules:
        return
    
    from waitress import serve

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

    # Stem splitting (Demucs) model status - optional
    try:
        from cdmf_stem_splitting import stem_split_models_present
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
            print(
                "[AceForge] Demucs (stem splitting) model is not downloaded yet. "
                "Use the Stem Splitting tab and click \"Download Demucs models\" before first use.",
                flush=True,
            )
    except ImportError:
        pass

    # MIDI generation (basic-pitch) model status - optional
    try:
        from midi_model_setup import basic_pitch_models_present
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
            print(
                "[AceForge] basic-pitch (MIDI generation) model is not downloaded yet. "
                "Use the MIDI Generation tab and click \"Download basic-pitch models\" before first use.",
                flush=True,
            )
    except ImportError:
        pass

    print(
        f"Starting AceForge (ACE-Step Edition {APP_VERSION}) "
        "on http://127.0.0.1:5056/ ...",
        flush=True,
    )

    # CRITICAL: In frozen apps, aceforge_app.py handles ALL window creation
    # music_forge_ui.py should NEVER create windows when imported by aceforge_app.py
    # This is a pure Flask server - no pywebview code here
    aceforge_app_loaded = 'aceforge_app' in sys.modules
    
    # If aceforge_app is loaded, we're running in the frozen app
    # In this case, aceforge_app.py handles all window creation
    # music_forge_ui.py should ONLY serve Flask, never create windows
    if aceforge_app_loaded:
        # Running in frozen app - aceforge_app.py handles windows
        # Just start Flask server (blocking)
        print("[AceForge] Running in frozen app mode - aceforge_app handles windows, starting Flask server only...", flush=True)
        serve(app, host="127.0.0.1", port=5056)
        return
    
    # Only use pywebview if running music_forge_ui.py directly (not imported)
    # AND not in frozen app (frozen apps use aceforge_app.py)
    # CRITICAL: If aceforge_app is loaded, NEVER use pywebview
    is_frozen = getattr(sys, "frozen", False)
    use_pywebview = is_frozen and not aceforge_app_loaded
    
    # ADDITIONAL SAFETY: Never use pywebview if aceforge_app is in sys.modules
    # This check must happen BEFORE any webview import
    if aceforge_app_loaded:
        use_pywebview = False
        # Force Flask-only mode
        serve(app, host="127.0.0.1", port=5056)
        return

    # Configuration constants for pywebview mode (only used when running directly)
    SERVER_SHUTDOWN_DELAY = 0.3  # Seconds to wait for graceful shutdown
    SOCKET_CHECK_TIMEOUT = 0.5   # Socket connection timeout in seconds
    KEEP_ALIVE_INTERVAL = 1      # Seconds between keep-alive checks

    if use_pywebview:
        # Use pywebview for native window experience
        # CRITICAL: Double-check that aceforge_app is NOT loaded before importing webview
        if 'aceforge_app' in sys.modules:
            # aceforge_app is loaded - this should never happen, but guard against it
            use_pywebview = False
            serve(app, host="127.0.0.1", port=5056)
            return
        
        # CRITICAL: Double-check aceforge_app is NOT loaded before importing webview
        # If it is loaded, we should have already returned above, but check again as safety
        if 'aceforge_app' in sys.modules:
            serve(app, host="127.0.0.1", port=5056)
            return
        
        try:
            import webview
            from waitress import create_server
            
            # Server control - use a shared reference to the server instance
            server_instance = None
            server_shutdown_event = threading.Event()
            
            # Start Flask server in a background thread using programmatic approach
            def start_server():
                """Start the Flask server in a background thread"""
                nonlocal server_instance
                try:
                    # Create server instance for programmatic control
                    server_instance = create_server(app, host="127.0.0.1", port=5056)
                    print("[AceForge] Server starting on http://127.0.0.1:5056", flush=True)
                    server_instance.run()
                except Exception as e:
                    if not server_shutdown_event.is_set():
                        print(f"[AceForge] Server error: {e}", flush=True)
            
            def shutdown_server():
                """Gracefully shutdown the Flask server"""
                nonlocal server_instance
                if server_shutdown_event.is_set():
                    return  # Already shutting down
                
                print("[AceForge] Shutting down server...", flush=True)
                server_shutdown_event.set()
                
                # Use programmatic shutdown instead of signals
                if server_instance is not None:
                    try:
                        server_instance.close()
                    except Exception:
                        # Best-effort shutdown; ignore failures during cleanup
                        pass
            
            def on_closed():
                """Callback when window is closed - shutdown everything"""
                print("[AceForge] Window closed by user, shutting down...", flush=True)
                shutdown_server()
                # Brief pause to allow server.close() to complete gracefully
                time.sleep(SERVER_SHUTDOWN_DELAY)
                sys.exit(0)
            
            # Start server thread as daemon (will exit when main thread exits)
            # The server is stopped programmatically via server.close() in on_closed()
            server_thread = threading.Thread(target=start_server, daemon=True, name="FlaskServer")
            server_thread.start()
            
            # Wait for server to be ready (simple check with socket)
            max_wait = 5
            waited = 0
            server_ready = False
            while waited < max_wait and not server_ready:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(SOCKET_CHECK_TIMEOUT)
                    result = sock.connect_ex(('127.0.0.1', 5056))
                    sock.close()
                    if result == 0:
                        server_ready = True
                        break
                except Exception:
                    # Socket check failed; continue waiting
                    pass
                time.sleep(0.2)
                waited += 0.2
            
            if not server_ready:
                print("[AceForge] WARNING: Server may not be ready", flush=True)
            
            # Create native window with pywebview
            window_url = "http://127.0.0.1:5056/"
            
            print("[AceForge] Opening native window...", flush=True)
            
            # CRITICAL: Final check before creating window - ensure aceforge_app is NOT loaded
            if 'aceforge_app' in sys.modules:
                serve(app, host="127.0.0.1", port=5056)
                return
            
            # Create window with native macOS styling
            window = webview.create_window(
                title="AceForge",
                url=window_url,
                width=1400,
                height=900,
                min_size=(1000, 700),
                resizable=True,
                fullscreen=False,
                # macOS-specific options for native feel
                on_top=False,
                shadow=True,
                # Window close callback - critical for proper shutdown
                on_closed=on_closed,
            )
            
            # Apply zoom from preferences (default 80%); takes effect on next launch if changed in Settings
            try:
                _cfg = cdmf_paths.load_config()
                _z = int(_cfg.get("ui_zoom") or 80)
                _z = max(50, min(150, _z))
            except Exception:
                _z = 80
            _webview_zoom = f"{_z}%"
            _webview_zoom_js = f'document.documentElement.style.zoom = "{_webview_zoom}";'
            def _apply_webview_zoom(win):
                time.sleep(1.8)
                try:
                    if hasattr(win, 'run_js'):
                        win.run_js(_webview_zoom_js)
                    else:
                        win.evaluate_js(_webview_zoom_js)
                    print(f"[AceForge] Webview zoom set to {_webview_zoom}", flush=True)
                except Exception as e:
                    print(f"[AceForge] Could not set webview zoom: {e}", flush=True)
            
            # Start the GUI event loop (this blocks until window is closed)
            # Pass _apply_webview_zoom so it runs in a separate thread after window is ready
            webview.start(_apply_webview_zoom, window, debug=False)
            
            # This should not be reached (on_closed exits), but just in case
            shutdown_server()
            sys.exit(0)
            
        except ImportError:
            # Fallback to browser if pywebview is not available
            print("[AceForge] pywebview not available, falling back to browser...", flush=True)
            try:
                webbrowser.open_new("http://127.0.0.1:5056/")
            except Exception:
                # Browser launch failed; user can manually navigate to URL
                pass
            # Start Flask (blocking)
            serve(app, host="127.0.0.1", port=5056)
        except Exception as e:
            # pywebview initialization failed; fall back to browser
            print(f"[AceForge] Error with pywebview: {e}", flush=True)
            print("[AceForge] Falling back to browser...", flush=True)
            # Check if server is already running before starting a new one
            server_running = False
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(SOCKET_CHECK_TIMEOUT)
                result = sock.connect_ex(('127.0.0.1', 5056))
                sock.close()
                server_running = (result == 0)
            except Exception:
                # Socket check failed; assume server not running
                pass
            
            if server_running:
                # Server already running from failed pywebview attempt; just open browser
                print("[AceForge] Server already running, opening browser...", flush=True)
                try:
                    webbrowser.open_new("http://127.0.0.1:5056/")
                except Exception:
                    # Browser launch failed; user can manually navigate to URL
                    pass
                # Keep main thread alive (server is in background thread)
                try:
                    while True:
                        time.sleep(KEEP_ALIVE_INTERVAL)
                except KeyboardInterrupt:
                    print("[AceForge] Interrupted by user", flush=True)
                    sys.exit(0)
            else:
                # Start fresh server and browser
                try:
                    webbrowser.open_new("http://127.0.0.1:5056/")
                except Exception:
                    # Browser launch failed; user can manually navigate to URL
                    pass
                # Start Flask (blocking)
                serve(app, host="127.0.0.1", port=5056)
    else:
        # Development mode: use browser
        try:
            webbrowser.open_new("http://127.0.0.1:5056/")
        except Exception:
            # Browser launch failed; user can manually navigate to URL
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
