# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for AceForge (macOS)

import sys
from pathlib import Path

# Import PyInstaller utilities for collecting binaries and data files
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs
import os

block_cipher = None

# Determine paths
spec_root = Path(SPECPATH)
static_dir = spec_root / 'static'
training_config_dir = spec_root / 'training_config'
ace_models_dir = spec_root / 'ace_models'
icon_path = spec_root / 'build' / 'macos' / 'AceForge.icns'

# Collect _lzma binary explicitly (critical for py3langid in frozen apps)
# PyInstaller should auto-detect it, but we ensure it's included
_lzma_binaries = []
try:
    # Try PyInstaller's collect_dynamic_libs first (most reliable)
    _lzma_binaries = collect_dynamic_libs('_lzma')
    if _lzma_binaries:
        print(f"[CDMF.spec] Collected _lzma binaries via collect_dynamic_libs: {len(_lzma_binaries)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_dynamic_libs('_lzma') failed: {e}")
    # Fallback: try to find it manually
    try:
        import _lzma
        import importlib.util
        _lzma_spec = importlib.util.find_spec('_lzma')
        if _lzma_spec and _lzma_spec.origin:
            _lzma_path = Path(_lzma_spec.origin)
            if _lzma_path.exists():
                _lzma_binaries.append((str(_lzma_path), '.'))
                print(f"[CDMF.spec] Found _lzma binary manually at: {_lzma_path}")
    except Exception as e2:
        print(f"[CDMF.spec] WARNING: Manual _lzma binary search failed: {e2}")
        # PyInstaller should still find it automatically, but log the warning

# Collect tokenizers binaries (Rust-based library with C extensions)
# VoiceBpeTokenizer depends on tokenizers which has native extensions
_tokenizers_binaries = []
try:
    _tokenizers_binaries = collect_dynamic_libs('tokenizers')
    if _tokenizers_binaries:
        print(f"[CDMF.spec] Collected tokenizers binaries via collect_dynamic_libs: {len(_tokenizers_binaries)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_dynamic_libs('tokenizers') failed: {e}")

# Collect data files for py3langid (critical for LangSegment)
# py3langid needs its data/model.plzma file
_py3langid_data = []
try:
    _py3langid_data = collect_data_files('py3langid')
    if _py3langid_data:
        print(f"[CDMF.spec] Collected py3langid data files: {len(_py3langid_data)} files")
        # Verify model.plzma is included
        has_model = any('model.plzma' in str(path) for path, _ in _py3langid_data)
        if not has_model:
            print(f"[CDMF.spec] WARNING: model.plzma not found in collected py3langid data files")
            # Try to find it manually
            try:
                import py3langid
                from pathlib import Path
                pkg_path = Path(py3langid.__file__).parent
                model_file = pkg_path / 'data' / 'model.plzma'
                if model_file.exists():
                    _py3langid_data.append((str(model_file), 'py3langid/data'))
                    print(f"[CDMF.spec] Manually added py3langid data/model.plzma")
                else:
                    print(f"[CDMF.spec] WARNING: model.plzma not found at {model_file}")
            except Exception as e2:
                print(f"[CDMF.spec] WARNING: Failed to manually locate py3langid data: {e2}")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('py3langid') failed: {e}")
    # Try manual collection as fallback
    try:
        import py3langid
        from pathlib import Path
        pkg_path = Path(py3langid.__file__).parent
        data_dir = pkg_path / 'data'
        if data_dir.exists():
            for data_file in data_dir.glob('*'):
                if data_file.is_file():
                    rel_path = data_file.relative_to(pkg_path)
                    _py3langid_data.append((str(data_file), f'py3langid/{rel_path.parent}'))
            print(f"[CDMF.spec] Manually collected {len(_py3langid_data)} py3langid data files")
    except Exception as e2:
        print(f"[CDMF.spec] WARNING: Manual py3langid data collection failed: {e2}")

# Collect data files for acestep.models.lyrics_utils (VoiceBpeTokenizer may need vocab files)
_acestep_lyrics_data = []
try:
    _acestep_lyrics_data = collect_data_files('acestep.models.lyrics_utils')
    if _acestep_lyrics_data:
        print(f"[CDMF.spec] Collected acestep.models.lyrics_utils data files: {len(_acestep_lyrics_data)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('acestep.models.lyrics_utils') failed: {e}")

# Collect data files for tokenizers (may have vocab/model files)
_tokenizers_data = []
try:
    _tokenizers_data = collect_data_files('tokenizers')
    if _tokenizers_data:
        print(f"[CDMF.spec] Collected tokenizers data files: {len(_tokenizers_data)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('tokenizers') failed: {e}")

