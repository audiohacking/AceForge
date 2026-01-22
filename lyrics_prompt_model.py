from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict

import torch
from huggingface_hub import snapshot_download
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from cdmf_paths import USER_SUPPORT_DIR

# ---------------------------------------------------------------------------
# Config: small-ish instruct model + local cache under <USER_SUPPORT_DIR>\models
# ---------------------------------------------------------------------------

# Default to Qwen 3B instruct; can be overridden via env.
MODEL_ID = os.environ.get("CDMF_PROMPT_LYRICS_MODEL", "Qwen/Qwen2-7B-Instruct")
# Local subdir for caching the prompt/lyrics model.
LOCAL_SUBDIR = os.environ.get("CDMF_PROMPT_LYRICS_LOCAL_DIR", "prompt_lyrics")

# If set to a truthy value, we *try* to use CUDA (GPU) for the lyrics LLM.
USE_GPU_ENV = os.environ.get("CDMF_LYRICS_USE_GPU", "").strip().lower()

_PIPELINE = None
_PIPELINE_LOCK = threading.Lock()


def _ensure_pipeline():
    """
    Lazily download + load the prompt/lyrics LLM into USER_SUPPORT_DIR/models/LOCAL_SUBDIR
    and return a cached text-generation pipeline.

    This model is *separate* from ACE-Step; it only lives in memory while
    generating prompts/lyrics.
    """
    global _PIPELINE

    if _PIPELINE is not None:
        return _PIPELINE

    with _PIPELINE_LOCK:
        if _PIPELINE is not None:
            return _PIPELINE

        model_root: Path = USER_SUPPORT_DIR / "models" / LOCAL_SUBDIR
        model_root.mkdir(parents=True, exist_ok=True)

        # Keep HF from spraying into a global .cache folder; confine to CDMF tree.
        os.environ.setdefault("HF_HUB_CACHE", str(model_root / "_hf_cache"))

        print(
            f"[CDMF] Downloading / loading prompt-lyrics model {MODEL_ID!r} -> {model_root}",
            flush=True,
        )

        local_dir = snapshot_download(
            repo_id=MODEL_ID,
            local_dir=str(model_root),
            local_dir_use_symlinks=False,
        )

        tokenizer = AutoTokenizer.from_pretrained(local_dir)
        # Let torch decide dtype; fp16 on CUDA, default on CPU.
        model = AutoModelForCausalLM.from_pretrained(
            local_dir,
            torch_dtype=torch.float16 if torch.cuda.is_available() else None,
        )
        model.eval()

        # Decide device for the pipeline.
        use_gpu = USE_GPU_ENV not in ("", "0", "false", "off", "no")
        if use_gpu and torch.cuda.is_available():
            device = 0  # cuda:0
            print(
                "[CDMF] lyrics LLM device set to cuda:0 (CDMF_LYRICS_USE_GPU=1).",
                flush=True,
            )
        else:
            device = -1  # CPU
            print(
                "[CDMF] lyrics LLM device set to CPU "
                "(set CDMF_LYRICS_USE_GPU=1 to try GPU).",
                flush=True,
            )

        _PIPELINE = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=device,
        )
        return _PIPELINE


# ---------------------------------------------------------------------------
# Robust prompt/lyrics extraction from LLM output
# ---------------------------------------------------------------------------


def _convert_braced_unicode_escapes(snippet: str) -> str:
    """
    Convert non-standard escapes of the form '\\u{1f483}' into real emoji chars
    so that json.loads() can succeed.

    This is *only* applied to the candidate JSON snippet, not to the full text.
    """

    def repl(match: re.Match[str]) -> str:
        hex_part = match.group(1)
        try:
            codepoint = int(hex_part, 16)
            return chr(codepoint)
        except Exception:
            # If anything goes wrong, drop the escape entirely rather than break JSON.
            return ""

    return re.sub(r"\\u\{([0-9a-fA-F]+)\}", repl, snippet)


