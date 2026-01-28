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

# Collect data files for basic-pitch (MIDI generation - optional component)
_basic_pitch_data = []
try:
    _basic_pitch_data = collect_data_files('basic_pitch')
    if _basic_pitch_data:
        print(f"[CDMF.spec] Collected basic_pitch data files: {len(_basic_pitch_data)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('basic_pitch') failed: {e} (basic-pitch may not be installed)")

# Collect data files for TTS (voice cloning - optional component)
_tts_data = []
try:
    _tts_data = collect_data_files('TTS')
    if _tts_data:
        print(f"[CDMF.spec] Collected TTS data files: {len(_tts_data)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('TTS') failed: {e} (TTS may not be installed)")

# TTS/vocoder/configs/__init__.py runs os.listdir(os.path.dirname(__file__)) at import; that dir must exist on disk.
# collect_data_files does not include .py; add vocoder configs as datas so .../TTS/vocoder/configs/ exists.
_tts_vocoder_configs = []
try:
    import TTS.vocoder.configs as _voc_cfg
    _vcd = os.path.dirname(_voc_cfg.__file__)
    for _f in os.listdir(_vcd):
        if _f.endswith(".py"):
            _tts_vocoder_configs.append((os.path.join(_vcd, _f), "TTS/vocoder/configs"))
    if _tts_vocoder_configs:
        print(f"[CDMF.spec] Collected TTS/vocoder/configs: {len(_tts_vocoder_configs)} .py files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: TTS vocoder configs: {e} (TTS may not be installed)")

# Collect data files for trainer (TTS dependency - includes VERSION file)
_trainer_data = []
try:
    _trainer_data = collect_data_files('trainer')
    if _trainer_data:
        print(f"[CDMF.spec] Collected trainer data files: {len(_trainer_data)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('trainer') failed: {e} (trainer may not be installed)")

# Collect data files for gruut (TTS phonemizer - must include VERSION; else "No such file or directory: .../gruut/VERSION")
_gruut_data = []
try:
    _gruut_data = collect_data_files('gruut')
    if _gruut_data:
        print(f"[CDMF.spec] Collected gruut data files: {len(_gruut_data)} files (incl. VERSION)")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('gruut') failed: {e} (TTS/gruut may not be installed)")

# Collect data files for jamo (TTS/Korean phonemizer - needs data/U+11xx.json, U+31xx.json)
_jamo_data = []
try:
    _jamo_data = collect_data_files('jamo')
    if _jamo_data:
        print(f"[CDMF.spec] Collected jamo data files: {len(_jamo_data)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('jamo') failed: {e} (TTS/jamo may not be installed)")

# Collect dynamic libraries for TTS (if available)
_tts_binaries = []
try:
    _tts_binaries = collect_dynamic_libs('TTS')
    if _tts_binaries:
        print(f"[CDMF.spec] Collected TTS binaries: {len(_tts_binaries)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_dynamic_libs('TTS') failed: {e} (TTS may not be installed)")

# Collect data files for Demucs (stem splitting - optional component)
_demucs_data = []
try:
    _demucs_data = collect_data_files('demucs')
    if _demucs_data:
        print(f"[CDMF.spec] Collected demucs data files: {len(_demucs_data)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_data_files('demucs') failed: {e} (Demucs may not be installed)")

# Collect dynamic libraries for Demucs (if available)
_demucs_binaries = []
try:
    _demucs_binaries = collect_dynamic_libs('demucs')
    if _demucs_binaries:
        print(f"[CDMF.spec] Collected demucs binaries: {len(_demucs_binaries)} files")
except Exception as e:
    print(f"[CDMF.spec] WARNING: collect_dynamic_libs('demucs') failed: {e} (Demucs may not be installed)")

a = Analysis(
    ['aceforge_app.py'],
    pathex=[],
    binaries=_lzma_binaries + _tokenizers_binaries + _tts_binaries + _demucs_binaries + [
        # _lzma, tokenizers, TTS, and Demucs binaries are collected above
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
        # Include VERSION file (placed in MacOS directory for frozen apps)
        ('VERSION', '.'),
    ] + _py3langid_data + _acestep_lyrics_data + _tokenizers_data + _basic_pitch_data + _tts_data + _tts_vocoder_configs + _trainer_data + _gruut_data + _jamo_data + _demucs_data,
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
        'pydub',  # Voice cloning: convert MP3/M4A/FLAC to WAV for TTS
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
        # Voice cloning (TTS library - must be installed in build env and in hiddenimports)
        'cdmf_ffmpeg',  # PATH fix for ffprobe/ffmpeg when .app has minimal PATH
        'cdmf_voice_cloning',
        'cdmf_voice_cloning_bp',
        'TTS',
        'TTS.api',
        # Collect all TTS submodules (critical for frozen apps)
        *collect_submodules('TTS'),
        # Stem splitting (Demucs library - optional component)
        'cdmf_stem_splitting',
        'cdmf_stem_splitting_bp',
        'demucs',
        'demucs.separate',
        'demucs.pretrained',
        # Collect all demucs submodules (critical for frozen apps)
        *collect_submodules('demucs'),
        # MIDI generation (basic-pitch library - optional component)
        'cdmf_midi_generation',
        'cdmf_midi_generation_bp',
        'midi_model_setup',
        'basic_pitch',
        'basic_pitch.inference',
        'basic_pitch.note_creation',
        'basic_pitch.constants',
        'basic_pitch.commandline_printing',
        # Collect all basic_pitch submodules (critical for frozen apps)
        *collect_submodules('basic_pitch'),
        # TTS dependencies that might be missed by PyInstaller
        'coqpit',
        'trainer',
        'pysbd',
        'inflect',
        'unidecode',
        'anyascii',  # Required by TTS.tts.utils.text
        'bangla',  # Required by TTS.tts.utils.text.phonemizers (Bangla)
        'jamo',  # Required by TTS/Korean phonemizer (needs data/*.json)
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
    # For serverless pywebview app: binary is AceForge_bin internally,
    # but will be copied/renamed to AceForge in the app bundle
    # This is the main entry point (aceforge_app.py) - no Flask, no terminal
    name='AceForge_bin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Hide console window - pywebview provides native UI
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
        # CFBundleExecutable: build_local and build-release.yml copy AceForge_bin→AceForge
        'CFBundleExecutable': 'AceForge',
    },
)
