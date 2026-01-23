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

# Server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5056
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# Global flag to ensure only one window is ever created
_window_created = False
_webview_started = False
_window_instance = None

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

def start_flask_server():
    """Start Flask server in background thread"""
    from waitress import serve
    print(f"[AceForge] Starting Flask server on {SERVER_URL}...", flush=True)
    try:
        serve(app, host=SERVER_HOST, port=SERVER_PORT, threads=4, channel_timeout=120)
    except Exception as e:
        print(f"[AceForge] Flask server error: {e}", flush=True)
        raise

# Event handlers for pywebview window
def on_before_show(window):
    """Called before window is shown"""
    global _window_instance
    _window_instance = window
    print("[AceForge] Window about to be shown", flush=True)

def on_closed():
    """Called when window is closed"""
    print("[AceForge] Window closed, exiting...", flush=True)
    sys.exit(0)

def on_closing():
    """Called when window is closing"""
    print("[AceForge] Window closing...", flush=True)

def on_initialized(renderer):
    """Called when GUI is initialized"""
    print(f"[AceForge] GUI initialized with renderer: {renderer}", flush=True)
    
    # CRITICAL: If multiple windows exist, prevent duplicate initialization
    if len(webview.windows) > 1:
        print("[AceForge] BLOCKED: Duplicate window initialization detected - canceling", flush=True)
        return False  # Cancel initialization to prevent duplicate window
    
    # Return True to allow initialization
    return True

def on_shown():
    """Called when window is shown"""
    print("[AceForge] Window shown", flush=True)

def on_minimized():
    """Called when window is minimized"""
    print("[AceForge] Window minimized", flush=True)

def on_restored():
    """Called when window is restored"""
    print("[AceForge] Window restored", flush=True)

def on_maximized():
    """Called when window is maximized"""
    print("[AceForge] Window maximized", flush=True)

def on_resized(width, height):
    """Called when window is resized"""
    print(f"[AceForge] Window resized to {width} x {height}", flush=True)

def on_loaded(window):
    """Called when DOM is ready"""
    global _window_instance
    _window_instance = window
    print("[AceForge] DOM loaded", flush=True)
    
    # The loading.html page will handle its own redirect via JavaScript
    # when it detects the server is ready, so we don't need to do anything here
    # Just log that the page loaded

def show_error_dialog(title, message):
    """Show an error dialog to the user"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()  # Hide main window
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        # Fallback: print to console and try to show via pywebview if available
        print(f"\n{'='*80}", flush=True)
        print(f"ERROR: {title}", flush=True)
        print(f"{'='*80}", flush=True)
        print(message, flush=True)
        print(f"{'='*80}\n", flush=True)
        try:
            if _window_instance:
                _window_instance.evaluate_js(f"alert('{title}\\n\\n{message.replace(chr(39), chr(92)+chr(39))}')")
        except:
            pass

def main():
    """Main entry point: start Flask server and pywebview window"""
    global _window_created, _webview_started, _window_instance
    
    try:
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
            _webview_started = True
            return
        
        # Start Flask server in background thread
        print("[AceForge] Starting Flask server...", flush=True)
        server_thread = threading.Thread(target=start_flask_server, daemon=True, name="FlaskServer")
        server_thread.start()
        
        # Give server a moment to start
        time.sleep(0.5)
        
        # Start with loading page - it will redirect to main UI once server is ready
        loading_url = f"{SERVER_URL}loading"
        
        print(f"[AceForge] Creating window with loading page: {loading_url}", flush=True)
        
        # Create pywebview window starting with loading page
        # Use minimal event handlers first to avoid crashes
        try:
            window = webview.create_window(
                title="AceForge - AI Music Generation",
                url=loading_url,  # Start with loading page
                width=1400,
                height=900,
                min_size=(1000, 700),
                resizable=True,
                fullscreen=False,
                frameless=False,  # Show window controls (minimize/restore/close buttons)
                on_top=False,
                shadow=True,
                text_select=True,  # Enable text selection
            )
            print("[AceForge] Window created successfully", flush=True)
        except Exception as e:
            import traceback
            error_msg = f"Failed to create pywebview window: {e}\n{traceback.format_exc()}"
            print(f"[AceForge] ERROR: {error_msg}", flush=True)
            show_error_dialog("AceForge Error", f"Failed to create window:\n\n{error_msg}")
            sys.exit(1)
        
        _window_instance = window
        _window_created = True
        
        # Register event handlers on window object (if supported)
        try:
            window.events.closed += on_closed
            print("[AceForge] Registered on_closed handler", flush=True)
        except Exception as e:
            print(f"[AceForge] Warning: Could not register on_closed: {e}", flush=True)
        
        try:
            window.events.closing += on_closing
            print("[AceForge] Registered on_closing handler", flush=True)
        except Exception as e:
            print(f"[AceForge] Warning: Could not register on_closing: {e}", flush=True)
        
        # Try to register other handlers (may not be supported in all versions)
        optional_handlers = [
            ('shown', on_shown),
            ('minimized', on_minimized),
            ('restored', on_restored),
            ('maximized', on_maximized),
            ('resized', on_resized),
            ('loaded', on_loaded),
        ]
        
        for event_name, handler in optional_handlers:
            try:
                event_attr = getattr(window.events, event_name)
                event_attr += handler
                print(f"[AceForge] Registered {event_name} handler", flush=True)
            except Exception as e:
                print(f"[AceForge] Warning: Could not register {event_name}: {e}", flush=True)
        
        # CRITICAL: Mark that webview.start() is about to be called
        # This prevents any subsequent calls from creating duplicate windows
        _webview_started = True
        
        print("[AceForge] Starting webview event loop...", flush=True)
        
        # Start the GUI event loop (only once - this is a blocking call)
        try:
            webview.start(debug=True)  # Enable debug to see errors
        except Exception as e:
            error_msg = f"Failed to start webview: {e}\n{traceback.format_exc()}"
            print(f"[AceForge] ERROR: {error_msg}", flush=True)
            show_error_dialog("AceForge Error", f"Failed to start window:\n\n{error_msg}")
            sys.exit(1)
        
        # Cleanup after window closes
        print("[AceForge] Window closed, exiting...", flush=True)
        sys.exit(0)
        
    except Exception as e:
        import traceback
        error_msg = f"Fatal error in main(): {e}\n{traceback.format_exc()}"
        print(f"[AceForge] FATAL ERROR: {error_msg}", flush=True)
        show_error_dialog("AceForge Fatal Error", error_msg)
        sys.exit(1)


if __name__ == '__main__':
    import traceback
    
    try:
        main()
    except KeyboardInterrupt:
        print("[AceForge] Interrupted by user", flush=True)
        sys.exit(0)
    except Exception as e:
        error_msg = (
            "[AceForge] FATAL ERROR during startup:\n"
            f"{traceback.format_exc()}\n"
            "\n"
            "The application will now exit.\n"
        )
        print(error_msg, flush=True)
        
        # Try to show error dialog
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("AceForge Fatal Error", error_msg)
            root.destroy()
        except Exception:
            # If tkinter fails, at least we printed to console
            pass
        
        # Log to file
        try:
            log_dir = Path.home() / 'Library' / 'Logs' / 'AceForge'
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / 'error.log', 'w') as f:
                f.write(error_msg)
            print(f"[AceForge] Error logged to: {log_dir / 'error.log'}", flush=True)
        except Exception as log_err:
            print(f"[AceForge] Failed to log error: {log_err}", flush=True)
        
        sys.exit(1)
