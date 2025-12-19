# C:\AceForge\lyrics_model_setup.py  (new file)

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional
import json
import os
import re
import threading

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import snapshot_download

from cdmf_paths import APP_DIR

ProgressCallback = Optional[Callable[[float], None]]

# ---------------------------------------------------------------------------
# Paths / model choice
# ---------------------------------------------------------------------------

# Root directory for all models / caches (kept inside the app folder).
MODELS_ROOT = APP_DIR / "models"

# Default LLM for prompt/lyrics:
# - Small enough to bundle reasonably
# - Apache-2.0 license, good at JSON + creative text
LYRICS_MODEL_ID = os.environ.get(
    "CDMF_LYRICS_MODEL_ID", "Qwen/Qwen2-7B-Instruct"
)

# Where we want the *snapshot* of the model to live on disk.
LYRICS_MODEL_DIR = MODELS_ROOT / "prompt_lyrics"

# Encourage Hugging Face to keep all caches under <root>\models
os.environ.setdefault("HF_HOME", str(MODELS_ROOT))

# Global, lazily loaded model + tokenizer
_MODEL_LOCK = threading.Lock()
_MODEL: Optional[AutoModelForCausalLM] = None
_TOKENIZER: Optional[AutoTokenizer] = None


# ---------------------------------------------------------------------------
# Download / presence check
# ---------------------------------------------------------------------------

def lyrics_model_present() -> bool:
    """
    Returns True if we see a downloaded HF snapshot for the lyrics model
    in LYRICS_MODEL_DIR (config.json is a good proxy).
    """
    cfg = LYRICS_MODEL_DIR / "config.json"
    return cfg.is_file()


def ensure_lyrics_model(progress_cb: ProgressCallback = None) -> Path:
    """
    Ensure that the lyrics LLM has been snapshot-downloaded to disk.

    Uses huggingface_hub.snapshot_download() with local_dir pointing at
    <APP_DIR>/models/lyrics_qwen2_5_1_5b so nothing spills into the
    default user-level ~/.cache.
    """
    MODELS_ROOT.mkdir(parents=True, exist_ok=True)

    if lyrics_model_present():
        if progress_cb:
            progress_cb(1.0)
        return LYRICS_MODEL_DIR

    if progress_cb:
        progress_cb(0.0)

    # This pulls the full repo into LYRICS_MODEL_DIR directly.
    snapshot_download(
        repo_id=LYRICS_MODEL_ID,
        local_dir=str(LYRICS_MODEL_DIR),
        local_dir_use_symlinks=False,
        resume_download=True,
    )

    if progress_cb:
        progress_cb(1.0)

    return LYRICS_MODEL_DIR


# ---------------------------------------------------------------------------
# Lazy loading of the model
# ---------------------------------------------------------------------------

def _load_lyrics_model() -> tuple[AutoModelForCausalLM, AutoTokenizer]:
    """
    Lazily load Qwen2.5-1.5B-Instruct (or whatever you configure) from
    LYRICS_MODEL_DIR. Uses device_map="auto" if CUDA is available.
    """
    global _MODEL, _TOKENIZER

    with _MODEL_LOCK:
        if _MODEL is not None and _TOKENIZER is not None:
            return _MODEL, _TOKENIZER

        ensure_lyrics_model()

        tokenizer = AutoTokenizer.from_pretrained(
            str(LYRICS_MODEL_DIR),
            trust_remote_code=True,
        )

        # Ensure we have a pad token for generation
        if tokenizer.pad_token_id is None:
            if tokenizer.eos_token_id is not None:
                tokenizer.pad_token = tokenizer.eos_token
            else:
                tokenizer.add_special_tokens({"pad_token": "<|pad|>"})

        model = AutoModelForCausalLM.from_pretrained(
            str(LYRICS_MODEL_DIR),
            torch_dtype="auto",
            device_map="auto" if torch.cuda.is_available() else None,
            trust_remote_code=True,
        )
        model.eval()

        _MODEL = model
        _TOKENIZER = tokenizer

        return model, tokenizer


# ---------------------------------------------------------------------------
# Prompt building + output parsing
# ---------------------------------------------------------------------------

def _estimate_line_count(target_seconds: float) -> int:
    """
    Very rough estimate: 1 lyric line ~ 3–4 seconds.
    """
    try:
        t = max(15.0, float(target_seconds))
    except Exception:
        t = 90.0
    approx = int(t / 3.5)
    return max(8, min(64, approx))


