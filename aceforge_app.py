#!/usr/bin/env python3
"""
AceForge - Flask + pywebview Application
Native macOS app using Flask server with pywebview window.
"""

from __future__ import annotations

import sys
import os
import threading
import time
import socket
from pathlib import Path

# Set environment variables early
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
if 'PYTORCH_MPS_HIGH_WATERMARK_RATIO' not in os.environ:
    os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'] = '0.0'

# Critical: Import lzma EARLY (before any ACE-Step imports)
try:
    import lzma
    import _lzma
    test_data = b"test"
    compressed = lzma.compress(test_data)
    decompressed = lzma.decompress(compressed)
    if decompressed == test_data and getattr(sys, 'frozen', False):
        print("[AceForge] lzma module initialized successfully.", flush=True)
except Exception as e:
    print(f"[AceForge] WARNING: lzma initialization: {e}", flush=True)

# Import Flask app from music_forge_ui
from music_forge_ui import app

# Import pywebview
import webview

# CRITICAL: Monkey-patch webview.start() to be a global singleton
# This ensures webview.start() can ONLY be called once, even from other modules
_original_webview_start = webview.start
_webview_start_called = False
_webview_start_lock = threading.Lock()

def _singleton_webview_start(*args, **kwargs):
    """Singleton wrapper for webview.start() - prevents duplicate windows"""
    global _webview_start_called
    
    with _webview_start_lock:
        if _webview_start_called:
            print("[AceForge] CRITICAL: webview.start() already called - blocking duplicate window creation", flush=True)
            import traceback
            print(f"[AceForge] Blocked call stack:\n{''.join(traceback.format_stack()[-5:])}", flush=True)
            return  # Block the call - webview is already running
        
        _webview_start_called = True
        print("[AceForge] webview.start() called (first time) - starting GUI event loop", flush=True)
        return _original_webview_start(*args, **kwargs)

# Replace webview.start() with our singleton wrapper
webview.start = _singleton_webview_start

# Server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5056
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# Global singleton flags - ensure only one window is ever created
_window_created = False
_webview_started = False

