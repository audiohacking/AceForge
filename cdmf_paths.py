# C:\AceForge\cdmf_paths.py

from __future__ import annotations

from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Core paths and directories (shared across modules)
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).parent.resolve()

# Where finished tracks go
DEFAULT_OUT_DIR = str(APP_DIR / "generated")

# Presets / tracks metadata / user presets
PRESETS_PATH = APP_DIR / "presets.json"
TRACK_META_PATH = APP_DIR / "tracks_meta.json"
USER_PRESETS_PATH = APP_DIR / "user_presets.json"

# Shared location for ACE-Step base model weights used by the LoRA trainer.
ACE_TRAINER_MODEL_ROOT = APP_DIR / "ace_models"
ACE_TRAINER_MODEL_ROOT.mkdir(parents=True, exist_ok=True)

# Root for all ACE-Step training datasets (LoRA + MuFun).
TRAINING_DATA_ROOT = APP_DIR / "training_datasets"
TRAINING_DATA_ROOT.mkdir(parents=True, exist_ok=True)

# Training configs (JSON files for LoRA hyperparameters)
TRAINING_CONFIG_ROOT = APP_DIR / "training_config"
TRAINING_CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
DEFAULT_LORA_CONFIG = TRAINING_CONFIG_ROOT / "default_config.json"

# Where custom LoRA adapters live
CUSTOM_LORA_ROOT = APP_DIR / "custom_lora"
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
