#!/usr/bin/env python3
"""
Debug script to trace window creation during model loading.
Add this to trace what's happening when the second window appears.
"""

import sys
import traceback
import threading

# Hook into webview to log all window creation attempts
_original_create_window = None
_original_start = None
_window_creation_log = []

def _log_window_creation(*args, **kwargs):
    """Log all window creation attempts"""
    import inspect
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    caller_info = {
        'file': caller_frame.f_code.co_filename if caller_frame else 'unknown',
        'line': caller_frame.f_lineno if caller_frame else 0,
        'function': caller_frame.f_code.co_name if caller_frame else 'unknown',
        'args': args,
        'kwargs': kwargs,
        'stack': traceback.format_stack(caller_frame) if caller_frame else []
    }
    _window_creation_log.append(caller_info)
    print(f"[DEBUG] Window creation attempt from: {caller_info['file']}:{caller_info['line']} in {caller_info['function']}", flush=True)
    print(f"[DEBUG] Stack trace:\n{''.join(caller_info['stack'][-5:])}", flush=True)
    if _original_create_window:
        return _original_create_window(*args, **kwargs)
    return None

def _log_webview_start(*args, **kwargs):
    """Log all webview.start() calls"""
    import inspect
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    caller_info = {
        'file': caller_frame.f_code.co_filename if caller_frame else 'unknown',
        'line': caller_frame.f_lineno if caller_frame else 0,
        'function': caller_frame.f_code.co_name if caller_frame else 'unknown',
        'stack': traceback.format_stack(caller_frame) if caller_frame else []
    }
    _window_creation_log.append(('start', caller_info))
    print(f"[DEBUG] webview.start() called from: {caller_info['file']}:{caller_info['line']} in {caller_info['function']}", flush=True)
    print(f"[DEBUG] Stack trace:\n{''.join(caller_info['stack'][-5:])}", flush=True)
    if _original_start:
        return _original_start(*args, **kwargs)

def install_hooks():
    """Install hooks to trace window creation"""
    try:
        import webview
        global _original_create_window, _original_start
        if _original_create_window is None:
            _original_create_window = webview.create_window
            webview.create_window = _log_window_creation
        if _original_start is None:
            _original_start = webview.start
            webview.start = _log_webview_start
        print("[DEBUG] Window creation hooks installed", flush=True)
    except ImportError:
        print("[DEBUG] webview not available for hooking", flush=True)

def get_log():
    """Get the window creation log"""
    return _window_creation_log
