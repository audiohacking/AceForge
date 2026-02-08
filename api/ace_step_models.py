"""
ACE-Step models API: list available DiT/LM models and trigger downloads.
Uses bundled acestep15_downloader when available (always in PyInstaller app), else acestep-download on PATH.
See docs/ACE-Step-Tutorial.md (DiT Selection Summary, LM options).
"""

from pathlib import Path
import shutil
import subprocess
import sys
import threading
from typing import Optional, Tuple

from flask import Blueprint, jsonify, request

import cdmf_paths

# Bundled ACE-Step 1.5 downloader (vendored); when importable we use it so CLI is not required
def _bundled_downloader_available() -> bool:
    try:
        import acestep15_downloader.model_downloader  # noqa: F401
        return True
    except ImportError:
        return False

bp = Blueprint("api_ace_step_models", __name__)

# DiT variants from Tutorial (DiT Selection Summary). size_gb: approximate for download confirmation.
DIT_MODELS = [
    {"id": "turbo", "label": "Turbo (default)", "description": "Best balance, 8 steps", "steps": 8, "cfg": False, "size_gb": 8},
    {"id": "turbo-shift1", "label": "Turbo shift=1", "description": "Richer details", "steps": 8, "cfg": False, "size_gb": 0.5},
    {"id": "turbo-shift3", "label": "Turbo shift=3", "description": "Clearer timbre", "steps": 8, "cfg": False, "size_gb": 0.5},
    {"id": "turbo-continuous", "label": "Turbo continuous", "description": "Flexible shift 1–5", "steps": 8, "cfg": False, "size_gb": 0.5},
    {"id": "sft", "label": "SFT", "description": "50 steps, CFG", "steps": 50, "cfg": True, "size_gb": 8},
    {"id": "base", "label": "Base", "description": "50 steps, CFG; lego/extract/complete", "steps": 50, "cfg": True, "exclusive_tasks": ["lego", "extract", "complete"], "size_gb": 8},
]

# LM planner options from Tutorial. size_gb: approximate for download confirmation.
LM_MODELS = [
    {"id": "none", "label": "No LM", "size_gb": 0},
    {"id": "0.6B", "label": "0.6B", "size_gb": 2},
    {"id": "1.7B", "label": "1.7B (default)", "size_gb": 4},
    {"id": "4B", "label": "4B", "size_gb": 10},
]

# ACE-Step 1.5 CLI model ids (for acestep-download --model)
ACESTEP15_DIT_IDS = {
    "turbo": "acestep-v15-turbo",
    "turbo-shift1": "acestep-v15-turbo-shift1",
    "turbo-shift3": "acestep-v15-turbo-shift3",
    "turbo-continuous": "acestep-v15-turbo-continuous",
    "sft": "acestep-v15-sft",
    "base": "acestep-v15-base",
}
ACESTEP15_LM_IDS = {
    "0.6B": "acestep-5Hz-lm-0.6B",
    "1.7B": "acestep-5Hz-lm-1.7B",
    "4B": "acestep-5Hz-lm-4B",
}

_download_progress = {
    "running": False,
    "model": None,
    "progress": 0.0,
    "error": None,
    "current_file": None,
    "file_index": 0,
    "total_files": 0,
    "eta_seconds": None,
    "cancelled": False,
}
_download_lock = threading.Lock()
_download_cancel_requested = False


def _checkpoint_root() -> Path:
    """Checkpoints directory (models_folder/checkpoints)."""
    root = cdmf_paths.get_models_folder() / "checkpoints"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _default_dit_installed() -> bool:
    """True if current default ACE-Step checkpoint (v1 3.5B) is present."""
    try:
        from ace_model_setup import ace_models_present
        return ace_models_present()
    except Exception:
        return False


