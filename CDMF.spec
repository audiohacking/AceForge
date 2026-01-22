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
icon_path = spec_root / 'build' / 'macos' / 'AceForge.icns'

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
        # Show in dock and run in foreground
        'LSUIElement': False,
        'LSBackgroundOnly': False,
        'CFBundlePackageType': 'APPL',
        # The main executable will be the wrapper script added by build workflow
        'CFBundleExecutable': 'AceForge',
    },
)