def _fix_invalid_escapes(snippet: str) -> str:
    """
    Remove ONLY illegal backslashes that break json.loads(), while preserving
    valid JSON escapes ("\\", "/", "bfnrt", "uXXXX").
    """
    # First normalize '\\u{1f483}'-style escapes into actual characters.
    snippet = _convert_braced_unicode_escapes(snippet)
    # Then drop backslashes that are not part of a valid escape sequence.
    return re.sub(r'\\(?!["\\/bfnrtu])', "", snippet)


def _extract_first_json_object(text: str) -> Dict[str, Any] | None:
    """
    Try to recover the *best* JSON object with a 'prompt' key from a text-generation
    response.

    - Strips ```json fences.
    - Scans for balanced {...} blocks (tracking strings & escapes).
    - Fixes bad backslash escapes and '\\u{1f4xx}'-style emoji escapes.
    - Returns the largest valid dict with a 'prompt' key, or None on failure.
    """
    if not isinstance(text, str):
        return None

    cleaned = text.strip()

    # Strip ```json fences if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_+-]*\s*", "", cleaned)
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3].rstrip()

    # Quick path: maybe whole output is JSON already.
    try:
        obj = json.loads(_fix_invalid_escapes(cleaned))
        if isinstance(obj, dict) and "prompt" in obj:
            return obj
    except Exception:
        pass

    best_obj: Dict[str, Any] | None = None
    best_len = 0
    n = len(cleaned)
    i = 0

    while i < n:
        start = cleaned.find("{", i)
        if start == -1:
            break

        depth = 0
        in_string = False
        escape = False
        end = None

        for j in range(start, n):
            ch = cleaned[j]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break

        if end is None:
            i = start + 1
            continue

        snippet = cleaned[start:end]
        snippet_fixed = _fix_invalid_escapes(snippet)

        try:
            obj = json.loads(snippet_fixed)
        except Exception:
            i = start + 1
            continue

        if isinstance(obj, dict) and "prompt" in obj:
            span_len = end - start
            p = str(obj.get("prompt", "")).strip().lower()
            l = str(obj.get("lyrics", "")).strip().lower()
            # Skip obvious template placeholders if present.
            if p == "string" and l == "string":
                i = end
                continue
            if span_len > best_len:
                best_len = span_len
                best_obj = obj

        i = start + 1

    return best_obj


def _fallback_prompt_lyrics_from_text(
    raw_text: str,
    *,
    want_prompt: bool,
    want_lyrics: bool,
    concept: str,
) -> tuple[str, str]:
    """
    Extremely forgiving fallback when we couldn't get useful JSON.

    Heuristics:

      * Prompt: fall back to the high-level concept.
      * Lyrics: if requested, take from the first section tag like [intro]
        or after a 'Lyrics:' label. If nothing matches, leave lyrics empty
        and let the final placeholder guards decide (usually "[inst]" for
        instrumental).
    """
    prompt_out = concept.strip()
    lyrics_out = ""

    text = (raw_text or "").strip()
    if not text:
        return prompt_out, lyrics_out

    if want_lyrics:
        # Prefer content starting at a section tag [intro] / [verse] / etc.
        m = re.search(r"(\[[^\]]+\].*)", text, re.DOTALL)
        if m:
            lyrics_out = m.group(1).strip()
        else:
            # Otherwise, if there's a "Lyrics:" label, use content after it.
            m2 = re.search(r"(?i)lyrics\s*:(.*)", text, re.DOTALL)
            if m2:
                lyrics_out = m2.group(1).strip()

    return prompt_out, lyrics_out


def _is_placeholder(value: str) -> bool:
    """
    Detect obvious template / placeholder text that we don't want to
    commit into the prompt/lyrics fields.
    """
    v = (value or "").strip().lower()
    if not v:
        return True

    placeholders = {
        "string",
        "...",
        "<prompt text>",
        "<prompt>",
        "<prompt string>",
        "<lyrics text>",
        "<lyric text>",
        "<lyrics>",
        "<lyrics string>",
        "[prompt]",
        "[lyrics]",
        "prompt text",
        "lyric text",
        "example",
        "your prompt here",
        "your lyrics here",
    }
    return v in placeholders


