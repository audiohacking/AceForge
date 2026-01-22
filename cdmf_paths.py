# C:\AceForge\cdmf_paths.py

from __future__ import annotations

from pathlib import Path
import sys
import json
import os

# Import user directories module for OSX-compliant paths
from cdmf_user_dirs import (
    get_app_dir,
    get_user_preferences_dir,
    get_user_app_support_dir,
    ensure_user_directories
)

# ---------------------------------------------------------------------------
# Core paths and directories (shared across modules)
# ---------------------------------------------------------------------------

# APP_DIR is now the bundled app directory (for reading bundled resources)
APP_DIR = get_app_dir()

# Initialize user directories (including migration from legacy locations)
ensure_user_directories()

# Get user-specific directories following OSX conventions
USER_PREFS_DIR = get_user_preferences_dir()
USER_SUPPORT_DIR = get_user_app_support_dir()

# Configuration file for user settings (now in Preferences)
CONFIG_PATH = USER_PREFS_DIR / "aceforge_config.json"

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
    """Get the configured models folder path, or default to user Application Support."""
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
    
    # Default path is now in user Application Support
    default_path = USER_SUPPORT_DIR / "ace_models"
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

# Where finished tracks go (now in user Application Support)
DEFAULT_OUT_DIR = str(USER_SUPPORT_DIR / "generated")

# Presets / tracks metadata / user presets (now in user Preferences)
# Try user preferences first, fall back to bundled presets for reading
PRESETS_PATH = USER_PREFS_DIR / "presets.json"
# If user presets don't exist, copy from bundled version
if not PRESETS_PATH.exists():
    bundled_presets = APP_DIR / "presets.json"
    if bundled_presets.exists():
        try:
            import shutil
            shutil.copy2(bundled_presets, PRESETS_PATH)
        except Exception:
            # If copy fails, just use bundled path for reading
            PRESETS_PATH = bundled_presets

TRACK_META_PATH = USER_PREFS_DIR / "tracks_meta.json"
USER_PRESETS_PATH = USER_PREFS_DIR / "user_presets.json"

# Shared location for ACE-Step base model weights used by the LoRA trainer.
ACE_TRAINER_MODEL_ROOT = USER_SUPPORT_DIR / "ace_models"
ACE_TRAINER_MODEL_ROOT.mkdir(parents=True, exist_ok=True)

# Root for all ACE-Step training datasets (LoRA + MuFun).
TRAINING_DATA_ROOT = USER_SUPPORT_DIR / "training_datasets"
TRAINING_DATA_ROOT.mkdir(parents=True, exist_ok=True)

# Training configs (JSON files for LoRA hyperparameters)
TRAINING_CONFIG_ROOT = USER_SUPPORT_DIR / "training_config"
TRAINING_CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
DEFAULT_LORA_CONFIG = TRAINING_CONFIG_ROOT / "default_config.json"

# Where custom LoRA adapters live
CUSTOM_LORA_ROOT = USER_SUPPORT_DIR / "custom_lora"
CUSTOM_LORA_ROOT.mkdir(parents=True, exist_ok=True)

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
