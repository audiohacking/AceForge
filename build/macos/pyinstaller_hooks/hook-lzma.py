"""
PyInstaller hook for lzma module.
Ensures the _lzma C extension is properly available in frozen apps.
"""

# Import lzma early to ensure it's available
try:
    import lzma
    import _lzma  # Ensure C extension is loaded
except ImportError:
    # If lzma isn't available, that's a problem but we can't fix it here
    pass