class WindowControlAPI:
    """API for window control operations (minimize, restore, etc.)"""
    
    def minimize(self):
        """Minimize the window"""
        try:
            if webview.windows:
                webview.windows[0].minimize()
                return {"status": "ok"}
            return {"status": "error", "message": "No window available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def restore(self):
        """Restore the window if minimized or maximized"""
        try:
            if webview.windows:
                webview.windows[0].restore()
                return {"status": "ok"}
            return {"status": "error", "message": "No window available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def maximize(self):
        """Maximize the window"""
        try:
            if webview.windows:
                webview.windows[0].maximize()
                return {"status": "ok"}
            return {"status": "error", "message": "No window available"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

def wait_for_server(max_wait=30):
    """Wait for Flask server to be ready"""
    waited = 0
    while waited < max_wait:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((SERVER_HOST, SERVER_PORT))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(0.5)
        waited += 0.5
    return False

def cleanup_resources():
    """Clean up all resources and release memory before shutdown"""
    print("[AceForge] Cleaning up resources and releasing memory...", flush=True)
    
    try:
        # Clean up ACE-Step pipeline if it exists
        try:
            import generate_ace
            # Access the module-level globals
            if hasattr(generate_ace, '_ACE_PIPELINE') and hasattr(generate_ace, '_ACE_PIPELINE_LOCK'):
                with generate_ace._ACE_PIPELINE_LOCK:
                    if generate_ace._ACE_PIPELINE is not None:
                        print("[AceForge] Cleaning up ACE-Step pipeline...", flush=True)
                        try:
                            # Call cleanup_memory to release GPU/CPU memory
                            generate_ace._ACE_PIPELINE.cleanup_memory()
                        except Exception as e:
                            print(f"[AceForge] Warning: Error during pipeline cleanup: {e}", flush=True)
                        
                        # Clear the global pipeline reference
                        generate_ace._ACE_PIPELINE = None
                        print("[AceForge] ACE-Step pipeline released", flush=True)
        except ImportError:
            pass  # generate_ace not available
        except Exception as e:
            print(f"[AceForge] Warning: Error accessing pipeline: {e}", flush=True)
        
        # Clear PyTorch caches
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                print("[AceForge] CUDA cache cleared", flush=True)
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                try:
                    torch.mps.empty_cache()
                    print("[AceForge] MPS cache cleared", flush=True)
                except Exception:
                    pass
        except Exception as e:
            print(f"[AceForge] Warning: Error clearing PyTorch cache: {e}", flush=True)
        
        # Force garbage collection
        import gc
        gc.collect()
        print("[AceForge] Garbage collection completed", flush=True)
        
    except Exception as e:
        print(f"[AceForge] Warning: Error during cleanup: {e}", flush=True)
    
    print("[AceForge] Resource cleanup completed", flush=True)

def start_flask_server():
    """Start Flask server in background thread"""
    from waitress import serve
    print(f"[AceForge] Starting Flask server on {SERVER_URL}...", flush=True)
    try:
        serve(app, host=SERVER_HOST, port=SERVER_PORT, threads=4, channel_timeout=120)
    except Exception as e:
        print(f"[AceForge] Flask server error: {e}", flush=True)
        raise

def main():
    """Main entry point: start Flask server and pywebview window"""
    global _window_created, _webview_started
    
    # CRITICAL GUARD: Prevent multiple calls to main() or webview.start()
    if _webview_started:
        print("[AceForge] BLOCKED: webview.start() already called - preventing duplicate window", flush=True)
        return
    
    # Guard: Ensure only one window is ever created
    if _window_created:
        print("[AceForge] BLOCKED: Window already created, not creating another", flush=True)
        return
    
    if len(webview.windows) > 0:
        print("[AceForge] BLOCKED: Window already exists, not creating another", flush=True)
        _window_created = True
        # Don't call webview.start() here - it should already be running
        # If we get here, something is wrong - just return
        return
    
    # Start Flask server in background thread
    server_thread = threading.Thread(target=start_flask_server, daemon=True, name="FlaskServer")
    server_thread.start()
    
    # Wait for server to be ready
    print("[AceForge] Waiting for server to start...", flush=True)
    if not wait_for_server():
        print("[AceForge] ERROR: Server failed to start in time", flush=True)
        sys.exit(1)
    
    print(f"[AceForge] Server ready at {SERVER_URL}", flush=True)
    
    # Create API instance for window controls
    window_api = WindowControlAPI()
    
    # Define window close handler for clean shutdown
    def on_window_closed():
        """Handle window close event - cleanup and exit"""
        print("[AceForge] Window closed by user, shutting down...", flush=True)
        
        # Clean up all resources and release memory
        cleanup_resources()
        
        # Give a brief moment for cleanup to complete
        time.sleep(0.5)
        
        # Exit cleanly
        print("[AceForge] Shutdown complete, exiting...", flush=True)
        sys.exit(0)
    
    # Create pywebview window pointing to Flask server
    # Only create if no windows exist and we haven't created one before
    if len(webview.windows) == 0 and not _window_created:
        window = webview.create_window(
            title="AceForge - AI Music Generation",
            url=SERVER_URL,
            width=1400,
            height=900,
            min_size=(1000, 700),
            resizable=True,
            fullscreen=False,
            on_top=False,
            shadow=True,
            js_api=window_api,  # Expose window control API to JavaScript
        )
        _window_created = True
        
        # Register window close event handler
        try:
            window.events.closed += on_window_closed
        except Exception as e:
            print(f"[AceForge] Warning: Could not register close handler: {e}", flush=True)
            # Fallback: use atexit as backup
            import atexit
            atexit.register(cleanup_resources)
    
    # Mark that webview.start() is about to be called
    # The singleton wrapper will prevent duplicate calls from any module
    _webview_started = True
    
    # Register atexit handler as backup cleanup
    import atexit
    atexit.register(cleanup_resources)
    
    # Start the GUI event loop (only once - this is a blocking call)
    # The singleton wrapper ensures this can only be called once globally
    webview.start(debug=False)
    
    # This should not be reached (on_window_closed exits), but just in case
    cleanup_resources()
    sys.exit(0)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        error_msg = (
            "[AceForge] FATAL ERROR during startup:\n"
            f"{traceback.format_exc()}\n"
            "\n"
            "The application will now exit.\n"
        )
        print(error_msg, flush=True)
        
        # Log to file
        try:
            log_dir = Path.home() / 'Library' / 'Logs' / 'AceForge'
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / 'error.log', 'w') as f:
                f.write(error_msg)
        except:
            pass
        
        sys.exit(1)
