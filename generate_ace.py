from __future__ import annotations

import os
import sys
import random
import threading
import inspect
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List

# Make HF Hub use real files instead of symlinks (Windows privilege issue)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

from pydub import AudioSegment
from ace_model_setup import ensure_ace_models

# ---------------------------------------------------------------------------
#  Torchaudio → WAV shim (bypass torchcodec / FFmpeg issues)
# ---------------------------------------------------------------------------
try:
    import torch
    import torchaudio
    import wave
    import numpy as np

    def _candy_torchaudio_save(
        filepath,
        src,
        sample_rate: int,
        format: str | None = None,
        backend: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Minimal replacement for torchaudio.save that writes 16-bit PCM WAVs
        without going through torchcodec / FFmpeg.

        Only intended for the ACE-Step pipeline in this app.
        """
        if src is None:
            raise ValueError("torchaudio.save: got None tensor")

        # src is typically [channels, num_samples] (or [num_samples] / [B, C, T])
        if hasattr(src, "detach"):
            wav = src.detach().cpu()
        else:
            raise TypeError("torchaudio.save: expected a torch.Tensor-like object")

        if wav.ndim == 1:
            wav = wav.unsqueeze(0)          # [T] -> [1, T]
        elif wav.ndim == 3:
            wav = wav[0]                    # [B, C, T] -> [C, T]

        if wav.ndim != 2:
            raise ValueError(f"torchaudio.save: unexpected tensor shape {tuple(wav.shape)}")

        # Clamp to [-1, 1] and convert to int16 PCM
        wav = wav.clamp(-1.0, 1.0)
        wav_i16 = (wav * 32767.0).to(torch.int16).numpy()
        channels, num_samples = wav_i16.shape

        # Ensure parent dir exists
        parent = os.path.dirname(str(filepath)) or "."
        os.makedirs(parent, exist_ok=True)

        # Write a vanilla RIFF/WAVE file
        with wave.open(str(filepath), "wb") as fh:
            fh.setnchannels(int(channels))
            fh.setsampwidth(2)  # 16-bit
            fh.setframerate(int(sample_rate))
            fh.writeframes(wav_i16.T.tobytes())

    def _candy_torchaudio_load(
        filepath,
        frame_offset: int = 0,
        num_frames: int = -1,
        normalize: bool = True,
        channels_first: bool = True,
        format: str | None = None,
    ):
        """
        Minimal replacement for torchaudio.load that reads 16-bit PCM WAVs
        without going through torchcodec / FFmpeg.

        Only intended for ACE-Step's reference / edit audio paths in this app.
        """
        path_str = str(filepath)

        # Read the entire WAV (or a slice) using built-in wave
        with wave.open(path_str, "rb") as fh:
            n_channels = fh.getnchannels()
            sample_rate = fh.getframerate()
            n_frames_total = fh.getnframes()

            # Clamp starting position
            if frame_offset < 0:
                frame_offset = 0
            if frame_offset > n_frames_total:
                frame_offset = n_frames_total
            fh.setpos(frame_offset)

            # Decide how many frames to read
            if num_frames is None or num_frames < 0:
                frames_to_read = n_frames_total - frame_offset
            else:
                frames_to_read = min(num_frames, n_frames_total - frame_offset)

            raw_bytes = fh.readframes(frames_to_read)

        if not raw_bytes:
            # Empty audio tensor
            empty = torch.zeros((n_channels, 0), dtype=torch.float32)
            return empty if channels_first else empty.t(), sample_rate

        # Convert bytes → int16 → float32
        audio_i16 = np.frombuffer(raw_bytes, dtype=np.int16)

        # Shape: [num_samples, channels]
        if n_channels > 0:
            audio = audio_i16.reshape(-1, n_channels).astype("float32")
        else:
            audio = audio_i16.astype("float32").reshape(-1, 1)
            n_channels = 1

        if normalize:
            audio /= 32768.0

        audio_tensor = torch.from_numpy(audio)  # [num_samples, channels]

        if channels_first:
            audio_tensor = audio_tensor.t()      # [channels, num_samples]

        return audio_tensor, sample_rate

    # Monkey-patch torchaudio.save/load before ACE-Step uses them
    torchaudio.save = _candy_torchaudio_save  # type: ignore[assignment]
    torchaudio.load = _candy_torchaudio_load  # type: ignore[assignment]

except Exception as _ta_err:
    # If this somehow fails, we fall back to the original torchaudio.load/save,
    # in which case you'll still see the torchcodec error.
    pass

# ACE-Step pipeline (using cdmf_pipeline_ace_step.py)
_ACE_IMPORT_ERROR = None  # <-- MUST exist before the try

try:
    from cdmf_pipeline_ace_step import ACEStepPipeline
except Exception as e:  # import-time diagnostics only
    ACEStepPipeline = None  # type: ignore[assignment]
    _ACE_IMPORT_ERROR = e
    # Print import error immediately for debugging frozen apps
    print(f"[ACE] WARNING: Failed to import ACEStepPipeline: {type(e).__name__}: {e}", flush=True)

# -----------------------------------------------------------------------------
#  Basic config
# -----------------------------------------------------------------------------

import cdmf_paths

# Default target length + fades (UI can override)
DEFAULT_TARGET_SECONDS = 150.0
DEFAULT_FADE_IN_SECONDS = 0.5
DEFAULT_FADE_OUT_SECONDS = 0.5

# Where this script lives
APP_DIR = Path(__file__).parent.resolve()

# Force Hugging Face cache into the configured models folder
HF_HOME = cdmf_paths.get_models_folder()
os.environ.setdefault("HF_HOME", str(HF_HOME))

# Default output root if none is explicitly provided
DEFAULT_OUTPUT_ROOT = APP_DIR / "generated"

# Subfolder where ACE-Step input_params JSONs will be stored, relative to each
# output directory (e.g. generated/input_params_record).
INPUT_PARAMS_SUBDIR_NAME = "input_params_record"

# If you decide to call a local ACE-Step repo via infer-api.py instead of
# importing its Python API, you can point to it here:
ACE_STEP_REPO_DIR = Path(os.environ.get("ACE_STEP_REPO_DIR", APP_DIR / "ACE-Step")).resolve()
# Force ACE-Step to look for checkpoints inside the configured models folder
os.environ.setdefault(
    "ACE_STEP_CACHE_DIR",
    str(cdmf_paths.get_models_folder().resolve())
)

# -----------------------------------------------------------------------------
#  Progress callback plumbing (UI can hook into this)
# -----------------------------------------------------------------------------

ProgressCallback = Callable[[float, str], None]
_PROGRESS_CALLBACK: Optional[ProgressCallback] = None


def register_progress_callback(cb: Optional[ProgressCallback]) -> None:
    """
    Register a callback that receives (fraction, stage) during generation.

    fraction: 0.0 → 1.0
    stage: arbitrary label ("ace", "fades", etc.)
    """
    global _PROGRESS_CALLBACK
    _PROGRESS_CALLBACK = cb


def _report_progress(fraction: float, stage: str = "ace") -> None:
    """
    Internal helper to report progress to the UI, if a callback is registered.
    """
    if _PROGRESS_CALLBACK is None:
        return
    try:
        frac = float(fraction)
    except Exception:
        frac = 0.0
    try:
        _PROGRESS_CALLBACK(frac, stage)
    except Exception:
        # Do not let UI progress errors kill generation
        pass


# -----------------------------------------------------------------------------
#  ACE-Step pipeline singleton
# -----------------------------------------------------------------------------

_ACE_PIPELINE: Optional["ACEStepPipeline"] = None
_ACE_PIPELINE_LOCK = threading.Lock()
_ACE_GENERATION_LOCK = threading.Lock()

def _monkeypatch_ace_tqdm() -> None:
    """
    Patch ACE-Step's internal `tqdm` so its diffusion/decoding loops
    feed into our `_report_progress` callback.

    This makes the front-end progress bar track *actual* backend work
    instead of just a couple of coarse jumps.
    """
    if ACEStepPipeline is None:
        return

    try:
        import cdmf_pipeline_ace_step as ace_mod
    except Exception:
        # If the module isn't importable for some reason, just bail out.
        return

    # Avoid double-patching if `_get_ace_pipeline()` is called more than once.
    if getattr(ace_mod, "_candy_tqdm_patched", False):
        return

    orig_tqdm = ace_mod.tqdm

    # Map ACE internal function names → (global_progress_start, global_progress_end)
    # These ranges sit inside [0.0, 1.0] for the overall job.
    STAGE_RANGES = {
        # Main diffusion / editing loops
        "text2music_diffusion_process": (0.20, 0.80),
        "flowedit_diffusion_process": (0.20, 0.80),
        # Latents → waveform decode
        "latents2audio": (0.80, 0.90),
    }

    def candy_tqdm(iterable=None, *args, **kwargs):
        """
        Wrapper around ACE's original `tqdm` that:
          - figures out which ACE function is using it (via call stack),
          - maps inner progress 0..1 to a global 0..1 window,
          - forwards updates to `_report_progress`,
          - otherwise behaves like a normal tqdm over `iterable`.
        """
        stage_name = "ace"
        start, end = 0.20, 0.90  # default fallback span

        try:
            stack = inspect.stack()
            # Look a few frames up the stack for a known ACE function name
            for frame_info in stack[1:6]:
                fn = frame_info.function
                if fn in STAGE_RANGES:
                    start, end = STAGE_RANGES[fn]
                    stage_name = fn
                    break
        except Exception:
            # If inspection fails, we still run the original tqdm
            pass

        # If tqdm is used in "manual" mode (no iterable), just delegate.
        if iterable is None:
            return orig_tqdm(*args, **kwargs)

        # Try to get a total if not explicitly provided
        total = kwargs.get("total")
        if total is None:
            try:
                total = len(iterable)
            except Exception:
                total = None

        inner = orig_tqdm(iterable, *args, **kwargs)

        def generator():
            # Protect against division-by-zero
            span = max(0.0, float(end) - float(start))
            idx = 0
            denom = float(total) if total else None

            for item in inner:
                idx += 1
                if denom:
                    frac_local = idx / denom  # 0..1 within this stage
                    frac_global = start + span * frac_local
                    try:
                        _report_progress(frac_global, stage=stage_name)
                    except Exception:
                        # Never let UI progress reporting kill generation
                        pass
                yield item

        return generator()

    ace_mod.tqdm = candy_tqdm
    ace_mod._candy_tqdm_patched = True
    

def _get_ace_pipeline() -> "ACEStepPipeline":
    """
    Lazily construct and cache a single ACEStepPipeline instance.

    We explicitly point it at our app-local ACE cache so it reuses the
    model that the "Download Models" button fetched, instead of trying to
    re-download into the user's home directory.
    """
    global _ACE_PIPELINE

    if _ACE_PIPELINE is not None:
        return _ACE_PIPELINE

    if ACEStepPipeline is None:
        # Check if running as frozen app (macOS .app bundle)
        is_frozen = getattr(sys, 'frozen', False)
        
        # Format error details
        error_type = type(_ACE_IMPORT_ERROR).__name__ if _ACE_IMPORT_ERROR else "Unknown"
        error_msg_detail = str(_ACE_IMPORT_ERROR) if _ACE_IMPORT_ERROR else "No error details available"
        
        if is_frozen:
            # For frozen app, acestep should already be bundled
            error_msg = (
                "ACEStepPipeline could not be imported from cdmf_pipeline_ace_step.py.\n\n"
                "This is unexpected in a frozen app bundle - the ace-step package\n"
                "should have been bundled during the build process.\n\n"
                "Possible causes:\n"
                "- The app bundle was built without ace-step installed\n"
                "- A dependency is missing or incompatible\n\n"
                "Try downloading a fresh copy of AceForge from:\n"
                "  https://github.com/audiohacking/AceForge/releases\n\n"
                f"Original import error ({error_type}):\n{error_msg_detail}"
            )
        else:
            # For running from source
            error_msg = (
                "ACEStepPipeline could not be imported from cdmf_pipeline_ace_step.py.\n\n"
                "This usually means the ace-step package is not installed.\n"
                "ACE-Step must be installed from GitHub (not PyPI) using:\n"
                '  pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps\n\n'
                "Or run the setup using the launcher script (CDMF.sh / CDMF.bat) which\n"
                "will handle all dependencies automatically.\n\n"
                f"Original import error ({error_type}):\n{error_msg_detail}"
            )
        
        raise RuntimeError(error_msg)

    with _ACE_PIPELINE_LOCK:
        if _ACE_PIPELINE is not None:
            return _ACE_PIPELINE

        print(
            "[ACE] Initializing ACEStepPipeline (first time will download/load checkpoints)...",
            flush=True,
        )
        _report_progress(0.05, "ace_load")

        # Make sure our dedicated ACE cache under ace_models/checkpoints is ready.
        try:
            checkpoint_root = ensure_ace_models()
        except Exception as exc:
            raise RuntimeError(
                "Failed to prepare ACE-Step checkpoints. "
                "See the console logs above for details."
            ) from exc

        # Wire ACE's internal progress bars into our callback before heavy work starts.
        _monkeypatch_ace_tqdm()

        # Tell ACE-Step to use our cache root as its checkpoint_dir so it
        # doesn't try to re-download into ~/.cache/ace-step/checkpoints.
        pipeline = ACEStepPipeline(checkpoint_dir=str(checkpoint_root))
        _ACE_PIPELINE = pipeline

        print("[ACE] ACEStepPipeline ready.", flush=True)

    return _ACE_PIPELINE


# -----------------------------------------------------------------------------
#  Vibe tags (mapped into ACE "Tags" field)
# -----------------------------------------------------------------------------

ACE_VIBE_TAGS: Dict[str, List[str]] = {
    "lofi_dreamy": [
        "lofi", "downtempo", "dreamy", "soft beats", "chill"
    ],
    "chiptunes_upbeat": [
        "chiptune", "8-bit", "upbeat", "retro game soundtrack"
    ],
    "chiptunes_zelda": [
        "chiptune", "fantasy", "adventure", "RPG", "game soundtrack"
    ],
    "fantasy": [
        "fantasy", "orchestral", "cinematic", "RPG background music"
    ],
    "cyberpunk": [
        "cyberpunk", "synthwave", "electronic", "neon", "dark"
    ],
    "misc": [],
    "any": [],
}


# -----------------------------------------------------------------------------
#  Helpers
# -----------------------------------------------------------------------------

def _choose_effective_seed(seed: int) -> int:
    if seed and seed > 0:
        return int(seed)
    eff = random.randint(1, 2**31 - 1)
    print(f"[ACE] No seed or seed=0 provided → using random seed {eff}")
    return eff


def _next_available_output_path(out_dir: Path, basename: str, ext: str = ".wav") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(basename).stem
    if not ext.startswith("."):
        ext = "." + ext

    candidate = out_dir / f"{stem}{ext}"
    if not candidate.exists():
        return candidate

    idx = 2
    while True:
        candidate = out_dir / f"{stem}{idx}{ext}"
        if not candidate.exists():
            return candidate
        idx += 1


def _apply_vibe_to_tags(prompt: str, seed_vibe: str) -> str:
    """
    Take the user's freeform style prompt and merge it with a seed-vibe tag set.
    This ends up in ACE-Step's "Tags" field.
    """
    prompt = (prompt or "").strip()
    key = (seed_vibe or "").strip() or "any"
    tags = ACE_VIBE_TAGS.get(key, [])

    tag_text = ", ".join(tags) if tags else ""
    if tag_text and prompt:
        return f"{tag_text}, {prompt}"
    return prompt or tag_text


def _ensure_reference_wav(src_audio_path: str | None) -> str:
    """
    Normalise a reference audio path so ACE-Step can consume it.

    - Ensures the file exists.
    - If it's already a .wav, returns the absolute path.
    - If it's another audio type (e.g. .mp3), converts it to .wav next to
      the original file and returns that path.
    """
    if not src_audio_path:
        raise ValueError(
            "Audio2Audio / retake / repaint / extend modes require a reference audio file."
        )

    src = Path(src_audio_path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"Reference audio not found: {src}")

    if src.suffix.lower() == ".wav":
        return str(src.resolve())

    # Convert to WAV using pydub so ACE-Step always sees a .wav file.
    try:
        audio = AudioSegment.from_file(str(src))
    except Exception as e:
        raise RuntimeError(f"Failed to read reference audio {src}: {e}") from e

    wav_path = src.with_suffix(".wav")
    try:
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        audio.export(str(wav_path), format="wav")
    except Exception as e:
        raise RuntimeError(f"Failed to convert {src} to WAV: {e}") from e

    print(f"[ACE] Converted reference audio to WAV for ACE-Step: {wav_path}", flush=True)
    return str(wav_path.resolve())


def _prepare_reference_audio(
    task: str,
    audio2audio_enable: bool,
    src_audio_path: str | None,
) -> tuple[str, bool, Optional[str]]:
    """
    Normalise the ACE-Step edit / audio2audio mode:

      - Task is clamped to one of: text2music / retake / repaint / extend.
      - If Audio2Audio is enabled while task is still 'text2music', we
        internally flip it to 'retake' (this is how ACE-Step expects edits).
      - For any edit mode (retake/repaint/extend) we prefer to have a
        reference audio file and make sure ACE-Step sees a .wav path.
        If no reference is provided, we *gracefully* fall back to
        text2music instead of throwing.
    """
    task_norm = (task or "text2music").strip().lower()
    if task_norm not in ("text2music", "retake", "repaint", "extend"):
        task_norm = "text2music"

    # Audio2Audio is effectively an edit of an existing clip. If the user
    # left the task on "Text → music", run it as a retake under the hood.
    if audio2audio_enable and task_norm == "text2music":
        task_norm = "retake"

    # Any of the edit-style tasks imply some form of Audio2Audio.
    audio2audio_flag = bool(
        audio2audio_enable or task_norm in ("retake", "repaint", "extend")
    )

    # If we *think* we're in an edit / audio2audio mode but there's no
    # reference audio path at all, don't crash — just fall back to
    # plain text2music.
    if audio2audio_flag and not src_audio_path:
        print(
            "[ACE] Audio2Audio / edit task requested but no reference audio "
            "was provided — falling back to plain text2music.",
            flush=True,
        )
        task_norm = "text2music"
        audio2audio_flag = False
        return task_norm, audio2audio_flag, None

    if audio2audio_flag:
        ref_path = _ensure_reference_wav(src_audio_path)
    else:
        ref_path = None

    return task_norm, audio2audio_flag, ref_path


def _apply_fades_in_place(
    wav_path: Path,
    fade_in_seconds: float,
    fade_out_seconds: float,
) -> float:
    audio = AudioSegment.from_file(wav_path)
    duration_ms = len(audio)
    if duration_ms <= 0:
        return 0.0

    fi = max(0.0, float(fade_in_seconds))
    fo = max(0.0, float(fade_out_seconds))
    half_sec = (duration_ms / 1000.0) / 2.0
    fi = min(fi, half_sec)
    fo = min(fo, half_sec)

    if fi > 0:
        audio = audio.fade_in(int(fi * 1000.0))
    if fo > 0:
        audio = audio.fade_out(int(fo * 1000.0))

    audio.export(str(wav_path), format="wav")
    return duration_ms / 1000.0


def _apply_vocal_instrumental_mix_if_requested(
    wav_path: Path,
    vocal_gain_db: float,
    instrumental_gain_db: float,
) -> None:
    """
    Optional post-process step:

    If either gain is non-zero, use `audio-separator` to split the track into
    Vocals + Instrumental stems, apply the requested dB changes, then write
    the mixed result back into ``wav_path`` in-place.

    If audio-separator (or its model/FFmpeg deps) aren't available, this
    quietly logs and does nothing.
    """
    try:
        vg = float(vocal_gain_db)
        ig = float(instrumental_gain_db)
    except Exception:
        return

    # Nothing to do if both sliders are effectively at 0 dB.
    if abs(vg) < 0.1 and abs(ig) < 0.1:
        return

    wav_path = Path(wav_path)
    if not wav_path.exists():
        print(f"[ACE] Stem mix requested but file does not exist: {wav_path}", flush=True)
        return

    try:
        from audio_separator.separator import Separator  # type: ignore[import]
    except Exception as exc:
        print(
            "[ACE] Vocal/instrumental sliders requested but the "
            "'audio-separator' package is not available; skipping stem mix: "
            f"{exc}",
            flush=True,
        )
        return

    tmp_dir = wav_path.parent / "_cdmf_stems_tmp"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        print(f"[ACE] Could not create temporary stem folder {tmp_dir}: {exc}", flush=True)
        return

    try:
        # Keep models cached in tmp_dir/models so we don't re-download every time.
        models_dir = tmp_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        separator = Separator(
            model_file_dir=str(models_dir),
            output_dir=str(tmp_dir),
            output_format="wav",
        )
        separator.load_model()
    except Exception as exc:
        print(f"[ACE] Failed to load audio-separator model; skipping stem mix: {exc}", flush=True)
        return

    output_names = {
        "Vocals": "cdmf_vocals",
        "Instrumental": "cdmf_instrumental",
    }

    try:
        separator.separate(str(wav_path), output_names)
    except Exception as exc:
        print(f"[ACE] audio-separator failed on {wav_path}: {exc}", flush=True)
        return

    vocal_file = tmp_dir / "cdmf_vocals.wav"
    inst_file = tmp_dir / "cdmf_instrumental.wav"

    if not vocal_file.exists() or not inst_file.exists():
        print(
            "[ACE] audio-separator did not produce expected stems "
            f"({vocal_file}, {inst_file}); skipping stem mix.",
            flush=True,
        )
        return

    try:
        vocal_seg = AudioSegment.from_file(vocal_file)
        inst_seg = AudioSegment.from_file(inst_file)
    except Exception as exc:
        print(f"[ACE] Failed to read separated stems: {exc}", flush=True)
        return

    # Align durations by padding the shorter clip with silence.
    max_len = max(len(vocal_seg), len(inst_seg))
    if len(vocal_seg) < max_len:
        vocal_seg = vocal_seg + AudioSegment.silent(duration=max_len - len(vocal_seg))
    if len(inst_seg) < max_len:
        inst_seg = inst_seg + AudioSegment.silent(duration=max_len - len(inst_seg))

    # pydub's '+' operator is dB gain.
    if abs(vg) > 0.05:
        vocal_seg = vocal_seg + vg
    if abs(ig) > 0.05:
        inst_seg = inst_seg + ig

    mixed = inst_seg.overlay(vocal_seg)

    try:
        mixed.export(str(wav_path), format="wav")
        print(
            "[ACE] Applied vocal/instrumental mix: "
            f"vocals {vg:+.1f} dB, instrumental {ig:+.1f} dB.",
            flush=True,
        )
    except Exception as exc:
        print(f"[ACE] Failed to write mixed stem back to {wav_path}: {exc}", flush=True)

    # Best-effort cleanup
    try:
        for p in tmp_dir.glob("*"):
            try:
                p.unlink()
            except Exception:
                pass
        tmp_dir.rmdir()
    except Exception:
        pass


# -----------------------------------------------------------------------------
#  ACE-Step bridge (to be wired to the real API)
# -----------------------------------------------------------------------------

def _run_ace_text2music(
    *,
    tags: str,
    lyrics: str,
    seconds: float,
    seed: int,
    output_path: Path,
    steps: int = 85,
    guidance_scale: float = 10.0,
    # --- Advanced knobs (exposed via Advanced panel) -----------------------
    scheduler_type: str = "euler",
    cfg_type: str = "apg",
    omega_scale: float = 5.0,
    guidance_interval: float = 1.0,
    guidance_interval_decay: float = 0.25,
    min_guidance_scale: float = 7.0,
    use_erg_tag: bool = True,
    use_erg_lyric: bool = True,
    use_erg_diffusion: bool = True,
    oss_steps: str | list[int] | None = None,
    # Retake / repaint / extend controls
    task: str = "text2music",
    repaint_start: float = 0.0,
    repaint_end: float = 0.0,
    retake_variance: float = 0.5,
    src_audio_path: str | None = None,
    # Audio2Audio + LoRA
    audio2audio_enable: bool = False,
    ref_audio_strength: float = 0.7,
    lora_name_or_path: str | None = None,
    lora_weight: float = 0.75,
) -> None:
    """
    Call ACE-Step Text2Music and render a single track into ``output_path``.

    Mapping to ACEStepPipeline.__call__:

      • Candy “genre_prompt” (+ vibe tags) → ACE ``prompt`` (aka Tags)
      • Candy ``lyrics``                  → ACE ``lyrics``
        (we pass ``[inst]`` for instrumentals upstream)
      • ``seconds``                       → ``audio_duration``
      • ``steps``                         → ``infer_step``
      • ``guidance_scale``               → ``guidance_scale``
      • ``scheduler_type``               → ``scheduler_type`` (euler / heun / pingpong)
      • ``cfg_type``                     → ``cfg_type`` (apg / cfg / cfg_star)
      • ``omega_scale``                  → ``omega_scale`` (granularity)
      • ``guidance_interval*``           → guidance window / decay controls
      • ``use_erg_*``                    → ERG tag / lyric / diffusion toggles
      • ``oss_steps``                    → custom sigma steps
      • ``task`` / repaint_* / variance → retake / repaint / extend behaviour
      • ``audio2audio_*``               → reference-audio remix strength / source
      • ``lora_*``                       → LoRA adapter selection / strength
      • ``seed``                        → ``manual_seeds``

    Any *_input_params.json file returned by ACE-Step is moved into
    APP_DIR / "input_params_record". No .wav files are kept there.
    """
    pipeline = _get_ace_pipeline()

    tags = (tags or "").strip()
    lyrics = (lyrics or "").strip()

    if not tags:
        raise ValueError("ACE-Step: tags/prompt cannot be empty.")

    seconds = max(1.0, float(seconds))
    steps = max(1, int(steps))
    guidance_scale = float(guidance_scale)
    omega_scale = float(omega_scale)
    guidance_interval = float(guidance_interval)
    guidance_interval_decay = float(guidance_interval_decay)
    min_guidance_scale = float(min_guidance_scale)
    retake_variance = float(retake_variance)
    ref_audio_strength = float(ref_audio_strength)
    lora_weight = float(lora_weight)

    # Hard guard: normalise edit / Audio2Audio combination here as well so that
    # ACE-Step never sees an invalid (task, src_audio_path) pair that would
    # trigger its internal assertion.
    task, audio2audio_enable, src_audio_path = _prepare_reference_audio(
        task,
        bool(audio2audio_enable),
        src_audio_path,
    )

    # Debug print so we can see exactly what we are sending into ACE-Step.
    try:
        print(
            f"[ACE] _run_ace_text2music: task={task}, "
            f"audio2audio={audio2audio_enable}, "
            f"src_audio_path={src_audio_path!r}",
            flush=True,
        )
    except Exception:
        pass

    manual_seed = int(seed) if seed is not None else 0

    # Ensure parent dir exists for the final WAV output
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # One-at-a-time generation so we don't fight over the GPU.
    with _ACE_GENERATION_LOCK:
        _report_progress(0.25, "ace_infer")

        # ACEStepPipeline.__call__ returns [audio_path(s)..., input_params_json]
        # We tell it to save into the *final* output_path directory.
        # Build kwargs so we can conditionally include LoRA config only when set.
        call_kwargs: Dict[str, Any] = {
            "format": "wav",
            "audio_duration": seconds,
            "prompt": tags,
            "lyrics": lyrics,
            "infer_step": steps,
            "guidance_scale": guidance_scale,
            "scheduler_type": scheduler_type,
            "cfg_type": cfg_type,
            "omega_scale": omega_scale,
            "guidance_interval": guidance_interval,
            "guidance_interval_decay": guidance_interval_decay,
            "min_guidance_scale": min_guidance_scale,
            "use_erg_tag": use_erg_tag,
            "use_erg_lyric": use_erg_lyric,
            "use_erg_diffusion": use_erg_diffusion,
            "oss_steps": oss_steps,
            "manual_seeds": manual_seed if manual_seed > 0 else None,
            # Retake / repaint / extend (no-op for plain text2music defaults)
            "task": task,
            "repaint_start": repaint_start,
            "repaint_end": repaint_end,
            "retake_variance": retake_variance,
            # Audio2Audio / reference audio
            "audio2audio_enable": bool(audio2audio_enable),
            "ref_audio_strength": ref_audio_strength,
            "batch_size": 1,
            "save_path": str(output_path),
            "debug": False,
        }

        # Wire up reference vs source audio correctly:
        #
        # - For audio2audio: send the clip as `ref_audio_input` and DO NOT
        #   pass `src_audio_path`. ACE-Step will internally flip `task` to
        #   "audio2audio", and older builds avoid the buggy assert.
        #
        # - For plain text2music: leave both unset (None).
        if audio2audio_enable and src_audio_path:
            call_kwargs["ref_audio_input"] = src_audio_path
            # Important: never set a non-None src_audio_path for this mode.
            call_kwargs["src_audio_path"] = None
        else:
            call_kwargs["ref_audio_input"] = None
            call_kwargs["src_audio_path"] = None

        # Only forward LoRA configuration if an adapter path/name was provided.
        lora_path = (lora_name_or_path or "").strip() if isinstance(lora_name_or_path, str) else ""
        if lora_path:
            call_kwargs["lora_name_or_path"] = lora_path
            call_kwargs["lora_weight"] = lora_weight

        result = pipeline(**call_kwargs)

    if not result:
        raise RuntimeError("ACE-Step did not return any outputs.")

    # Separate paths into WAVs and JSONs
    path_strings = [p for p in result if isinstance(p, str)]
    if not path_strings:
        raise RuntimeError("ACE-Step outputs did not contain any file paths.")

    wav_candidates = [
        Path(p) for p in path_strings if p.lower().endswith(".wav")
    ]
    json_candidates = [
        Path(p) for p in path_strings if p.lower().endswith(".json")
    ]

    if not wav_candidates:
        # Fallback: treat the first string as the audio path
        raw_path = Path(path_strings[0])
    else:
        raw_path = wav_candidates[0]

    if not raw_path.exists():
        raise RuntimeError(f"ACE-Step output file not found: {raw_path}")

    print(f"[ACE] Output written by ACE-Step: {raw_path}", flush=True)

    # Normalize to the requested output_path if ACE used a different filename
    if raw_path.resolve() != output_path.resolve():
        audio = AudioSegment.from_file(raw_path)
        audio.export(str(output_path), format="wav")
        print(f"[ACE] Normalized output to: {output_path}", flush=True)

    # Move any *_input_params*.json into a subfolder relative to the *output*
    # directory, e.g. generated/input_params_record for the default out_dir.
    input_params_dir = output_path.parent / INPUT_PARAMS_SUBDIR_NAME
    input_params_dir.mkdir(parents=True, exist_ok=True)

    moved: set[Path] = set()

    # First, move any JSON paths ACE-Step explicitly returned.
    if json_candidates:
        for json_path in json_candidates:
            try:
                if not json_path.exists():
                    continue
                target = input_params_dir / json_path.name
                # Replace any existing file with the same name
                if target.exists():
                    target.unlink()
                json_path.replace(target)
                moved.add(target)
                print(f"[ACE] Moved input params JSON to: {target}", flush=True)
            except Exception as e:
                print(
                    f"[ACE] Warning: failed to move input params JSON "
                    f"{json_path} → {input_params_dir}: {e}",
                    flush=True,
                )

    # Fallback: sweep the output directory for any leftover *input_params*.json
    # that ACE-Step may have written without including in its return value.
    try:
        for extra in output_path.parent.glob("*input_params*.json"):
            try:
                if not extra.is_file():
                    continue
                target = input_params_dir / extra.name
                if target.exists():
                    target.unlink()
                extra.replace(target)
                print(f"[ACE] Swept input params JSON to: {target}", flush=True)
            except Exception as e:
                print(
                    f"[ACE] Warning: failed to sweep input params JSON "
                    f"{extra} → {input_params_dir}: {e}",
                    flush=True,
                )
    except Exception as e:
        print(
            f"[ACE] Warning: failed to scan for extra input_params JSON files: {e}",
            flush=True,
        )


# -----------------------------------------------------------------------------
#  Main entry point for the Flask UI
# -----------------------------------------------------------------------------

def generate_track_ace(
    *,
    genre_prompt: str,
    lyrics: str = "",
    instrumental: bool = True,
    negative_prompt: str = "",
    target_seconds: float = DEFAULT_TARGET_SECONDS,
    fade_in_seconds: float = DEFAULT_FADE_IN_SECONDS,
    fade_out_seconds: float = DEFAULT_FADE_OUT_SECONDS,
    seed: int = 0,
    out_dir: Path | None = None,
    basename: str = "Candy Dreams",
    seed_vibe: str = "any",
    bpm: float | None = None,
    steps: int = 65,
    guidance_scale: float = 4.0,
    # New: post-mix volume controls for separated stems (dB)
    vocal_gain_db: float = 0.0,
    instrumental_gain_db: float = 0.0,
    # Advanced ACE-Step controls (mirrors _run_ace_text2music)
    scheduler_type: str = "euler",
    cfg_type: str = "apg",
    omega_scale: float = 10.0,
    guidance_interval: float = 0.5,
    guidance_interval_decay: float = 0.0,
    min_guidance_scale: float = 3.0,
    use_erg_tag: bool = True,
    use_erg_lyric: bool = True,
    use_erg_diffusion: bool = True,
    oss_steps: str | list[int] | None = None,
    task: str = "text2music",
    repaint_start: float = 0.0,
    repaint_end: float = 0.0,
    retake_variance: float = 0.5,
    audio2audio_enable: bool = False,
    ref_audio_strength: float = 0.7,
    src_audio_path: str | None = None,
    lora_name_or_path: str | None = None,
    lora_weight: float = 0.75,
) -> Dict[str, Any]:
    """
    High-level wrapper for the Flask UI.

    - genre_prompt  – description of style / vibe / instruments → ACE "Tags"
    - lyrics        – optional lyrics (only used if instrumental=False)
    - instrumental  – if True, strongly biases toward instrumental-only output
    - bpm           – optional beats-per-minute hint; if set, we append
                      "tempo <bpm> bpm" into the tags
    - advanced knobs – passed straight through to ACEStepPipeline.__call__()
    """
    genre_prompt = (genre_prompt or "").strip()
    lyrics = (lyrics or "").strip()
    negative_prompt = (negative_prompt or "").strip()

    if not genre_prompt:
        raise ValueError("Genre / style prompt cannot be completely empty.")

    requested_total = float(target_seconds)
    if requested_total <= 0:
        raise ValueError("Target length must be > 0.")

    fade_in_seconds = max(0.0, float(fade_in_seconds))
    fade_out_seconds = max(0.0, float(fade_out_seconds))

    out_dir = Path(out_dir or DEFAULT_OUTPUT_ROOT)
    out_dir.mkdir(parents=True, exist_ok=True)

    eff_seed = _choose_effective_seed(int(seed) if seed is not None else 0)

    # Build ACE "Tags" field directly from the genre/style prompt.
    # Seed vibe controls are no longer used here.
    tags_text = (genre_prompt or "").strip()

    tag_bits: List[str] = []
    if tags_text:
        tag_bits.append(tags_text)

    if instrumental:
        tag_bits.append(
            "instrumental background music only, no vocals, no lyrics, "
            "no spoken word, no chanting"
        )

    if negative_prompt:
        tag_bits.append(f"avoid: {negative_prompt}")

    bpm_val: Optional[float] = None
    if bpm is not None:
        try:
            bpm_val = float(bpm)
        except Exception:
            bpm_val = None
        if bpm_val is not None and bpm_val > 0:
            tag_bits.append(f"tempo {bpm_val:.0f} bpm")

    combined_tags = ", ".join(tag_bits).strip()
    if not combined_tags:
        combined_tags = "instrumental background music, no vocals"

    # Normalize a few categorical fields
    scheduler_type = (scheduler_type or "euler").lower()
    if scheduler_type not in ("euler", "heun", "pingpong"):
        scheduler_type = "euler"

    cfg_type = (cfg_type or "apg").lower()
    if cfg_type not in ("apg", "cfg", "cfg_star"):
        cfg_type = "apg"

    # Normalise edit / Audio2Audio settings before we talk to ACE-Step.
    task, audio2audio_enable, src_audio_path = _prepare_reference_audio(
        task,
        bool(audio2audio_enable),
        src_audio_path,
    )

    out_path = _next_available_output_path(out_dir, basename, ext=".wav")

    print(
        f"[ACE] Generating track → {out_path} "
        f"(target ≈ {requested_total:.1f}s, seed={eff_seed}, "
        f"bpm={bpm_val}, instrumental={instrumental}, "
        f"steps={steps}, guidance={guidance_scale}, "
        f"scheduler={scheduler_type}, cfg={cfg_type}, "
        f"omega={omega_scale}, task={task}, "
        f"audio2audio={audio2audio_enable}, lora={bool(lora_name_or_path)})"
    )

    _report_progress(0.05, "start")
    _report_progress(0.15, "ace_infer")

    if instrumental:
        effective_lyrics = "[inst]"
    else:
        effective_lyrics = lyrics

    _run_ace_text2music(
        tags=combined_tags,
        lyrics=effective_lyrics,
        seconds=requested_total,
        seed=eff_seed,
        output_path=out_path,
        steps=int(steps),
        guidance_scale=float(guidance_scale),
        scheduler_type=scheduler_type,
        cfg_type=cfg_type,
        omega_scale=float(omega_scale),
        guidance_interval=float(guidance_interval),
        guidance_interval_decay=float(guidance_interval_decay),
        min_guidance_scale=float(min_guidance_scale),
        use_erg_tag=bool(use_erg_tag),
        use_erg_lyric=bool(use_erg_lyric),
        use_erg_diffusion=bool(use_erg_diffusion),
        oss_steps=oss_steps,
        task=task,
        repaint_start=float(repaint_start),
        repaint_end=float(repaint_end),
        retake_variance=float(retake_variance),
        src_audio_path=src_audio_path,
        audio2audio_enable=bool(audio2audio_enable),
        ref_audio_strength=float(ref_audio_strength),
        lora_name_or_path=lora_name_or_path,
        lora_weight=float(lora_weight),
    )

    _report_progress(0.90, "fades")

    actual_seconds = _apply_fades_in_place(
        wav_path=out_path,
        fade_in_seconds=fade_in_seconds,
        fade_out_seconds=fade_out_seconds,
    )

    # Optional: run stem separation + remix if sliders are non-zero.
    _report_progress(0.93, "stem_mix")
    _apply_vocal_instrumental_mix_if_requested(
        wav_path=out_path,
        vocal_gain_db=vocal_gain_db,
        instrumental_gain_db=instrumental_gain_db,
    )

    _report_progress(1.0, "done")

    print(
        f"[ACE] Finished track: {out_path.name} "
        f"(≈{actual_seconds:.1f}s, seed={eff_seed}, bpm={bpm_val})"
    )

    return {
        "wav_path": str(out_path),
        "actual_seconds": actual_seconds,
        "seed": eff_seed,
        "genre_prompt": genre_prompt,
        "lyrics": lyrics,
        "instrumental": instrumental,
        "negative_prompt": negative_prompt,
        "seed_vibe": seed_vibe,
        "target_seconds": requested_total,
        "bpm": bpm_val,
        "steps": steps,
        "guidance_scale": guidance_scale,
        # New: store the slider positions in track metadata
        "vocal_gain_db": float(vocal_gain_db),
        "instrumental_gain_db": float(instrumental_gain_db),
        # Advanced knobs (so /tracks/meta + presets can round-trip them)
        "scheduler_type": scheduler_type,
        "cfg_type": cfg_type,
        "omega_scale": float(omega_scale),
        "guidance_interval": float(guidance_interval),
        "guidance_interval_decay": float(guidance_interval_decay),
        "min_guidance_scale": float(min_guidance_scale),
        "use_erg_tag": bool(use_erg_tag),
        "use_erg_lyric": bool(use_erg_lyric),
        "use_erg_diffusion": bool(use_erg_diffusion),
        "oss_steps": oss_steps,
        "task": task,
        "repaint_start": float(repaint_start),
        "repaint_end": float(repaint_end),
        "retake_variance": float(retake_variance),
        "audio2audio_enable": bool(audio2audio_enable),
        "ref_audio_strength": float(ref_audio_strength),
        "src_audio_path": src_audio_path,
        "lora_name_or_path": lora_name_or_path,
        "lora_weight": float(lora_weight),
    }


# -----------------------------------------------------------------------------
#  Simple CLI for testing
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate an ACE-Step track (CLI helper).")
    parser.add_argument("--genre-prompt", type=str, default="", help="Genre/style prompt (tags).")
    parser.add_argument(
        "--prompt",
        type=str,
        default="",
        help="(Deprecated) Alias for --genre-prompt."
    )
    parser.add_argument(
        "--lyrics",
        type=str,
        default="",
        help="Lyrics text (optional; ignored if --instrumental is set).",
    )
    parser.add_argument(
        "--instrumental",
        action="store_true",
        help="Generate instrumental-only track (ignore lyrics).",
    )
    parser.add_argument(
        "--negative-prompt",
        type=str,
        default="",
        help="Negative concepts to avoid (folded into tags).",
    )
    parser.add_argument("--seconds", type=float, default=DEFAULT_TARGET_SECONDS)
    parser.add_argument("--fade-in", type=float, default=DEFAULT_FADE_IN_SECONDS)
    parser.add_argument("--fade-out", type=float, default=DEFAULT_FADE_OUT_SECONDS)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=65)
    parser.add_argument("--guidance", type=float, default=4.0)
    parser.add_argument(
        "--out-dir",
        type=str,
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Output directory (defaults to ./generated).",
    )
    parser.add_argument("--basename", type=str, default="Candy Dreams")
    parser.add_argument(
        "--seed-vibe",
        type=str,
        default="any",
        help="Style / vibe key (matches the web UI dropdown).",
    )
    parser.add_argument(
        "--bpm",
        type=float,
        default=None,
        help="Optional tempo in beats per minute (added as a tag hint).",
    )

    args = parser.parse_args()

    genre_prompt = args.genre_prompt or args.prompt

    summary = generate_track_ace(
        genre_prompt=genre_prompt,
        lyrics=args.lyrics,
        instrumental=bool(args.instrumental),
        negative_prompt=args.negative_prompt,
        target_seconds=args.seconds,
        fade_in_seconds=args.fade_in,
        fade_out_seconds=args.fade_out,
        seed=args.seed,
        out_dir=Path(args.out_dir),
        basename=args.basename,
        seed_vibe=args.seed_vibe,
        bpm=args.bpm,
        steps=args.steps,
        guidance_scale=args.guidance,
    )

    print("Generation summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
