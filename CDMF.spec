# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for AceForge (macOS)

import sys
from pathlib import Path

block_cipher = None

# Determine paths
spec_root = Path(SPECPATH)
static_dir = spec_root / 'static'
training_config_dir = spec_root / 'training_config'
ace_models_dir = spec_root / 'ace_models'

a = Analysis(
    ['music_forge_ui.py'],
    pathex=[],
    binaries=[],
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
    ],
    hiddenimports=[
        'diffusers',
        'transformers',
        'torch',
        'torchaudio',
        'torchvision',
        'flask',
        'waitress',
        'acestep',
        'peft',
        'pytorch_lightning',
        'librosa',
        'soundfile',
        'einops',
        'rotary_embedding_torch',
    ],
    hookspath=[],
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
    name='AceForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Keep console for server logs
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
    name='AceForge',
)

# macOS app bundle
app = BUNDLE(
    coll,
    name='AceForge.app',
    icon=None,  # Add icon path if you have a .icns file
    bundle_identifier='com.aceforge.app',
    info_plist={
        'CFBundleName': 'AceForge',
        'CFBundleDisplayName': 'AceForge',
        'CFBundleShortVersionString': '0.1.0-macos',
        'CFBundleVersion': '0.1.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '12.0',
        'NSRequiresAquaSystemAppearance': False,
    },
)