def _build_generation_prompt(
    concept: str,
    *,
    target_seconds: float,
    bpm: Optional[float],
    want_prompt: bool,
    want_lyrics: bool,
) -> str:
    line_count = _estimate_line_count(target_seconds)

    mode_parts = []
    if want_prompt and want_lyrics:
        mode_parts.append("Generate BOTH prompt tags and full lyrics.")
    elif want_prompt:
        mode_parts.append(
            "Generate ONLY the 'prompt' tags. Set 'lyrics' to \"[inst]\"."
        )
    elif want_lyrics:
        mode_parts.append(
            "Generate ONLY the 'lyrics'. Set 'prompt' to an empty string \"\"."
        )

    bpm_text = ""
    if bpm is not None:
        bpm_text = f"- Target tempo: about {bpm:.0f} bpm.\n"

    instructions = f"""
You are an assistant for the ACE-Step text-to-music model.

Your job is to turn a short user song concept into:

1. "prompt": a short, comma-separated list of English tags describing:
   - genre
   - mood
   - instrumentation
   - production / mix style
   - tempo / energy
   Example:
   "16-bit SNES-style chiptune, upbeat battle theme, tempo 140 bpm, bright lead synth, punchy drums, looping instrumental"

2. "lyrics": sectioned song lyrics formatted for ACE-Step with markers like:
   [intro], [verse], [pre-chorus], [chorus], [bridge], [outro]
   - Each line should be short and singable (≈4–10 words).
   - Total length should be roughly suitable for a track of ~{target_seconds:.0f} seconds,
     around {line_count} lines of lyrics.
   - You MAY use onomatopoeia / simple vocal sounds (like "la la", "ooh") or 🎵 emojis sparingly.

{bpm_text}
User song concept:
"{concept.strip()}"

{ " ".join(mode_parts) }

VERY IMPORTANT OUTPUT RULES:

- Output MUST be a SINGLE JSON object with EXACTLY these keys:
  {{
    "prompt": "comma-separated tags here",
    "lyrics": "full lyrics here"
  }}

- Do NOT wrap the JSON in backticks or add any extra commentary.
- If lyrics are not requested, set "lyrics" to "[inst]".
- If prompt tags are not requested, set "prompt" to "" (empty string).
- The "prompt" field MUST NOT contain newlines.
- The "lyrics" field should contain the full multi-line lyrics text with section markers.
"""
    # Qwen2.x instruct models respond fine to plain instructions like this.
    return instructions.strip()


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    Pull a JSON object out of the model's response, even if it added stray
    text before/after.
    """
    match = _JSON_RE.search(text)
    if not match:
        raise ValueError("LLM output did not contain a JSON object.")

    raw = match.group(0)
    data = json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError("LLM output JSON was not an object.")

    return data


# ---------------------------------------------------------------------------
# Public generation API
# ---------------------------------------------------------------------------

def generate_prompt_and_lyrics(
    concept: str,
    *,
    target_seconds: float = 90.0,
    bpm: Optional[float] = None,
    want_prompt: bool = True,
    want_lyrics: bool = True,
    max_new_tokens: int = 512,
    temperature: float = 0.9,
    top_p: float = 0.95,
) -> Dict[str, str]:
    """
    Core helper used by the Flask blueprint:

    Returns a dict like:
      {
        "prompt": "comma-separated tags...",
        "lyrics": "[verse] ...",
      }
    """
    if not concept or not concept.strip():
        raise ValueError("Song concept cannot be empty.")

    if not want_prompt and not want_lyrics:
        raise ValueError("At least one of prompt or lyrics must be requested.")

    model, tokenizer = _load_lyrics_model()

    prompt_text = _build_generation_prompt(
        concept=concept,
        target_seconds=target_seconds,
        bpm=bpm,
        want_prompt=want_prompt,
        want_lyrics=want_lyrics,
    )

    device = next(model.parameters()).device
    enc = tokenizer(
        prompt_text,
        return_tensors="pt",
    )
    enc = {k: v.to(device) for k, v in enc.items()}

    with torch.no_grad():
        out = model.generate(
            **enc,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
        )

    # Strip the prompt portion; keep only newly generated tokens.
    gen_ids = out[0][enc["input_ids"].shape[1]:]
    text = tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

    data = _parse_json_from_text(text)

    prompt_val = str(data.get("prompt") or "")
    lyrics_val = str(data.get("lyrics") or "")

    # Enforce "disabled" behaviors in case the model ignored instructions.
    if not want_prompt:
        prompt_val = ""
    if not want_lyrics:
        lyrics_val = "[inst]"

    return {
        "prompt": prompt_val.strip(),
        "lyrics": lyrics_val.strip(),
    }
