# C:\AceForge\cdmf_state.py

from __future__ import annotations

import threading
import time
from typing import Optional, Dict, Any

from ace_model_setup import ace_models_present


# ---------------------------------------------------------------------------
# Generation progress (shared with /progress endpoint and model downloads)
# ---------------------------------------------------------------------------

PROGRESS_LOCK = threading.Lock()
GENERATION_PROGRESS: Dict[str, Any] = {
    "current": 0.0,
    "total": 1.0,
    "stage": "",
    "done": False,
    "error": False,
}

# Track that was last successfully generated into DEFAULT_OUT_DIR
LAST_GENERATED_TRACK: Optional[str] = None

# ---------------------------------------------------------------------------
# ACE-Step model availability (lazy download via UI)
# ---------------------------------------------------------------------------

MODEL_LOCK = threading.Lock()
MODEL_STATUS: Dict[str, Any] = {
    # "ready"        -> model is present on disk
    # "absent"       -> no model yet
    # "downloading"  -> background download in progress
    # "error"        -> last download attempt failed
    # "unknown"      -> initial state before we probe disk
    "state": "unknown",
    "message": "",
}

# ---------------------------------------------------------------------------
# MuFun-ACEStep analysis model availability
# ---------------------------------------------------------------------------

MUFUN_LOCK = threading.Lock()
MUFUN_STATUS: Dict[str, Any] = {
    "state": "unknown",
    "message": "",
}

# ---------------------------------------------------------------------------
# Training state (ACE-Step LoRA)
# ---------------------------------------------------------------------------

TRAIN_LOCK = threading.Lock()
TRAIN_STATE: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "last_update": None,
    "last_message": "",
    "finished_at": None,
    "returncode": None,
    "error": None,
    "exp_name": None,
    "dataset_path": None,
    "lora_config_path": None,
    "pid": None,
    "log_path": None,
    # Progress fields
    "progress": 0.0,        # 0.0 - 1.0
    "max_steps": None,
    "max_epochs": None,
    "current_epoch": None,
    "current_step": None,
}


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def reset_progress() -> None:
    with PROGRESS_LOCK:
        GENERATION_PROGRESS["current"] = 0.0
        GENERATION_PROGRESS["total"] = 1.0
        GENERATION_PROGRESS["stage"] = ""
        GENERATION_PROGRESS["done"] = False
        GENERATION_PROGRESS["error"] = False


def mark_running(stage: str = "ACE") -> None:
    with PROGRESS_LOCK:
        GENERATION_PROGRESS["current"] = 0.0
        GENERATION_PROGRESS["total"] = 1.0
        GENERATION_PROGRESS["stage"] = stage
        GENERATION_PROGRESS["done"] = False
        GENERATION_PROGRESS["error"] = False


def mark_done(stage: str = "done") -> None:
    with PROGRESS_LOCK:
        GENERATION_PROGRESS["current"] = 1.0
        GENERATION_PROGRESS["total"] = 1.0
        GENERATION_PROGRESS["stage"] = stage
        GENERATION_PROGRESS["done"] = True
        GENERATION_PROGRESS["error"] = False


def ace_progress_callback(fraction: float, stage: str) -> None:
    """
    Callback invoked from generate_ace.generate_track_ace to update UI progress.
    This is wired via register_progress_callback() in music_forge_ui.py.
    """
    with PROGRESS_LOCK:
        try:
            frac = max(0.0, min(1.0, float(fraction)))
        except Exception:
            frac = 0.0
        GENERATION_PROGRESS["current"] = frac
        GENERATION_PROGRESS["total"] = 1.0
        GENERATION_PROGRESS["stage"] = stage or "ace"
        GENERATION_PROGRESS["done"] = False
        GENERATION_PROGRESS["error"] = False


def model_download_progress_cb(fraction: float) -> None:
    """
    Progress callback used while the ACE-Step model is being downloaded by
    ace_model_setup.ensure_ace_models(). This drives the same progress bar
    that generation uses, but with a distinct stage label.
    """
    with PROGRESS_LOCK:
        try:
            frac = max(0.0, min(1.0, float(fraction)))
        except Exception:
            frac = 0.0

        # Leave a bit of headroom so we still visibly "finish" at 1.0 later.
        frac = 0.05 + 0.9 * frac  # map 0..1 → 0.05..0.95

        GENERATION_PROGRESS["current"] = frac
        GENERATION_PROGRESS["total"] = 1.0
        GENERATION_PROGRESS["stage"] = "ace_model_download"
        GENERATION_PROGRESS["done"] = False
        GENERATION_PROGRESS["error"] = False


# ---------------------------------------------------------------------------
# Model status initialization
# ---------------------------------------------------------------------------

def init_model_status() -> None:
    """
    Initialize MODEL_STATUS based on whether the ACE-Step model is already
    present on disk. This is a quick, non-network check used before the
    first page render.
    """
    if ace_models_present():
        with MODEL_LOCK:
            MODEL_STATUS["state"] = "ready"
            MODEL_STATUS["message"] = "ACE-Step model is present."
    else:
        with MODEL_LOCK:
            if MODEL_STATUS["state"] == "unknown":
                MODEL_STATUS["state"] = "absent"
                MODEL_STATUS["message"] = "ACE-Step model has not been downloaded yet."
