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

from flask import Flask, Response, request

# ---------------------------------------------------------------------------
# Early module imports for frozen app compatibility
# ---------------------------------------------------------------------------

# CRITICAL: Prevent module-level code from running multiple times
# This module should only initialize once, even if somehow re-imported
if not hasattr(sys.modules.get(__name__, None), '_music_forge_ui_initialized'):
    _music_forge_ui_initialized = True
    sys.modules[__name__]._music_forge_ui_initialized = True
    
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
else:
    # Module already initialized - skip initialization to prevent duplicate messages
    pass

# ---------------------------------------------------------------------------
# Diffusers / ace-step compatibility shim (early)
# ---------------------------------------------------------------------------

# Only run diffusers patching if module hasn't been initialized yet
if not hasattr(sys.modules.get(__name__, None), '_diffusers_patched'):
    _diffusers_patched = True
    sys.modules[__name__]._diffusers_patched = True
    
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

# Global flag to prevent main() from running when imported
_MUSIC_FORGE_UI_IMPORTED = True

# Flask app instance
app = Flask(__name__)

# Configure Flask for frozen apps (PyInstaller)
if getattr(sys, 'frozen', False):
    # Running as frozen app - use sys._MEIPASS for static/template folders
    app.template_folder = str(Path(sys._MEIPASS) / 'static')
    app.static_folder = str(Path(sys._MEIPASS) / 'static')
else:
    # Running from source - use relative paths
    app.template_folder = 'static'
    app.static_folder = 'static'

# Register blueprints
app.register_blueprint(create_tracks_blueprint())
app.register_blueprint(create_models_blueprint())
app.register_blueprint(create_mufun_blueprint())
app.register_blueprint(create_training_blueprint())

# Create UI defaults dict for generation blueprint
ui_defaults = {
    "target_seconds": DEFAULT_TARGET_SECONDS,
    "fade_in": DEFAULT_FADE_IN_SECONDS,
    "fade_out": DEFAULT_FADE_OUT_SECONDS,
    "steps": 55,
    "guidance_scale": 6.0,
    "vocal_gain_db": 0.0,
    "instrumental_gain_db": 0.0,
}

app.register_blueprint(create_generation_blueprint(
    html_template=HTML,
    ui_defaults=ui_defaults,
    generate_track_ace=generate_track_ace,
))
app.register_blueprint(create_lyrics_blueprint())

# ---------------------------------------------------------------------------
# Log streaming setup
# ---------------------------------------------------------------------------

# Queue for log messages to be streamed to UI
_log_queue = queue.Queue()

# Custom logging handler that puts messages into the queue
class QueueHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            _log_queue.put_nowait(msg)
        except queue.Full:
            pass  # Drop message if queue is full
        except Exception:
            pass  # Ignore errors in logging handler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s',
    handlers=[QueueHandler()]
)

# Stream stdout/stderr to logging
class StreamToLogger:
    """Redirect stdout/stderr to logging system"""
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''
        self.temp_buf = ''

    def write(self, buf):
        # Accumulate partial lines
        self.temp_buf += buf
        temp_buf = self.temp_buf
        
        # Process complete lines (those ending with newline)
        while '\n' in temp_buf:
            line, temp_buf = temp_buf.split('\n', 1)
            line = line.strip()
            if line:
                # Filter out noisy messages
                if 'Task queue depth' in line:
                    return  # Skip task queue depth messages
                if 'Client disconnected' in line:
                    return  # Skip client disconnect messages
                
                # Extract tqdm progress bar updates
                tqdm_match = re.search(r'(\d+)%\|.*?\| (\d+)/(\d+)', line)
                if tqdm_match:
                    percent = int(tqdm_match.group(1))
                    current = int(tqdm_match.group(2))
                    total = int(tqdm_match.group(3))
                    line = f"Progress: {percent}% ({current}/{total} steps)"
                
                self.logger.log(self.log_level, line)
        
        self.temp_buf = temp_buf

    def flush(self):
        pass

