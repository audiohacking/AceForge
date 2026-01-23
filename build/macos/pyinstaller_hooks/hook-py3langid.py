"""
PyInstaller hook for py3langid package.
Ensures the data/model.plzma file is properly bundled in frozen apps.
"""
from PyInstaller.utils.hooks import collect_data_files

# Collect all data files from py3langid package
# This is critical for LangSegment which uses py3langid for language detection
datas = collect_data_files('py3langid')

# Explicitly ensure model.plzma is included
try:
    import py3langid
    from pathlib import Path
    pkg_path = Path(py3langid.__file__).parent
    model_file = pkg_path / 'data' / 'model.plzma'
    if model_file.exists():
        # Check if it's already in datas
        model_in_datas = any('model.plzma' in str(path) for path, _ in datas)
        if not model_in_datas:
            datas.append((str(model_file), 'py3langid/data'))
except Exception:
    # If we can't find it, collect_data_files should have handled it
    pass
