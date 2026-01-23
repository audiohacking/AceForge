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
        )
        _window_created = True
    
    # CRITICAL: Mark that webview.start() is about to be called
    # This prevents any subsequent calls from creating duplicate windows
    _webview_started = True
    
    # Start the GUI event loop (only once - this is a blocking call)
    webview.start(debug=False)
    
    # Cleanup after window closes
    print("[AceForge] Window closed, exiting...", flush=True)
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