# Redirect stdout/stderr to logging
sys.stdout = StreamToLogger(logging.getLogger('stdout'), logging.INFO)
sys.stderr = StreamToLogger(logging.getLogger('stderr'), logging.ERROR)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main UI"""
    return render_template_string(HTML)

@app.route("/logs/stream")
def stream_logs():
    """Stream logs to UI via Server-Sent Events"""
    def generate():
        while True:
            try:
                msg = _log_queue.get(timeout=1.0)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                yield "data: \n\n"  # Keep connection alive
            except Exception:
                break
    
    return Response(generate(), mimetype="text/event-stream")

@app.route("/shutdown", methods=["POST"])
def shutdown_server():
    """Gracefully shutdown the server"""
    try:
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
        return {"status": "ok", "message": "Server shutting down..."}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


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
        print(f"[AceForge] BLOCKED: music_forge_ui.main() called but __name__={__name__} (not '__main__')", flush=True)
        import traceback
        print(f"[AceForge] music_forge_ui.main() call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
        return
    
    # Additional safety check: If this module was imported (not run directly), don't execute
    # The _MUSIC_FORGE_UI_IMPORTED flag is set when the module is imported
    if _MUSIC_FORGE_UI_IMPORTED and __name__ == "__main__":
        # This is a weird case - module was imported but then run directly
        # Still check if aceforge_app is loaded
        if 'aceforge_app' in sys.modules:
            print("[AceForge] BLOCKED: music_forge_ui.main() called but aceforge_app is loaded - skipping to prevent duplicate windows", flush=True)
            return
    
    # Additional safety check: If aceforge_app is in sys.modules, we're being imported
    # by aceforge_app.py and should NOT create windows
    if 'aceforge_app' in sys.modules:
        print("[AceForge] BLOCKED: music_forge_ui.main() called but aceforge_app is loaded - skipping to prevent duplicate windows", flush=True)
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

    print(
        "Starting AceForge (ACE-Step Edition v0.1) "
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
    
    if use_pywebview:
        try:
            import webview
            from waitress import create_server
            
            # Start Flask server in background thread
            def start_server():
                server = create_server(app, host="127.0.0.1", port=5056, threads=4)
                server.run()
            
            server_thread = threading.Thread(target=start_server, daemon=True)
            server_thread.start()
            
            # Wait for server to be ready
            max_wait = 30
            waited = 0
            while waited < max_wait:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex(("127.0.0.1", 5056))
                    sock.close()
                    if result == 0:
                        break
                except Exception:
                    pass
                time.sleep(0.5)
                waited += 0.5
            
            window_url = "http://127.0.0.1:5056/"
            
            def on_closed():
                """Handle window close event"""
                print("[AceForge] Window closed, shutting down...", flush=True)
                shutdown_server()
                sys.exit(0)
            
            print("[AceForge] Opening native window...", flush=True)
            
            # CRITICAL: Final check before creating window - ensure aceforge_app is NOT loaded
            if 'aceforge_app' in sys.modules:
                print("[AceForge] CRITICAL: aceforge_app detected before window creation - BLOCKING", flush=True)
                import traceback
                print(f"[AceForge] Blocked window creation call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
                serve(app, host="127.0.0.1", port=5056)
                return
            
            # Create window with native macOS styling
            print("[AceForge] music_forge_ui.py creating window (should NOT happen if aceforge_app is loaded)", flush=True)
            import traceback
            print(f"[AceForge] music_forge_ui window creation call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
            webview.create_window(
                title="AceForge - AI Music Generation",
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
            
            # Start the GUI event loop (this blocks until window is closed)
            # When window closes, on_closed() will be called automatically
            webview.start(debug=False)
            
            # This should not be reached (on_closed exits), but just in case
            shutdown_server()
            sys.exit(0)
            
        except ImportError:
            # pywebview not available - fall back to browser
            print("[AceForge] pywebview not available, falling back to browser...", flush=True)
            use_pywebview = False
    
    if not use_pywebview:
        # Start server and open browser
        KEEP_ALIVE_INTERVAL = 1.0
        
        # Check if server is already running
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", 5056))
            sock.close()
            if result == 0:
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
                serve(app, host="127.0.0.1", port=5056)
        except Exception as e:
            print(f"[AceForge] Error starting server: {e}", flush=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
