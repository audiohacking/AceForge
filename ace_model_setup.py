from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional, Callable

from huggingface_hub import snapshot_download

# Hugging Face repo for ACE-Step
ACE_REPO_ID = "ACE-Step/ACE-Step-v1-3.5B"

# Root folder we use as Hugging Face "cache_dir" for ACE-Step.
# This will contain the usual HF layout:
#   ace_models/checkpoints/
#     blobs/
#     models--ACE-Step--ACE-Step-v1-3.5B/
#       snapshots/<rev-hash>/
ACE_CHECKPOINT_ROOT = (
    Path(__file__).resolve().parent / "ace_models" / "checkpoints"
)

# Name HF uses for the repo under the cache root
ACE_LOCAL_DIRNAME = "models--ACE-Step--ACE-Step-v1-3.5B"

ProgressCallback = Callable[[float], None]


def _build_tqdm_with_progress_cb(progress_cb: ProgressCallback):
    """
    Build a tqdm subclass that forwards overall progress [0, 1] to
    the given callback. Used so the Flask UI can show real download progress.
    """
    from tqdm.auto import tqdm as base_tqdm

    class HFProgressTqdm(base_tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Initial ping at 0%
            try:
                progress_cb(0.0)
            except Exception:
                pass

        def update(self, n=1):
            res = super().update(n)
            try:
                total = float(self.total or 0.0)
                if total > 0:
                    frac = float(self.n) / total
                    frac = max(0.0, min(1.0, frac))
                    progress_cb(frac)
            except Exception:
                # Never let progress reporting break the download
                pass
            return res

    return HFProgressTqdm


def _ace_repo_dir() -> Path:
    """
    Directory where Hugging Face will place the ACE-Step repo
    under our ACE_CHECKPOINT_ROOT.
    """
    return ACE_CHECKPOINT_ROOT / ACE_LOCAL_DIRNAME


def ace_models_present() -> bool:
    """
    Lightweight check: treat the model as present if we can find at least
    one *.safetensors weight file anywhere under ACE_CHECKPOINT_ROOT,
    without triggering any network downloads.
    """
    root = ACE_CHECKPOINT_ROOT
    if not root.is_dir():
        return False

    repo_dir = _ace_repo_dir()
    if repo_dir.is_dir():
        for p in repo_dir.rglob("model.safetensors"):
            return True

    # Fallback: catch any older layouts just in case
    for p in root.rglob("model.safetensors"):
        return True

    return False


def ensure_ace_models(progress_cb: Optional[ProgressCallback] = None) -> Path:
    """
    Ensure the ACE-Step model is present under ace_models/checkpoints.
    Returns the path to the repo dir:
      ace_models/checkpoints/models--ACE-Step--ACE-Step-v1-3.5B

    If `progress_cb` is provided, it will be called with a float in [0, 1]
    reflecting approximate snapshot_download progress.
    """
    target_dir = ACE_CHECKPOINT_ROOT / ACE_LOCAL_DIRNAME

    # If it's already there and non-empty, we're done.
    if target_dir.is_dir() and any(target_dir.iterdir()):
        if progress_cb is not None:
            try:
                progress_cb(1.0)
            except Exception:
                pass
        return target_dir

    print("[CDMF] ACE-Step model not found at:")
    print(f"       {target_dir}")
    print("[CDMF] Downloading from Hugging Face repo:", ACE_REPO_ID)
    print("[CDMF] This is a large download (multiple GB). Please wait...")

    # Ensure parent exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Build a tqdm_class for real progress if requested
    if progress_cb is not None:
        tqdm_class = _build_tqdm_with_progress_cb(progress_cb)
    else:
        tqdm_class = None

    try:
        kwargs = {
            "repo_id": ACE_REPO_ID,
            "local_dir": str(target_dir),
            # local_dir_use_symlinks deprecated; new behavior copies into local_dir
        }
        if tqdm_class is not None:
            kwargs["tqdm_class"] = tqdm_class

        downloaded_path = Path(snapshot_download(**kwargs))
    except TypeError as t_err:
        # Older huggingface_hub may not support tqdm_class.
        # Fall back to a plain download; progress just won't be mirrored.
        print(
            "[CDMF] WARNING: snapshot_download() does not support tqdm_class; "
            "download progress will not be reflected precisely:", t_err
        )
        downloaded_path = Path(
            snapshot_download(
                repo_id=ACE_REPO_ID,
                local_dir=str(target_dir),
            )
        )
    except Exception as exc:
        print("[CDMF] ERROR: Failed to download ACE-Step model:", exc)
        print("       If you already downloaded it manually,")
        print("       place the model contents here:")
        print(f"       {target_dir}")
        raise


if __name__ == "__main__":
    # Allow you to run this manually if needed
    try:
        path = ensure_ace_models()
    except Exception:
        sys.exit(1)
    else:
        print("[CDMF] Model cache ready at:", path)