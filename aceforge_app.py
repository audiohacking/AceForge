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
import atexit
from pathlib import Path

# CRITICAL: Prevent module from being executed multiple times
# This can happen if the entry point is somehow re-executed
if hasattr(sys.modules.get(__name__, None), '_aceforge_app_executed'):
    # Module already executed - this should never happen, but guard against it
    print("[AceForge] CRITICAL: aceforge_app.py is being re-executed! This should not happen.", flush=True)
    print("[AceForge] Exiting to prevent duplicate instances.", flush=True)
    sys.exit(1)

# Mark module as executed
sys.modules[__name__]._aceforge_app_executed = True

# Try to import fcntl (Unix/macOS only)
try:
    import fcntl
    _FCNTL_AVAILABLE = True
except ImportError:
    _FCNTL_AVAILABLE = False
    print("[AceForge] WARNING: fcntl not available - single-instance lock disabled", flush=True)

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

# Import pywebview FIRST and patch it BEFORE importing music_forge_ui
# This ensures that even if music_forge_ui tries to use webview, it will be protected
import webview

# CRITICAL: Singleton guards for webview operations
# These ensure webview.create_window() and webview.start() can ONLY be called once
# This must happen BEFORE importing music_forge_ui to protect against any webview usage there
_original_webview_start = webview.start
_original_webview_create_window = webview.create_window
_webview_start_called = False
_webview_window_created = False
_webview_lock = threading.Lock()

def _singleton_webview_start(*args, **kwargs):
    """Singleton wrapper for webview.start() - prevents duplicate event loops"""
    global _webview_start_called
    
    with _webview_lock:
        if _webview_start_called:
            # webview.start() already called - silently block
            return None
        
        _webview_start_called = True
        return _original_webview_start(*args, **kwargs)

def _singleton_webview_create_window(*args, **kwargs):
    """Singleton wrapper for webview.create_window() - prevents duplicate windows"""
    global _webview_window_created
    
    with _webview_lock:
        if _webview_window_created:
            # Window already created - return existing window or None
            if webview.windows:
                return webview.windows[0]
            return None
        
        _webview_window_created = True
        return _original_webview_create_window(*args, **kwargs)

# Replace webview functions with singleton wrappers IMMEDIATELY
# This protects against any code that imports webview after this point
webview.start = _singleton_webview_start
webview.create_window = _singleton_webview_create_window

# NOW import Flask app from music_forge_ui
# If music_forge_ui tries to use webview, it will get the patched (protected) version
from music_forge_ui import app

# Server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5056
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# Application state - managed by singleton guards above
_app_initialized = False

# Single-instance lock file to prevent multiple app instances
_LOCK_FILE = None
_LOCK_FD = None