# ---------------------------------------------------------------------------
# Public API used by cdmf_generation.prompt_lyrics_generate
# ---------------------------------------------------------------------------


def generate_prompt_and_lyrics(
    *,
    concept: str,
    want_prompt: bool,
    want_lyrics: bool,
    existing_prompt: str,
    existing_lyrics: str,
    target_seconds: float,
    target_lines: int,
    target_chars: int,
) -> Dict[str, Any]:
    """
    Core helper used by /prompt_lyrics/generate.

    Returns:
      {
        "prompt": "...",
        "lyrics": "...",
        "title":  "...",
        "raw_text": "<full LLM output for debugging>"
      }
    """
    global _PIPELINE
    pipe = _ensure_pipeline()

    # Build instructions for ACE-Step style prompts / lyrics
    length_rules: list[str] = []
    if target_lines > 0:
        length_rules.append(f"- Aim for ≈{target_lines} lines of lyrics.")
    if target_seconds > 0:
        length_rules.append(
            f"- Imagine a song of about {int(target_seconds)} seconds total."
        )

    length_hint = "\n".join(length_rules)

    # -----------------------------------------------------------------------
    # Instruction with concrete examples: one instrumental, one vocal
    # -----------------------------------------------------------------------
    instr: list[str] = [
        "You are an expert songwriter and producer for the ACE-Step music model.",
        "You design:",
        "  1) A detailed genre/style 'prompt' describing the sound of the track.",
        "  2) Optional song 'lyrics' in clear sections.",
        "",
        'You must reply ONLY with a single JSON object with exactly these keys:',
        '  { \"prompt\": \"string\", \"lyrics\": \"string\", \"title\": \"string\" }',
        "",
        "PROMPT RULES:",
        "- The 'prompt' must be a single line with comma-separated tags.",
        "- It should always include, in some order:",
        "    • Genre / style (e.g. 'medieval folk ballad', 'lo-fi hip hop'),",
        "    • Tempo (e.g. 'slow 70 bpm', 'mid-tempo 110 bpm'),",
        "    • 2–5 instruments (e.g. 'lute', 'flute', 'hand drums', 'female vocal'),",
        "    • Texture / mix words (e.g. 'warm reverb', 'intimate tavern',",
        "      'echoing stone hall', 'cinematic', 'lo-fi tape hiss'),",
        "    • Mood (e.g. 'melancholy', 'hopeful', 'mysterious').",
        "- Example instrumental prompt:",
        '  \"medieval folk ballad, slow 75 bpm, solo lute and wooden flute, gentle',
        '   hand drums, echoing stone hall reverb, melancholy but adventurous mood\"',
        "- Example vocal prompt:",
        '  \"fantasy tavern song, mid-tempo 100 bpm, lute and fiddle with soft',
        '   female vocal, crowd chant backing, warm candlelit tavern ambience,',
        '   bittersweet and nostalgic\"',
        "",
        "LYRICS FORMAT RULES:",
        "- The 'lyrics' field must contain formatted song lyrics.",
        "- Use sections like [intro], [verse], [chorus], [bridge], [outro].",
        "- Put the section tag on its own line, then 3–6 short lines underneath.",
        "- IMPORTANT: Each line must make sense grammatically and logically, i.e., do NOT end a line with a word that doesn't make sense.",
        "",
        "LYRICS RHYME RULES (VERY IMPORTANT – YOU MUST FOLLOW THESE):",
        "- In EVERY verse and chorus, almost all lines must clearly end in rhyming words.",
        "- Use simple end-rhyme patterns like ABAB or AABB.",
        "- That means the LAST WORD of line 1 should rhyme with the LAST WORD",
        "  of line 3 (ABAB), or line 2 (AABB), etc.",
        "- At least 3 out of 4 lines in each section must share an obvious rhyme",
        "  family (night/light/flight, cold/old/hold, stone/alone/unknown, etc.).",
        "- If a line does not rhyme with any other line in its section, REWRITE it so it does.",
        "- Do NOT rhyme a word with itself. I.e. do not use 'sun' at the end of two lines in a row.",
        "",
        "- GOOD example (AABB):",
        "  [verse]",
        "  I walk the road alone at night",
        "  My only guide the distant light",
        "  The mountains whisper soft and cold",
        "  Of stories I was never cold",
        "",
        "- BAD example (do NOT do this – the endings do not rhyme):",
        "  [verse]",
        "  I walk the road alone at night",
        "  The wind is sharp and cuts like stone",
        "  My heart remembers distant fires",
        "  I wonder if I'll find a home",
        "",
        "- Your output MUST behave like the GOOD example, not the BAD one.",
        "- Prioritize clear, simple rhymes over complex vocabulary.",
        "- Prioritize rhythm/meter. The syllable count should make the lines easy to sing.",
        "",
        "- Aim for simple, singable lines with a steady rhythm.",
        "- Line pairs should end in rhymes (night/light, road/home, etc.);",
        "  do NOT just describe the scene in prose.",
        "- Use emoji sparingly (at most a few total). It is fine to use none.",
        "",
        "TITLE RULES:",
        "- The 'title' MUST be a short, evocative song name.",
        "- 2–6 words; no quotes, no trailing punctuation.",
        "- Use Title Case (capitalize main words).",
        "- Avoid generic placeholders like 'Song Title' or 'Track 1'.",
        "",
        "INSTRUMENTAL CASE:",
        "- If this track is meant to be purely instrumental and no lyrics are",
        '  desired, set \"lyrics\" to exactly \"[inst]\" and do not write any verses.',
        "",
        "PLACEHOLDERS (DO NOT USE):",
        "- Never use placeholders as entire fields: not 'string', '...',",
        "  '<prompt text>', '<lyrics text>', '<prompt string>',",
        "  '<lyrics string>', 'example', or similar.",
        "",
        "OUTPUT FORMAT:",
        "- Output ONLY one JSON object with keys 'prompt', 'lyrics', and 'title'.",
        "- Do NOT add any explanation or commentary before or after the JSON.",
    ]

    if not want_lyrics:
        instr.append(
            '- For this request the main focus is the "prompt" field. '
            'Set "lyrics" to exactly "[inst]" and do not write any verses.'
        )
    if not want_prompt:
        instr.append(
            "- For this request the lyrics are more important than the prompt, but "
            "you MUST still output all keys in the JSON object."
        )

    if length_hint:
        instr.append("")
        instr.append("Length hints for the lyrics (if any):")
        instr.append(length_hint)

    # -----------------------------------------------------------------------
    # Concrete JSON example to imitate
    # -----------------------------------------------------------------------
    instr.extend(
        [
            "",
            "EXAMPLE OF CORRECT OUTPUT FORMAT:",
            "{",
            '  \"prompt\": \"medieval folk ballad, slow 75 bpm, lute, flute, hand drums, echoing hall reverb, melancholy but adventurous\",',
            '  \"lyrics\": \"[verse]\\nI walk the road alone at night\\nMy only guide the distant light\\nThe mountains whisper soft and cold\\nOf stories I was never told\\n\\n[chorus]\\n...\",',
            '  \"title\": \"Road Of Night\"',
            "}",
            "",
            "Do NOT copy these exact words. This is only an example of the JSON shape.",
        ]
    )

    instr.append("")
    instr.append("Song concept (high level; do NOT copy it word-for-word):")
    instr.append(concept.strip())
    instr.append("")

    # Final, hard constraints at the very end (small models weight this heavily)
    instr.extend(
        [
            "",
            "FINAL, VERY IMPORTANT RULES (YOU MUST FOLLOW ALL OF THESE):",
            "- Your reply MUST be a single valid JSON object with keys 'prompt', 'lyrics', 'title'.",
            "- The 'lyrics' string MUST contain at least two section tags like [verse] and [chorus].",
            "- In each [verse] and [chorus], write 3–6 lines, and MOST line endings must rhyme",
            "  in a simple pattern (ABAB or AABB).",
            "- If you do not include [verse]/[chorus] tags or rhyming line endings, your answer is WRONG.",
            "",
            "Reply now with ONLY the JSON. Do not add explanations or any extra text.",
        ]
    )

    # -----------------------------------------------------------------------
    # Build model input (prefer chat template if available)
    # -----------------------------------------------------------------------
    tokenizer = getattr(pipe, "tokenizer", None)
    instr_text = "\n".join(instr)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert songwriter and producer for the ACE-Step music model. "
                "You MUST obey the output format exactly and always return valid JSON."
            ),
        },
        {
            "role": "user",
            "content": instr_text,
        },
    ]

    chat_prompt = None
    model_input = instr_text

    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        try:
            chat_prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            model_input = chat_prompt
        except Exception as exc:
            print(
                "[CDMF] lyrics_generate warning: apply_chat_template failed; "
                f"falling back to plain prompt: {exc}",
                flush=True,
            )

    # Slightly more creative but still controlled sampling
    outputs = pipe(
        model_input,
        max_new_tokens=512,
        do_sample=True,
        temperature=0.8,
        top_p=0.95,
        top_k=40,
        repetition_penalty=1.02,
    )

    if (
        not outputs
        or not isinstance(outputs, list)
        or "generated_text" not in outputs[0]
    ):
        raise RuntimeError(f"Unexpected LLM output: {outputs!r}")

    raw_full = outputs[0]["generated_text"]

    # If we used a chat template and the model echoed the prompt, strip it off.
    if chat_prompt and raw_full.startswith(chat_prompt):
        raw_text = raw_full[len(chat_prompt) :]
    else:
        raw_text = raw_full

    # Debug: always log a truncated view of what the model actually produced.
    print(
        "[CDMF] lyrics_generate raw LLM output (first 500 chars):",
        repr(raw_text[:500]),
        flush=True,
    )

    # -----------------------------------------------------------------------
    # Step 1: JSON-based extraction (preferred)
    # -----------------------------------------------------------------------
    obj = _extract_first_json_object(raw_text)

    if obj is not None:
        prompt_val = obj.get("prompt", "")
        lyrics_val = obj.get("lyrics", "")
        title_val = obj.get("title", "")
    else:
        prompt_val = ""
        lyrics_val = ""
        title_val = ""

    # Accept either strings or lists from the model
    if isinstance(prompt_val, (list, tuple)):
        prompt_out = " ".join(str(x) for x in prompt_val if str(x).strip()).strip()
    else:
        prompt_out = str(prompt_val or "").strip()

    if isinstance(lyrics_val, (list, tuple)):
        lyrics_out = "\n".join(str(x) for x in lyrics_val if str(x).strip()).strip()
    else:
        lyrics_out = str(lyrics_val or "").strip()

    if isinstance(title_val, (list, tuple)):
        title_out = " ".join(str(x) for x in title_val if str(x).strip()).strip()
    else:
        title_out = str(title_val or "").strip()

    # If JSON was missing or clearly template-ish, fall back to heuristic parsing.
    need_fallback = False

    if obj is None:
        print(
            "[CDMF] lyrics_generate warning: no valid prompt/lyrics JSON block could "
            "be parsed; attempting heuristic fallback.",
            flush=True,
        )
        need_fallback = True
    else:
        # If the model gave only placeholders for either field we actually care about,
        # treat that as a failure and fall back.
        if (want_prompt and _is_placeholder(prompt_out)) or (
            want_lyrics and _is_placeholder(lyrics_out)
        ):
            print(
                "[CDMF] lyrics_generate warning: JSON prompt/lyrics look like "
                "placeholders; attempting heuristic fallback.",
                flush=True,
            )
            need_fallback = True

        # Hard-format check: if we want lyrics but there are no section tags, treat as failure.
        if want_lyrics and not re.search(r"\[[^\]]+\]", lyrics_out):
            print(
                "[CDMF] lyrics_generate warning: JSON lyrics have no section tags; "
                "attempting heuristic fallback.",
                flush=True,
            )
            need_fallback = True

    if need_fallback:
        prompt_out, lyrics_out = _fallback_prompt_lyrics_from_text(
            raw_text,
            want_prompt=want_prompt,
            want_lyrics=want_lyrics,
            concept=concept,
        )

    # -----------------------------------------------------------------------
    # Fallbacks / placeholder guards (final)
    # -----------------------------------------------------------------------
    # Prompt: fall back to the concept if the model phoned it in.
    if _is_placeholder(prompt_out):
        prompt_out = concept.strip()

    # Lyrics:
    if _is_placeholder(lyrics_out):
        # If we didn't get usable lyrics, treat as instrumental by default.
        lyrics_out = "[inst]"

    # Title: if it's missing or placeholder, salvage something from the concept
    if _is_placeholder(title_out) or not title_out.strip():
        base = concept.strip()
        if base:
            plain = re.sub(r"[\[\]\{\}\(\)\"']", "", base)
            words = plain.split()
            if words:
                title_out = " ".join(words[:6]).strip().title()
            else:
                title_out = ""
        else:
            title_out = ""

    # Normalize any literal "\n" from the model into real newlines
    if "\\n" in lyrics_out:
        lyrics_out = lyrics_out.replace("\\n", "\n")

    # -----------------------------------------------------------------------
    # Light cleanup: kill colon after tags, strip heavy emoji spam, tidy spaces
    # -----------------------------------------------------------------------
    # [verse]: -> [verse]
    lyrics_out = re.sub(r"\[([^\]]+)\]\s*:", r"[\1]", lyrics_out)
    # Remove repeated note/shine emojis if the model gets cute
    lyrics_out = re.sub(r"[🎵🎶✨⭐🌙💫]+", "", lyrics_out)
    # Trim stray spaces before newlines
    lyrics_out = re.sub(r"[ \t]+\n", "\n", lyrics_out)
    lyrics_out = lyrics_out.strip()

    # If we *asked* for lyrics and the model started with [inst] but then
    # clearly wrote more lines, strip the [inst] marker.
    if want_lyrics and lyrics_out.lower().startswith("[inst]") and "\n" in lyrics_out:
        lyrics_out = lyrics_out.split("\n", 1)[1].lstrip()

    # Final debug logging so we can see what will go back to Flask.
    print(
        "[CDMF] lyrics_generate final prompt:",
        repr(prompt_out),
        flush=True,
    )
    print(
        "[CDMF] lyrics_generate final lyrics (first 200 chars):",
        repr(lyrics_out[:200]),
        flush=True,
    )
    print(
        "[CDMF] lyrics_generate final title:",
        repr(title_out),
        flush=True,
    )

    # -------------------------------------------------------------------
    # GPU offload after use:
    # If the pipeline is on CUDA, move the model back to CPU, clear the
    # CUDA cache, and drop the cached pipeline so the next run will
    # rebuild it on demand. On CPU-only runs we keep the pipeline hot.
    # -------------------------------------------------------------------
    try:
        pipe_device = getattr(pipe, "device", None)
        if torch.cuda.is_available() and getattr(pipe_device, "type", None) == "cuda":
            try:
                model_ref = getattr(pipe, "model", None)
                if model_ref is not None:
                    model_ref.to("cpu")
            except Exception as exc:
                print(
                    "[CDMF] lyrics_generate warning: failed to move LLM back to CPU:",
                    exc,
                    flush=True,
                )
            try:
                torch.cuda.empty_cache()
            except Exception as exc:
                print(
                    "[CDMF] lyrics_generate warning: torch.cuda.empty_cache() failed:",
                    exc,
                    flush=True,
                )
    finally:
        pipe_device = getattr(pipe, "device", None)
        if torch.cuda.is_available() and getattr(pipe_device, "type", None) == "cuda":
            _PIPELINE = None

    return {
        "prompt": prompt_out,
        "lyrics": lyrics_out,
        "title": title_out,
        "raw_text": raw_text,
    }