a = Analysis(
    ['aceforge_app.py'],
    pathex=[],
    binaries=_lzma_binaries + _tokenizers_binaries + [
        # _lzma and tokenizers binaries are collected above
        # Additional binaries can be added here if needed
    ],
    datas=[
        # Include static files (HTML, CSS, JS, images)
        (str(static_dir), 'static'),
        # Include training config JSON files
        (str(training_config_dir), 'training_config'),
        # Include ACE model documentation (not the models themselves - too large)
        (str(ace_models_dir / 'README.md'), 'ace_models'),
        (str(ace_models_dir / 'LICENSE.txt'), 'ace_models'),
        (str(ace_models_dir / 'ACE_STEP_CHANGES.txt'), 'ace_models'),
        # Include presets
        ('presets.json', '.'),
    ] + _py3langid_data + _acestep_lyrics_data + _tokenizers_data,
    hiddenimports=[
        'diffusers',
        'diffusers.loaders',
        'diffusers.loaders.single_file',
        'diffusers.loaders.ip_adapter',
        'diffusers.loaders.lora_pipeline',
        'diffusers.loaders.textual_inversion',
        'diffusers.pipelines.stable_diffusion_3',
        'diffusers.pipelines.stable_diffusion_3.pipeline_stable_diffusion_3',
        'diffusers.utils.torch_utils',
        'diffusers.utils.peft_utils',
        # Collect all transformers submodules (critical for frozen apps)
        *collect_submodules('transformers'),
        'torch',
        'torchaudio',
        # Collect all torchvision submodules (critical for transformers integration)
        *collect_submodules('torchvision'),
        'flask',
        'waitress',
        'webview',  # pywebview for native window UI (imported as 'webview')
        # Required by cdmf_pipeline_ace_step.py
        'loguru',
        'huggingface_hub',
        # ACE-Step wrapper module (imported with try/except in generate_ace.py)
        'cdmf_pipeline_ace_step',
        # Lyrics prompt model (lazily imported in cdmf_generation.py)
        'lyrics_prompt_model',
        # ACE-Step package and all its submodules (critical for frozen app)
        'acestep',
        'acestep.schedulers',
        'acestep.schedulers.scheduling_flow_match_euler_discrete',
        'acestep.schedulers.scheduling_flow_match_heun_discrete',
        'acestep.schedulers.scheduling_flow_match_pingpong',
        'acestep.language_segmentation',
        'acestep.music_dcae',
        'acestep.music_dcae.music_dcae_pipeline',
        'acestep.models',
        'acestep.models.ace_step_transformer',
        'acestep.models.lyrics_utils',
        'acestep.models.lyrics_utils.lyric_tokenizer',
        'acestep.apg_guidance',
        'acestep.cpu_offload',
        # Other dependencies
        'peft',
        'pytorch_lightning',
        'librosa',
        'soundfile',
        'einops',
        'rotary_embedding_torch',
        # Tokenizers library (required by VoiceBpeTokenizer)
        'tokenizers',
        'tokenizers.implementations',
        'tokenizers.models',
        'tokenizers.pre_tokenizers',
        'tokenizers.processors',
        'tokenizers.trainers',
        # Language detection (used by ACE-Step LangSegment)
        'py3langid',
        'py3langid.langid',
        # Standard library modules that PyInstaller sometimes misses
        'lzma',  # Required by py3langid for loading pickled models
        '_lzma',  # C extension for lzma (required on some systems)
    ],
    hookspath=['build/macos/pyinstaller_hooks'],  # Custom hooks for frozen app compatibility
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Note: matplotlib is used by some dependencies but excluded to reduce bundle size
        # If you encounter import errors, remove this exclusion
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    # Binary renamed to AceForge_bin (not AceForge) because:
    # - The main "AceForge" executable is the wrapper script (macos_terminal_launcher.sh)
    # - The wrapper opens Terminal.app and then runs launch_in_terminal.sh
    # - launch_in_terminal.sh executes this binary (AceForge_bin)
    # This architecture allows the app to launch in Terminal with visible logs
    name='AceForge_bin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Hide console window for native app experience (pywebview handles UI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AceForge',  # Collection name stays as AceForge
)

# macOS app bundle
app = BUNDLE(
    coll,
    name='AceForge.app',
    icon=str(icon_path) if icon_path.exists() else None,  # Use AceForge logo icon
    bundle_identifier='com.aceforge.app',
    info_plist={
        'CFBundleName': 'AceForge',
        'CFBundleDisplayName': 'AceForge',
        'CFBundleShortVersionString': '0.1.0-macos',
        'CFBundleVersion': '0.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
        'NSRequiresAquaSystemAppearance': False,
        # Show in dock and run in foreground (native app experience)
        'LSUIElement': False,
        'LSBackgroundOnly': False,
        'CFBundlePackageType': 'APPL',
        # Native macOS app behavior
        'NSAppTransportSecurity': {
            'NSAllowsLocalNetworking': True,  # Allow localhost connections for Flask
        },
        # The main executable will be the wrapper script added by build workflow
        'CFBundleExecutable': 'AceForge',
    },
)