def acquire_instance_lock():
    """Acquire a file-based lock to ensure only one instance runs"""
    global _LOCK_FILE, _LOCK_FD
    
    if not _FCNTL_AVAILABLE:
        # fcntl not available - skip locking (shouldn't happen on macOS)
        print("[AceForge] WARNING: fcntl not available, skipping instance lock", flush=True)
        return True
    
    # Use a lock file in the user's Application Support directory
    lock_dir = Path.home() / 'Library' / 'Application Support' / 'AceForge'
    lock_dir.mkdir(parents=True, exist_ok=True)
    _LOCK_FILE = lock_dir / 'aceforge.lock'
    
    try:
        # Try to open the lock file in exclusive mode
        _LOCK_FD = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
        
        # Try to acquire an exclusive lock (non-blocking)
        try:
            fcntl.flock(_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Lock acquired successfully - write our PID
            os.write(_LOCK_FD, str(os.getpid()).encode())
            os.fsync(_LOCK_FD)
            
            # Register cleanup function
            def release_lock():
                global _LOCK_FD, _LOCK_FILE
                if _LOCK_FD is not None:
                    try:
                        if _FCNTL_AVAILABLE:
                            fcntl.flock(_LOCK_FD, fcntl.LOCK_UN)
                        os.close(_LOCK_FD)
                        if _LOCK_FILE and _LOCK_FILE.exists():
                            _LOCK_FILE.unlink()
                    except Exception:
                        pass
                    _LOCK_FD = None
            
            atexit.register(release_lock)
            print("[AceForge] Instance lock acquired - single instance enforced", flush=True)
            return True
            
        except BlockingIOError:
            # Lock is held by another process
            os.close(_LOCK_FD)
            _LOCK_FD = None
            
            # Try to read the PID from the lock file
            try:
                if _LOCK_FILE.exists():
                    with open(_LOCK_FILE, 'r') as f:
                        pid = int(f.read().strip())
                    # Check if the process is still running
                    try:
                        os.kill(pid, 0)  # Signal 0 just checks if process exists
                        print(f"[AceForge] ERROR: Another instance is already running (PID {pid})", flush=True)
                        print("[AceForge] Please close the existing instance before starting a new one.", flush=True)
                    except ProcessLookupError:
                        # Process doesn't exist - stale lock file
                        print("[AceForge] WARNING: Stale lock file detected, removing...", flush=True)
                        _LOCK_FILE.unlink()
                        # Retry once
                        return acquire_instance_lock()
            except Exception:
                pass
            
            print("[AceForge] ERROR: Another instance of AceForge is already running.", flush=True)
            print("[AceForge] Only one instance can run at a time.", flush=True)
            return False
            
    except Exception as e:
        print(f"[AceForge] WARNING: Could not acquire instance lock: {e}", flush=True)
        print("[AceForge] Continuing anyway, but multiple instances may cause issues.", flush=True)
        if _LOCK_FD is not None:
            try:
                os.close(_LOCK_FD)
            except Exception:
                pass
            _LOCK_FD = None
        return True  # Allow to continue, but warn

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

# Global shutdown flag
_shutting_down = False

def main():
    """Main entry point: start Flask server and pywebview window"""
    global _app_initialized, _shutting_down
    
    # CRITICAL: Acquire instance lock FIRST - prevents multiple instances
    if not acquire_instance_lock():
        print("[AceForge] Exiting - another instance is running", flush=True)
        sys.exit(1)
    
    # CRITICAL GUARD: Prevent multiple initialization or initialization during shutdown
    if _app_initialized or _shutting_down:
        return
    
    # Additional check: if webview is already running, don't initialize again
    if _webview_start_called or len(webview.windows) > 0:
        return
    
    _app_initialized = True
    
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
        global _app_initialized, _shutting_down, _LOCK_FD, _LOCK_FILE
        
        # Prevent any re-initialization or duplicate shutdown calls
        if _shutting_down:
            return
        _shutting_down = True
        _app_initialized = False
        
        # Clean up all resources and release memory
        cleanup_resources()
        
        # Release instance lock
        if _LOCK_FD is not None:
            try:
                if _FCNTL_AVAILABLE:
                    fcntl.flock(_LOCK_FD, fcntl.LOCK_UN)
                os.close(_LOCK_FD)
                if _LOCK_FILE and _LOCK_FILE.exists():
                    _LOCK_FILE.unlink()
            except Exception:
                pass
        
        # Exit immediately - no delays that could trigger re-initialization
        # Use os._exit to bypass any cleanup handlers that might trigger re-init
        os._exit(0)
    
    # Create pywebview window pointing to Flask server
    # The singleton wrapper ensures this can only be called once
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
    
    if window is None:
        # Window creation was blocked (already exists) - should not happen, but handle gracefully
        print("[AceForge] ERROR: Window creation blocked but no window exists", flush=True)
        sys.exit(1)
    
    # Register window close event handler
    try:
        window.events.closed += on_window_closed
    except Exception as e:
        print(f"[AceForge] Warning: Could not register close handler: {e}", flush=True)
        # Fallback: use atexit as backup
        import atexit
        atexit.register(cleanup_resources)
    
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
