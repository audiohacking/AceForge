# C:\AceForge\cdmf_paths.py

from __future__ import annotations

from pathlib import Path
import sys
import json
import os
import platform

# ---------------------------------------------------------------------------
# Core paths and directories (shared across modules)
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).parent.resolve()

def get_user_preferences_dir() -> Path:
    """
    Get the user preferences directory following platform conventions.
    - macOS: ~/Library/Preferences/com.audiohacking.AceForge/
    - Windows/Linux: APP_DIR (fallback to app directory)
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        pref_dir = Path.home() / "Library" / "Preferences" / "com.audiohacking.AceForge"
        pref_dir.mkdir(parents=True, exist_ok=True)
        return pref_dir
    # Fallback for Windows/Linux: use app directory
    return APP_DIR

def get_user_data_dir() -> Path:
    """
    Get the user data directory following platform conventions.
    - macOS: ~/Library/Application Support/AceForge/
    - Windows/Linux: APP_DIR (fallback to app directory)
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        data_dir = Path.home() / "Library" / "Application Support" / "AceForge"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    # Fallback for Windows/Linux: use app directory
    return APP_DIR

# Configuration file for user settings
CONFIG_PATH = get_user_preferences_dir() / "aceforge_config.json"

def load_config() -> dict:
    """Load configuration from aceforge_config.json or return defaults."""
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                config = json.load(f)
                return config
        except Exception as e:
            print(f"[AceForge] Warning: Failed to load config: {e}", flush=True)
    return {}

def save_config(config: dict) -> None:
    """Save configuration to aceforge_config.json."""
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[AceForge] Warning: Failed to save config: {e}", flush=True)

def get_models_folder() -> Path:
    """
    Get the configured models folder path, or default based on platform:
    - macOS: ~/Library/Application Support/AceForge/models/
    - Windows/Linux: APP_DIR / ace_models
    """
    config = load_config()
    models_path = config.get("models_folder")
    if models_path:
        path = Path(models_path)
        # Validate that the path exists or can be created
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception as e:
            print(f"[AceForge] Warning: Cannot use configured models folder {models_path}: {e}", flush=True)
            print("[AceForge] Falling back to default models folder.", flush=True)
    
    # Default path based on platform
    system = platform.system()
    if system == "Darwin":  # macOS
        default_path = get_user_data_dir() / "models"
    else:
        # Windows/Linux: use app directory
        default_path = APP_DIR / "ace_models"
    
    default_path.mkdir(parents=True, exist_ok=True)
    return default_path

def set_models_folder(path: str) -> bool:
    """Set the models folder path in configuration."""
    try:
        path_obj = Path(path).resolve()
        # Try to create the directory to validate the path
        path_obj.mkdir(parents=True, exist_ok=True)
        
        config = load_config()
        config["models_folder"] = str(path_obj)
        save_config(config)
        
        # Update environment variable for HF_HOME
        os.environ["HF_HOME"] = str(path_obj)
        
        return True
    except Exception as e:
        print(f"[AceForge] Error setting models folder: {e}", flush=True)
        return False

# Where finished tracks go
def _get_default_output_dir() -> Path:
    """Get default output directory based on platform."""
    system = platform.system()
    if system == "Darwin":  # macOS
        output_dir = get_user_data_dir() / "generated"
    else:
        output_dir = APP_DIR / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir

DEFAULT_OUT_DIR = str(_get_default_output_dir())

# Presets / tracks metadata / user presets  
# Keep these in APP_DIR as they're bundled with the application
# User presets go in user data directory
PRESETS_PATH = APP_DIR / "presets.json"
TRACK_META_PATH = get_user_data_dir() / "tracks_meta.json" if platform.system() == "Darwin" else APP_DIR / "tracks_meta.json"
USER_PRESETS_PATH = get_user_data_dir() / "user_presets.json" if platform.system() == "Darwin" else APP_DIR / "user_presets.json"

# Shared location for ACE-Step base model weights used by the LoRA trainer.
# Use the same location as get_models_folder() for consistency
ACE_TRAINER_MODEL_ROOT = get_models_folder()

# Root for all ACE-Step training datasets (LoRA + MuFun).
def _get_training_data_root() -> Path:
    """Get training data root directory based on platform."""
    system = platform.system()
    if system == "Darwin":  # macOS
        training_dir = get_user_data_dir() / "training_datasets"
    else:
        training_dir = APP_DIR / "training_datasets"
    training_dir.mkdir(parents=True, exist_ok=True)
    return training_dir

TRAINING_DATA_ROOT = _get_training_data_root()

# Training configs (JSON files for LoRA hyperparameters)
# Keep these in APP_DIR as they're bundled configuration templates
TRAINING_CONFIG_ROOT = APP_DIR / "training_config"
TRAINING_CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
DEFAULT_LORA_CONFIG = TRAINING_CONFIG_ROOT / "default_config.json"

# Where custom LoRA adapters live
def _get_custom_lora_root() -> Path:
    """Get custom LoRA adapters directory based on platform."""
    system = platform.system()
    if system == "Darwin":  # macOS
        lora_dir = get_user_data_dir() / "custom_lora"
    else:
        lora_dir = APP_DIR / "custom_lora"
    lora_dir.mkdir(parents=True, exist_ok=True)
    return lora_dir

CUSTOM_LORA_ROOT = _get_custom_lora_root()

# Seed vibes (these should match ACE_VIBE_TAGS in generate_ace.py)
SEED_VIBES = [
    ("any", "Any / Auto"),
    ("lofi_dreamy", "Lo-fi & Dreamy"),
    ("chiptunes_upbeat", "Chiptunes – Upbeat"),
    ("chiptunes_zelda", "Chiptunes – Legend of Zelda Fusion"),
    ("fantasy", "Fantasy / Orchestral"),
    ("cyberpunk", "Cyberpunk / Synthwave"),
    ("misc", "Misc / Other"),
]

# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------

def get_app_version() -> str:
    """
    Read the application version from VERSION file.
    Falls back to 'v0.1' if file doesn't exist or can't be read.
    The VERSION file is updated by GitHub Actions during release builds.
    """
    version_file = APP_DIR / "VERSION"
    if version_file.exists():
        try:
            with version_file.open("r", encoding="utf-8") as f:
                version = f.read().strip()
                if version:
                    return version
        except Exception as e:
            print(f"[AceForge] Warning: Failed to read VERSION file: {e}", flush=True)
    # Default fallback
    return "v0.1"

APP_VERSION = get_app_version()
