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

# CRITICAL: Prevent module-level code from running multiple times
# This module should only initialize once, even if somehow re-imported
if not hasattr(sys.modules.get(__name__, None), '_aceforge_app_initialized'):
    _aceforge_app_initialized = True
    sys.modules[__name__]._aceforge_app_initialized = True
    
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
else:
    # Module already initialized - this should NEVER happen in normal execution
    # If it does, something is seriously wrong with the import system
    print("[AceForge] CRITICAL: aceforge_app.py module-level code executed multiple times!", flush=True)
    print("[AceForge] This indicates a serious design flaw - modules should not be re-executed", flush=True)
    import traceback
    print(f"[AceForge] Re-execution call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)

# CRITICAL: Global state for singleton enforcement (persists across re-imports)
_webview_start_called = False
_webview_window_created = False
_webview_lock = threading.Lock()
_webview_patched = False  # Track if we've patched webview

def _patch_webview_module():
    """Patch webview module to enforce singleton behavior - call this whenever webview might be re-imported"""
    global _webview_patched, _original_webview_start, _original_webview_create_window
    
    # Import webview (may be re-imported, that's OK)
    import webview
    
    # Only patch if not already patched, or if the patch was lost (re-import)
    if not _webview_patched or not hasattr(webview, '_aceforge_patched'):
        _original_webview_start = webview.start
        _original_webview_create_window = webview.create_window
        
        def _singleton_webview_start(*args, **kwargs):
            """Singleton wrapper for webview.start() - prevents duplicate event loops"""
            global _webview_start_called
            
            with _webview_lock:
                if _webview_start_called:
                    # webview.start() already called - BLOCK and log the attempt
                    import traceback
                    print("[AceForge] BLOCKED: webview.start() called but already running", flush=True)
                    print(f"[AceForge] Blocked call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
                    return None
                
                _webview_start_called = True
                print("[AceForge] webview.start() called (first time) - starting GUI event loop", flush=True)
                import traceback
                print(f"[AceForge] webview.start() call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
                return _original_webview_start(*args, **kwargs)

        def _singleton_webview_create_window(*args, **kwargs):
            """Singleton wrapper for webview.create_window() - prevents duplicate windows"""
            global _webview_window_created
            
            with _webview_lock:
                if _webview_window_created:
                    # Window already created - BLOCK and log the attempt
                    import traceback
                    print("[AceForge] BLOCKED: webview.create_window() called but window already exists", flush=True)
                    print(f"[AceForge] Blocked call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
                    # Return existing window if available, otherwise None
                    if webview.windows:
                        return webview.windows[0]
                    return None
                
                _webview_window_created = True
                print("[AceForge] webview.create_window() called (first time) - creating window", flush=True)
                import traceback
                print(f"[AceForge] Window creation call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
                return _original_webview_create_window(*args, **kwargs)
        
        # Replace webview functions with singleton wrappers
        webview.start = _singleton_webview_start
        webview.create_window = _singleton_webview_create_window
        webview._aceforge_patched = True  # Mark as patched
        _webview_patched = True
        print("[AceForge] webview module patched for singleton enforcement", flush=True)

# Patch webview IMMEDIATELY and set up import hook to re-patch if re-imported
_patch_webview_module()

# Set up import hook using sys.meta_path (safer than patching __builtins__.__import__)
if getattr(sys, 'frozen', False):
    import importlib.util
    
    class WebviewImportHook:
        """Import hook to re-patch webview whenever it's imported"""
        def find_spec(self, name, path, target=None):
            if name == 'webview':
                # webview is being imported - we'll patch it after import
                return None  # Let normal import proceed
            return None
        
        def find_module(self, name, path=None):
            # Python 3.3+ uses find_spec, but keep this for compatibility
            return None
    
    # Install the import hook
    if WebviewImportHook not in sys.meta_path:
        sys.meta_path.insert(0, WebviewImportHook())
    
    # Also patch after any import by hooking into importlib
    _original_import_module = importlib.import_module
    def _patched_import_module(name, *args, **kwargs):
        module = _original_import_module(name, *args, **kwargs)
        if name == 'webview' or (hasattr(module, '__name__') and module.__name__ == 'webview'):
            _patch_webview_module()
        return module
    importlib.import_module = _patched_import_module

# NOW import Flask app from music_forge_ui
# If music_forge_ui tries to use webview, it will get the patched (protected) version
# Re-patch webview after import in case music_forge_ui imported it
from music_forge_ui import app
_patch_webview_module()  # Re-patch in case music_forge_ui imported webview

# Server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5056
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# Application state - managed by singleton guards above
_app_initialized = False

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
    
    # CRITICAL GUARD: Prevent multiple initialization or initialization during shutdown
    if _app_initialized or _shutting_down:
        import traceback
        print("[AceForge] BLOCKED: main() called but app already initialized or shutting down", flush=True)
        print(f"[AceForge] Blocked main() call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
        return
    
    # Additional check: if webview is already running, don't initialize again
    if _webview_start_called or len(webview.windows) > 0:
        import traceback
        print("[AceForge] BLOCKED: main() called but webview already running", flush=True)
        print(f"[AceForge] Blocked main() call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
        return
    
    print("[AceForge] main() called - initializing app", flush=True)
    import traceback
    print(f"[AceForge] main() call stack:\n{''.join(traceback.format_stack()[-10:])}", flush=True)
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
        global _app_initialized, _shutting_down
        
        # Prevent any re-initialization or duplicate shutdown calls
        if _shutting_down:
            return
        _shutting_down = True
        _app_initialized = False
        
        # Clean up all resources and release memory
        cleanup_resources()
        
        # Exit immediately - no delays that could trigger re-initialization
        # Use os._exit to bypass any cleanup handlers that might trigger re-init
        os._exit(0)
    
    # Re-patch webview before creating window (in case it was re-imported)
    _patch_webview_module()
    
    # Import webview to ensure we have the patched version
    import webview
    
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
    # CRITICAL: In PyInstaller frozen apps, modules can be re-executed
    # Use a simple file-based lock to prevent multiple main() executions
    import tempfile
    _lock_file = Path(tempfile.gettempdir()) / 'aceforge_app.lock'
    
    # Check if lock file exists
    if _lock_file.exists():
        try:
            # Try to read PID from lock file
            with open(_lock_file, 'r') as f:
                pid = int(f.read().strip())
            # Check if process is still alive (simple check)
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                # Process exists - another instance is running
                print(f"[AceForge] Another instance is already running (PID {pid}) - exiting", flush=True)
                sys.exit(1)
            except ProcessLookupError:
                # Process is dead - remove stale lock file
                _lock_file.unlink(missing_ok=True)
            except PermissionError:
                # Can't check, but assume it's running
                print(f"[AceForge] Lock file exists (PID {pid}) - assuming another instance is running", flush=True)
                sys.exit(1)
        except (ValueError, FileNotFoundError):
            # Lock file is invalid or missing - remove it
            _lock_file.unlink(missing_ok=True)
    
    # Create lock file
    try:
        _lock_file.write_text(str(os.getpid()))
    except Exception:
        pass
    
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