def _acestep_download_available() -> bool:
    """True if we can run ACE-Step 1.5 downloads: bundled acestep15_downloader or acestep-download on PATH."""
    if _bundled_downloader_available():
        return True
    try:
        r = subprocess.run(
            ["acestep-download", "--help"],
            capture_output=True,
            timeout=10,
            cwd=str(_checkpoint_root()),
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _download_progress_callback(file_index: int = 0, total_files: int = 0, current_file: Optional[str] = None, fraction: float = 0.0) -> None:
    """Called from downloader tqdm to update UI progress."""
    with _download_lock:
        _download_progress["file_index"] = file_index
        _download_progress["total_files"] = total_files
        _download_progress["current_file"] = current_file
        _download_progress["progress"] = fraction


def _download_cancel_check() -> bool:
    """Called from downloader; True if user requested cancel."""
    return _download_cancel_requested


def _run_download(model_id: Optional[str], checkpoints_dir: Path) -> Tuple[bool, str]:
    """
    Run download into checkpoints_dir (must be the app's path: get_models_folder()/checkpoints).
    model_id=None = main model (turbo + 1.7B LM); else ACE-Step 1.5 sub-model id.
    Returns (success, message). Uses bundled module in-process so path and detection stay in sync.
    Progress and cancel are reported via _download_progress and _download_cancel_requested.
    """
    if _bundled_downloader_available():
        from acestep15_downloader.model_downloader import (
            download_main_model,
            download_submodel,
            check_main_model_exists,
            DownloadCancelled,
        )
        checkpoints_dir.mkdir(parents=True, exist_ok=True)
        progress_cb = _download_progress_callback
        cancel_check = _download_cancel_check
        if model_id is None:
            return download_main_model(
                checkpoints_dir=checkpoints_dir,
                progress_callback=progress_cb,
                cancel_check=cancel_check,
            )
        if not check_main_model_exists(checkpoints_dir):
            ok, msg = download_main_model(
                checkpoints_dir=checkpoints_dir,
                progress_callback=progress_cb,
                cancel_check=cancel_check,
            )
            if not ok:
                return False, msg
        return download_submodel(
            model_id,
            checkpoints_dir=checkpoints_dir,
            progress_callback=progress_cb,
            cancel_check=cancel_check,
        )
    # Fallback: acestep-download on PATH (same --dir so path matches) — no progress/cancel
    cli_cmd = ["acestep-download", "--dir", str(checkpoints_dir)]
    if model_id:
        cli_cmd += ["--model", model_id, "--skip-main"]
    proc = subprocess.run(cli_cmd, capture_output=True, text=True, timeout=3600, cwd=str(checkpoints_dir))
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exited {proc.returncode}"
        return False, err
    return True, f"Downloaded to {checkpoints_dir}"


def _model_installed_15(model_id: str, kind: str) -> bool:
    """Check if a known model appears installed under checkpoints (1.5 layout or v1)."""
    root = _checkpoint_root()
    if kind == "dit":
        # Turbo is installed if we have 1.5 turbo OR the legacy v1 checkpoint (ACE-Step 3.5B)
        if model_id == "turbo":
            if _default_dit_installed():
                return True
            for name in ("acestep-v15-turbo", "turbo"):
                d = root / name
                if d.is_dir() and any(d.rglob("*.safetensors")):
                    return True
            return False
        cli_id = ACESTEP15_DIT_IDS.get(model_id)
        if not cli_id:
            return False
        for name in (cli_id, cli_id.replace("acestep-", "")):
            d = root / name
            if d.is_dir() and any(d.rglob("*.safetensors")):
                return True
        return False
    if kind == "lm":
        if model_id == "none":
            return True
        cli_id = ACESTEP15_LM_IDS.get(model_id)
        if not cli_id:
            return False
        for name in (cli_id, cli_id.replace("acestep-", "")):
            d = root / name
            if d.is_dir():
                return True
        return False
    return False


def _looks_like_model_dir(path: Path) -> bool:
    """True if path is a directory that looks like a model (has weights or known structure)."""
    if not path.is_dir():
        return False
    # Any .safetensors or model.safetensors
    if any(path.rglob("*.safetensors")):
        return True
    if any(path.rglob("model.safetensors")):
        return True
    # HF cache layout: snapshots/<hash>/ with files
    snapshots = path / "snapshots"
    if snapshots.is_dir():
        for sub in snapshots.iterdir():
            if sub.is_dir() and any(sub.rglob("*.safetensors")):
                return True
    # Non-empty dir with config/model files
    if (path / "config.json").is_file() or (path / "diffusion_pytorch_model.safetensors").is_file():
        return True
    return False


def _discover_model_dirs() -> list:
    """
    Scan checkpoints for all model-like directories (known layouts + any non-empty dir for custom models).
    Returns list of { "id": dir_name, "label": display name, "path": str, "custom": bool }.
    """
    root = _checkpoint_root()
    if not root.exists():
        return []
    known_ids = set(ACESTEP15_DIT_IDS.values()) | set(ACESTEP15_LM_IDS.values()) | {"acestep-v15-turbo", "turbo"}
    known_ids.add("models--ACE-Step--ACE-Step-v1-3.5B")  # legacy v1
    result = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith(".") or name in ("blobs", "refs"):
            continue
        # Include if it looks like a model OR is non-empty (custom trained / any folder user added)
        if not _looks_like_model_dir(child) and not any(child.iterdir()):
            continue
        # Human-readable label
        if name == "models--ACE-Step--ACE-Step-v1-3.5B":
            label = "ACE-Step v1 3.5B (legacy)"
        elif name.startswith("acestep-"):
            label = name.replace("acestep-", "").replace("-", " ")
        elif name.startswith("models--"):
            label = name.replace("models--", "").replace("--", " / ")
        else:
            label = name
        result.append({
            "id": name,
            "label": label,
            "path": str(child),
            "custom": name not in known_ids,
        })
    return sorted(result, key=lambda x: (x["custom"], x["label"].lower()))


@bp.route("/models", methods=["GET"])
@bp.route("/models/", methods=["GET"])
def list_models():
    """
    GET /api/ace-step/models
    Returns known DiT/LM models with installed status plus all discovered model dirs on disk (custom/trained).
    """
    use_15 = _acestep_download_available()
    # Known DiT: always include; installed = on disk (1.5 layout or v1 legacy)
    dit = []
    for m in DIT_MODELS:
        installed = _model_installed_15(m["id"], "dit") if use_15 else (m["id"] == "turbo" and _default_dit_installed())
        dit.append({**m, "installed": installed})
    # Known LM
    lm = []
    for m in LM_MODELS:
        installed = _model_installed_15(m["id"], "lm") if use_15 else (m["id"] == "none")
        lm.append({**m, "installed": installed})
    # All model dirs found under checkpoints (custom trained, v1, 1.5, etc.)
    discovered = _discover_model_dirs()
    return jsonify({
        "dit_models": dit,
        "lm_models": lm,
        "discovered_models": discovered,
        "acestep_download_available": use_15,
        "checkpoints_path": str(_checkpoint_root()),
    })


def _do_download_worker(model: str, root: Path) -> None:
    """Background thread: run the actual download and update _download_progress."""
    global _download_cancel_requested
    try:
        from acestep15_downloader.model_downloader import DownloadCancelled
        if model in ("turbo", "default", "") and not _acestep_download_available():
            from ace_model_setup import ensure_ace_models
            ensure_ace_models()
            with _download_lock:
                _download_progress["running"] = False
                _download_progress["progress"] = 1.0
                _download_progress["error"] = None
            return
        if model in ACESTEP15_DIT_IDS or model in ACESTEP15_LM_IDS:
            cli_id = ACESTEP15_DIT_IDS.get(model) or ACESTEP15_LM_IDS.get(model) or model
            success, msg = _run_download(cli_id, root)
        elif model in ("turbo", "default", ""):
            success, msg = _run_download(None, root)
        else:
            with _download_lock:
                _download_progress["running"] = False
                _download_progress["error"] = f"Unknown model: {model}"
            return
        with _download_lock:
            _download_progress["running"] = False
            _download_progress["progress"] = 1.0
            _download_progress["error"] = None if success else msg
            _download_progress["current_file"] = None
            _download_progress["file_index"] = 0
            _download_progress["total_files"] = 0
    except Exception as e:
        with _download_lock:
            try:
                from acestep15_downloader.model_downloader import DownloadCancelled
                cancelled = isinstance(e, DownloadCancelled)
            except ImportError:
                cancelled = False
            _download_progress["running"] = False
            _download_progress["cancelled"] = cancelled
            _download_progress["error"] = "Cancelled by user" if cancelled else str(e)
    finally:
        _download_cancel_requested = False


@bp.route("/models/disk-space", methods=["GET"])
def disk_space():
    """
    GET /api/ace-step/models/disk-space
    Returns free and total disk space for the models/checkpoints path (for download confirmation).
    """
    try:
        root = _checkpoint_root()
        root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(str(root))
        free_gb = round(usage.free / (1024 ** 3), 2)
        total_gb = round(usage.total / (1024 ** 3), 2)
        return jsonify({"free_gb": free_gb, "total_gb": total_gb, "path": str(root)})
    except Exception as e:
        return jsonify({"error": str(e), "free_gb": None, "total_gb": None, "path": ""}), 500


@bp.route("/models/download", methods=["POST"])
def download_model():
    """
    POST /api/ace-step/models/download
    Body: { "model": "turbo" | "acestep-v15-turbo" | "acestep-5Hz-lm-1.7B" | ... }
    Starts download in background; returns immediately with started=True. Poll GET /models/status for progress.
    """
    data = request.get_json(silent=True) or {}
    model = (data.get("model") or "").strip()
    if not model:
        return jsonify({"error": "Missing 'model' in body"}), 400

    with _download_lock:
        if _download_progress["running"]:
            return jsonify({"error": "A download is already in progress", "model": _download_progress["model"]}), 409
        _download_cancel_requested = False
        _download_progress["running"] = True
        _download_progress["model"] = model
        _download_progress["progress"] = 0.0
        _download_progress["error"] = None
        _download_progress["current_file"] = None
        _download_progress["file_index"] = 0
        _download_progress["total_files"] = 0
        _download_progress["eta_seconds"] = None
        _download_progress["cancelled"] = False

    root = _checkpoint_root()
    # Fast path: default turbo when 1.5 not available (sync, no thread)
    if model in ("turbo", "default", "") and not _acestep_download_available():
        try:
            from ace_model_setup import ensure_ace_models
            ensure_ace_models()
            with _download_lock:
                _download_progress["running"] = False
                _download_progress["progress"] = 1.0
            return jsonify({"ok": True, "started": False, "model": "turbo", "path": str(root)})
        except Exception as e:
            with _download_lock:
                _download_progress["running"] = False
                _download_progress["error"] = str(e)
            return jsonify({"error": str(e), "model": model}), 500
    # 1.5 not available for other models
    if model not in ("turbo", "default", "") and model not in ACESTEP15_DIT_IDS and model not in ACESTEP15_LM_IDS:
        with _download_lock:
            _download_progress["running"] = False
        return jsonify({"error": f"Unknown model: {model}", "model": model}), 400
    if (model in ACESTEP15_DIT_IDS or model in ACESTEP15_LM_IDS or model in ("turbo", "default", "")) and not _acestep_download_available():
        with _download_lock:
            _download_progress["running"] = False
        return jsonify({
            "error": "ACE-Step 1.5 downloader not available. In the app bundle it is always included.",
            "hint": "See https://github.com/ace-step/ACE-Step-1.5",
        }), 501

    def run():
        _do_download_worker(model, root)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return jsonify({"ok": True, "started": True, "model": model, "path": str(root)})


@bp.route("/models/download/cancel", methods=["POST"])
def download_cancel():
    """POST /api/ace-step/models/download/cancel — request cancellation of the current download."""
    global _download_cancel_requested
    with _download_lock:
        if not _download_progress["running"]:
            return jsonify({"cancelled": False, "message": "No download in progress"})
        _download_cancel_requested = True
    return jsonify({"cancelled": True, "message": "Cancel requested; download will stop after the current file."})


@bp.route("/models/status", methods=["GET"])
def download_status():
    """GET /api/ace-step/models/status — current download progress (if any)."""
    with _download_lock:
        return jsonify({
            "running": _download_progress["running"],
            "model": _download_progress["model"],
            "progress": _download_progress["progress"],
            "error": _download_progress["error"],
            "current_file": _download_progress["current_file"],
            "file_index": _download_progress["file_index"],
            "total_files": _download_progress["total_files"],
            "eta_seconds": _download_progress["eta_seconds"],
            "cancelled": _download_progress["cancelled"],
        })
