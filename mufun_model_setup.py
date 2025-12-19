from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional, Callable, Tuple, Any, Dict

from huggingface_hub import snapshot_download

# Hugging Face repo for MuFun-ACEStep
MUFUN_REPO_ID = "Yi3852/MuFun-ACEStep"

# Local cache root for MuFun under the AceForge app directory.
# Layout will look like:
#   models/mufun_acestep/
#     blobs/
#     models--Yi3852--MuFun-ACEStep/
MUFUN_CACHE_ROOT = Path(__file__).resolve().parent / "models" / "mufun_acestep"

ProgressCallback = Callable[[float], None]

_MUFUN_MODEL = None
_MUFUN_TOKENIZER = None
_MUFUN_DEVICE = "cpu"


def _normalize_mufun_lyrics(text: str) -> str:
    """
    Normalize MuFun 'lyrics' output.

    If MuFun returns standard Chinese phrases for 'instrumental only'
    (e.g. '纯音乐，请欣赏'), map them to ACE-Step's [inst] token.

    If empty, default to [inst] so instrumental tracks are always
    trainable without hand-editing.
    """
    t = (text or "").strip()
    if not t:
        return "[inst]"

    # Strip common punctuation / spaces and compare normalized string.
    simplified = (
        t.replace("！", "")
        .replace("。", "")
        .replace("，", "")
        .replace(",", "")
        .replace(" ", "")
    )

    if simplified in ("纯音乐请欣赏", "纯音乐"):
        return "[inst]"

    return t


def _normalize_mufun_prompt(text: str) -> str:
    """
    Clean up MuFun 'prompt' tag strings:

      * Fix known typos (exurberant → exuberant)
      * Drop junk tags (other, absolute music, internal use)
      * Deduplicate tags
      * Re-capitalize nicely
    """
    if not text:
        return ""

    raw_parts = [p.strip() for p in str(text).split(",")]
    cleaned: list[str] = []
    seen: set[str] = set()

    blacklist = {"other", "absolute music", "internal use"}
    replacements = {
        "exurberant": "exuberant",
        # Seen in sample output; normalize this into a nicer form.
        "instrumentalpop": "instrumental pop",
    }

    for part in raw_parts:
        if not part:
            continue

        lower = part.lower()
        # Apply typo fixes first
        if lower in replacements:
            part = replacements[lower]
            lower = part.lower()

        if lower in blacklist:
            continue

        if lower in seen:
            continue

        seen.add(lower)

        # Simple "nice" capitalization without overthinking it
        if part and not part[0].isupper():
            part = part[0].upper() + part[1:]

        cleaned.append(part)

    return ", ".join(cleaned)


def merge_base_and_mufun_tags(base_prompt: str, mufun_prompt: str) -> str:
    """
    Merge user/base tags with MuFun's generated tags and normalize the result.

    - Base tags stay at the front, in their original order.
    - MuFun tags are appended.
    - Exact duplicates (case-insensitive) across BOTH sets are removed.
    - All tags go through _normalize_mufun_prompt for typo-fixing and cleanup.

    Example:
        base_prompt = "SNES, 16-bit, 8-bit, chiptunes, video game, JRPG"
        mufun_prompt = "8-bit, 16-bit, Chiptunes, Chiptune, Game, Retro game"

        → "Snes, 16-bit, 8-bit, Chiptunes, Video game, Jrpg, Chiptune, Game, Retro game"
    """
    base_prompt = (base_prompt or "").strip()
    mufun_prompt = (mufun_prompt or "").strip()

    if base_prompt and mufun_prompt:
        combined = f"{base_prompt}, {mufun_prompt}"
    else:
        combined = base_prompt or mufun_prompt

    return _normalize_mufun_prompt(combined)


def _build_tqdm_with_progress_cb(progress_cb: ProgressCallback):
    """
    Build a tqdm subclass that forwards overall progress [0, 1] to
    the given callback. We mirror the pattern used for ACE-Step so
    the UI can surface download progress if desired.
    """
    from tqdm.auto import tqdm as base_tqdm  # type: ignore[import]

    class HFProgressTqdm(base_tqdm):  # type: ignore[misc]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._last_ratio = 0.0

        def update(self, n=1):
            res = super().update(n)
            try:
                if self.total:
                    ratio = float(self.n) / float(self.total)
                else:
                    ratio = 0.0
                if ratio - self._last_ratio >= 0.01 or ratio >= 1.0:
                    self._last_ratio = ratio
                    progress_cb(ratio)
            except Exception:
                # Swallow any progress callback failure; download should continue.
                pass
            return res

    return HFProgressTqdm


def mufun_model_present() -> bool:
    """
    Lightweight check: treat the MuFun model as present if we can find at least
    one config.json anywhere under MUFUN_CACHE_ROOT, without triggering any
    network downloads.
    """
    root = MUFUN_CACHE_ROOT
    if not root.is_dir():
        return False

    for p in root.rglob("config.json"):
        return True

    # Fallback: non-empty directory
    try:
        next(root.iterdir())
        return True
    except StopIteration:
        return False


def ensure_mufun_model(progress_cb: Optional[ProgressCallback] = None) -> Path:
    """
    Ensure the MuFun-ACEStep model snapshot is present under MUFUN_CACHE_ROOT.

    Returns the *snapshot directory* (the folder that actually contains
    config.json, model weights, etc.). If `progress_cb` is provided, it will
    be called with a float in [0, 1] reflecting approximate download progress.
    """
    target_dir = MUFUN_CACHE_ROOT

    # If we already have a config.json somewhere under target_dir, treat that
    # as the snapshot root and bail out early.
    snapshot_dir: Optional[Path] = None
    if target_dir.is_dir():
        for p in target_dir.rglob("config.json"):
            snapshot_dir = p.parent
            break

    if snapshot_dir is not None:
        if progress_cb is not None:
            try:
                progress_cb(1.0)
            except Exception:
                pass
        return snapshot_dir

    print("[CDMF] MuFun-ACEStep model not found at:")
    print(f"       {target_dir}")
    print("[CDMF] Downloading from Hugging Face repo:", MUFUN_REPO_ID)
    print("[CDMF] This is a large download (several GB). Please wait...")

    # Ensure parent exists
    target_dir.mkdir(parents=True, exist_ok=True)

    tqdm_class = None
    if progress_cb is not None:
        try:
            tqdm_class = _build_tqdm_with_progress_cb(progress_cb)
        except Exception:
            tqdm_class = None

    snapshot_dir = None

    try:
        kwargs = {
            "repo_id": MUFUN_REPO_ID,
            "local_dir": str(target_dir),
        }
        if tqdm_class is not None:
            kwargs["tqdm_class"] = tqdm_class

        snapshot_path = snapshot_download(**kwargs)
        snapshot_dir = Path(snapshot_path)
    except TypeError as t_err:
        # Older huggingface_hub may not support tqdm_class.
        print(
            "[CDMF] WARNING: snapshot_download() does not support tqdm_class; "
            "download progress will not be reflected precisely:",
            t_err,
        )
        snapshot_path = snapshot_download(
            repo_id=MUFUN_REPO_ID,
            local_dir=str(target_dir),
        )
        snapshot_dir = Path(snapshot_path)
    except Exception as exc:
        # On Windows, huggingface can sometimes trip over its own .incomplete
        # cleanup even though the files are actually present. If we can see a
        # config.json on disk, treat that as success instead of hard failing.
        print("[CDMF] ERROR: Failed to download MuFun-ACEStep model:", exc)
        print("       If you already downloaded it manually,")
        print("       place the model contents here:")
        print(f"       {target_dir}")

        snapshot_dir = None
        if target_dir.is_dir():
            for p in target_dir.rglob("config.json"):
                snapshot_dir = p.parent
                break

        if snapshot_dir is not None:
            print(
                "[CDMF] Detected MuFun files on disk despite download error; "
                "treating model as present."
            )
            if progress_cb is not None:
                try:
                    progress_cb(1.0)
                except Exception:
                    pass
            return snapshot_dir

        # No usable files: this really is a failure.
        raise

    # Normal success path.
    print("[CDMF] MuFun-ACEStep cache ready at:", snapshot_dir)
    if progress_cb is not None:
        try:
            progress_cb(1.0)
        except Exception:
            pass

    return snapshot_dir


def _load_mufun_model() -> Tuple[Any, Any, str]:
    """
    Load (and, on first run, download) the MuFun-ACEStep model using the
    local snapshot directory under MUFUN_CACHE_ROOT.

    Returns (tokenizer, model, device).
    """
    global _MUFUN_MODEL, _MUFUN_TOKENIZER, _MUFUN_DEVICE

    if _MUFUN_MODEL is not None and _MUFUN_TOKENIZER is not None:
        return _MUFUN_TOKENIZER, _MUFUN_MODEL, _MUFUN_DEVICE

    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM  # type: ignore[import]
        import torch  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "MuFun-ACEStep support requires 'transformers' and 'torch' to be "
            "installed in the AceForge virtual environment."
        ) from exc

    # Make sure the snapshot exists first (cheap no-op if already present),
    # and capture the actual snapshot directory path.
    snapshot_dir = ensure_mufun_model()

    device = "cuda" if torch.cuda.is_available() else "cpu"

    print(
        f"[CDMF] Loading MuFun-ACEStep model "
        f"(device={device}, snapshot_dir={snapshot_dir})",
        flush=True,
    )

    # IMPORTANT: load directly from the on-disk snapshot directory, instead of
    # asking transformers/huggingface_hub to manage its own cache in the same
    # folder again (which is where the .incomplete WinError came from).
    tokenizer = AutoTokenizer.from_pretrained(
        str(snapshot_dir),
        use_fast=False,
        trust_remote_code=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        str(snapshot_dir),
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
    ).to(device)

    _MUFUN_MODEL = model
    _MUFUN_TOKENIZER = tokenizer
    _MUFUN_DEVICE = device

    return tokenizer, model, device


def mufun_analyze_file(audio_path: str, force_instrumental: bool = False) -> Dict[str, Any]:
    """
    Run MuFun-ACEStep on a single audio file and return whatever it says.

    The model card suggests sending this prompt:

        '<audio>\\nDeconstruct this song, listing its tags and lyrics. "
        "Directly output a JSON object with prompt and lyrics fields, "
        "without any additional explanations or text.'

    We will try to parse the result as JSON; if that fails, we return
    a dict with a 'raw_text' field instead.

    On success, this function normalizes:
      * lyrics → maps '纯音乐，请欣赏' variants to [inst]
      * prompt → cleaned, deduped tag string

    If force_instrumental is True, the returned 'lyrics' field is
    forcibly set to "[inst]" regardless of what MuFun predicted, while
    preserving the original text in 'raw_lyrics' for debugging.
    """
    import json as _json

    tokenizer, model, _device = _load_mufun_model()

    prompt = (
        "<audio>\n"
        "You are an expert tagging assistant for the ACE-Step music model.\n"
        "Listen to the audio and assign accurate, concise English tags and lyrics.\n"
        "\n"
        "Output a single JSON object with exactly these fields:\n"
        "  {\"prompt\": \"comma-separated tags\", \"lyrics\": \"lyrics text or [inst]\"}\n"
        "\n"
        "Rules:\n"
        "- Use only English.\n"
        "- The \"prompt\" field MUST be a short, comma-separated list of tags.\n"
        "- Choose the single best set of 5–15 tags for the track, not every possible tag.\n"
        "- Prefer tags from the vocabulary below; avoid typos and unusual phrases.\n"
        "- If the track has no vocals or lyrics (pure instrumental), set \"lyrics\" to \"[inst]\" exactly.\n"
        "- Otherwise, put the main sung/rap lyrics in \"lyrics\" (not a description).\n"
        "- Do not add explanations, commentary, or extra text outside the JSON object.\n"
        "\n"
        "Tag vocabulary (prefer these; choose the best 5–15 tags per track):\n"
        "\n"
        "Genres / styles (game, media, general):\n"
        "  chiptune, chiptunes, 8-bit, 16-bit, SNES, NES, Game Boy, Sega Genesis, retro game,\n"
        "  video game soundtrack, game music, JRPG, RPG, action RPG, boss battle, mini boss,\n"
        "  final boss, menu theme, field theme, dungeon theme, battle theme, victory fanfare,\n"
        "  defeat theme, overworld, platformer, arcade, metroidvania, roguelike, roguelite,\n"
        "  shmup, bullet hell, racing game, fighting game, rhythm game, puzzle game,\n"
        "  horror game, survival horror, strategy game, tactics game, visual novel, dating sim,\n"
        "  town theme, village theme, city theme, castle theme, sky theme, snowfield theme,\n"
        "  desert theme, forest theme, jungle theme, swamp theme, cave theme, volcano theme,\n"
        "  underwater theme, space theme, sci-fi, cyberpunk, city night, neon city,\n"
        "  fantasy, dark fantasy, high fantasy, steampunk, western, medieval, oriental fantasy,\n"
        "  lo-fi, lofi, lo-fi hip hop, chillhop, hip hop, boom bap, trap, drill, phonk,\n"
        "  trap metal, pop, synthpop, city pop, K-pop, J-pop, anime opening, anime ending,\n"
        "  rock, alt rock, alternative rock, indie rock, pop rock, hard rock, punk rock,\n"
        "  pop punk, emo, post rock, shoegaze, metal, heavy metal, power metal, prog metal,\n"
        "  metalcore, death metal, black metal, djent,\n"
        "  blues, funk, fusion, jazz, smooth jazz, jazz fusion, big band, swing,\n"
        "  soul, neo soul, R&B, gospel, worship, choir,\n"
        "  folk, acoustic, singer songwriter, country, country pop, bluegrass,\n"
        "  reggae, ska, afrobeat, afro pop, latin, reggaeton, salsa, bossa nova,\n"
        "  EDM, electronic, electro, electro house, deep house, tropical house,\n"
        "  progressive house, techno, minimal techno, trance, psytrance, hardstyle,\n"
        "  eurobeat, drum and bass, DnB, jungle, liquid DnB, breakbeat, breaks,\n"
        "  IDM, glitch, glitch hop, dubstep, brostep, riddim,\n"
        "  ambient, dark ambient, drone, soundscape, chillout, downtempo, trip hop,\n"
        "  synthwave, retrowave, vaporwave, future funk, future bass,\n"
        "  industrial, experimental, avant-garde,\n"
        "  orchestral, cinematic, hybrid orchestral, trailer, soundtrack, film score,\n"
        "  piano solo, piano ballad, ballad, choral, acapella, band, live band.\n"
        "\n"
        "Moods / emotions:\n"
        "  cheerful, happy, joyful, upbeat, optimistic, hopeful, uplifting,\n"
        "  triumphant, victorious, epic, heroic, adventurous, brave, determined,\n"
        "  empowering, confident,\n"
        "  playful, cute, whimsical, quirky, silly, goofy, fun,\n"
        "  dreamy, floaty, nostalgic, bittersweet, melancholic, sad, tragic,\n"
        "  lonely, introspective, reflective, pensive, emotional,\n"
        "  romantic, tender, intimate, heartfelt,\n"
        "  sensual, sexy, seductive,\n"
        "  mysterious, eerie, spooky, haunting, ominous, tense, suspenseful,\n"
        "  foreboding, dark, brooding, grim, sinister,\n"
        "  angry, aggressive, intense, furious, menacing, chaotic, manic, hectic,\n"
        "  energetic, driving, urgent, powerful,\n"
        "  calm, relaxed, laid back, soothing, peaceful, gentle, soft,\n"
        "  meditative, zen, atmospheric, otherworldly, ethereal, spiritual.\n"
        "\n"
        "Energy / tempo / density:\n"
        "  very slow, slow, ballad tempo, medium tempo, midtempo,\n"
        "  fast, very fast, uptempo,\n"
        "  low energy, mellow, chill, moderate energy, high energy,\n"
        "  driving rhythm, steady groove, bouncy, punchy, heavy, light,\n"
        "  sparse, minimal, stripped-down, dense, busy, layered, massive,\n"
        "  halftime feel, double-time feel,\n"
        "  four on the floor, straight rhythm, swung rhythm, shuffle feel, syncopated.\n"
        "\n"
        "Texture / production / era:\n"
        "  retro, vintage, modern,\n"
        "  8-bit, 16-bit, SNES-style, NES-style, PS1-style, PS2-style, arcade-style,\n"
        "  chip-based, FM-synthesis, sample-based,\n"
        "  low-fi, lo-fi, hi-fi,\n"
        "  analog, digital, tape, cassette, vinyl, vinyl crackle,\n"
        "  warm, bright, dark tone, crisp, clear, polished, glossy,\n"
        "  raw, rough, gritty, dirty, noisy,\n"
        "  distorted, overdriven, saturated, crunchy, bitcrushed,\n"
        "  glitchy, chopped, stuttered, granular, filtered, muffled, underwater,\n"
        "  reverb heavy, echoey, delay heavy, dry, close-miked,\n"
        "  wide stereo, narrow stereo, mono, spacious,\n"
        "  cinematic, huge, wall of sound, intimate,\n"
        "  80s-style, 90s-style, 2000s-style, Y2K, club mix, live recording, studio recording.\n"
        "\n"
        "Instruments / instrumentation (non-vocal):\n"
        "  piano, grand piano, upright piano, felt piano, detuned piano,\n"
        "  electric piano, Rhodes, Wurlitzer,\n"
        "  organ, Hammond organ, church organ,\n"
        "  synth lead, square wave lead, pulse wave lead, saw lead, triangle lead, sine lead,\n"
        "  supersaw, chiptune lead, chiptune arps, arpeggios, sequencer,\n"
        "  synth pad, warm pad, analog pad, string pad, choir pad,\n"
        "  pluck synth, synth plucks,\n"
        "  strings, string ensemble, string section, string quartet,\n"
        "  violin, violins, viola, cello, contrabass,\n"
        "  pizzicato strings, staccato strings, legato strings, spiccato strings,\n"
        "  brass, orchestral brass, trumpet, trombone, french horn, tuba,\n"
        "  horn section, brass stabs,\n"
        "  woodwinds, flute, piccolo, recorder, clarinet, bass clarinet,\n"
        "  oboe, english horn, bassoon, saxophone, alto sax, tenor sax, baritone sax,\n"
        "  pan flute, ocarina, shakuhachi,\n"
        "  harp, koto, shamisen, erhu, guzheng, pipa, sitar,\n"
        "  marimba, xylophone, vibraphone, glockenspiel, bell, chimes,\n"
        "  tubular bells, celesta, music box,\n"
        "  acoustic guitar, nylon guitar, steel-string guitar, 12-string guitar,\n"
        "  classical guitar, flamenco guitar,\n"
        "  electric guitar, clean guitar, crunch guitar, distorted guitar,\n"
        "  overdriven guitar, lead guitar, rhythm guitar, power chords,\n"
        "  acoustic strums, acoustic picking,\n"
        "  banjo, mandolin, ukulele, lap steel, pedal steel,\n"
        "  bass, bass guitar, fretless bass, slap bass, acoustic bass, double bass,\n"
        "  synth bass, chiptune bass, acid bass, 303 bass, sub bass, 808 bass,\n"
        "  drum kit, acoustic drums, electronic drums, drum machine,\n"
        "  drum loop, breakbeat, jungle drums,\n"
        "  kick, 808 kick, snare, rimshot, clap, rim clicks,\n"
        "  hi-hat, closed hats, open hats, ride cymbal, crash cymbal, china cymbal,\n"
        "  cymbal swell, reverse cymbal,\n"
        "  toms, floor tom, percussion, hand percussion,\n"
        "  shakers, tambourine, congas, bongos, timbales, cowbell, woodblock, claves,\n"
        "  cajon, triangle, castanets,\n"
        "  steel drum, kalimba, thumb piano, handpan,\n"
        "  riser, impact, hit, boom, whoosh, sweep, noise FX, sound effects, drones.\n"
        "\n"
        "Vocals / voice:\n"
        "  no vocals, vocals, lead vocal, backing vocals, harmonies, stacked vocals,\n"
        "  call and response, group vocals,\n"
        "  male vocal, female vocal, child vocal,\n"
        "  choir, boys choir, girls choir, mixed choir, chant, chanting, crowd chant,\n"
        "  rap, rap verse, rap chorus, fast rap,\n"
        "  spoken word, narration, voiceover,\n"
        "  whisper vocal, soft vocal, breathy vocal, gentle vocal,\n"
        "  belt vocal, powerful vocal, falsetto,\n"
        "  screaming, growling, harsh vocals, metal screams,\n"
        "  vocoder, talkbox, robotic voice,\n"
        "  processed vocals, autotune, heavy autotune,\n"
        "  vocal chops, vocal samples, chopped vocals, shout samples.\n"
        "\n"
        "Rhythm / groove / feel:\n"
        "  straight groove, swung groove, shuffle groove,\n"
        "  offbeat, syncopated, polyrhythmic,\n"
        "  halftime groove, double-time groove,\n"
        "  four on the floor, two-step, waltz feel, march feel,\n"
        "  boom bap drums, trap hi-hats, drill drums,\n"
        "  funk groove, reggae groove, reggaeton groove, dembow groove.\n"
        "\n"
        "Usage / context:\n"
        "  looping BGM, background music, ambience,\n"
        "  stage theme, level theme, world map theme, area theme,\n"
        "  dungeon theme, battle theme, boss fight, mini boss fight, final boss,\n"
        "  battle results, victory fanfare, defeat theme, game over,\n"
        "  title screen, main menu, pause menu, settings menu, inventory screen,\n"
        "  shop, inn, tavern theme, bar theme, hub area, safe room,\n"
        "  town theme, village theme, city theme, castle theme, royal palace,\n"
        "  church theme, temple theme, shrine theme, sacred place,\n"
        "  forest theme, jungle theme, desert theme, snowfield theme, mountain theme,\n"
        "  cave theme, mine theme, swamp theme, volcano theme, lava area,\n"
        "  sky island, airship theme, beach theme, harbor theme, harbor town,\n"
        "  spaceship theme, space station, sci-fi lab, factory theme, industrial area,\n"
        "  cyber city, hacker den, hideout theme,\n"
        "  stealth mission, infiltration, heist, chase scene, racing, time attack,\n"
        "  training mode, tutorial, puzzle, puzzle room, mini game,\n"
        "  cutscene, prologue, epilogue, character theme,\n"
        "  opening theme, ending theme, credits,\n"
        "  trailer, teaser, montage, highlight reel,\n"
        "  streaming background, study music, focus music, sleep music, meditation music.\n"
        "\n"
        "Environment / soundscape:\n"
        "  rain ambience, storm ambience, thunder, wind ambience, snowstorm,\n"
        "  ocean waves, river, waterfall,\n"
        "  forest ambience, birdsong, insects,\n"
        "  city ambience, traffic ambience, crowd ambience, cafe ambience,\n"
        "  stadium ambience, arena ambience, subway ambience, train ambience,\n"
        "  machine hum, engine hum, computer room, server room,\n"
        "  fire crackle, fireplace, campfire,\n"
        "  cave reverb, cathedral reverb, large hall reverb.\n"
        "\n"
        "Return ONLY the JSON object with \"prompt\" and \"lyrics\".\n"
    )

    # Per the MuFun-ACEStep README, .chat signature is:
    #   res = model.chat(prompt=prompt, audio_files=aud, segs=None, tokenizer=tokenizer)
    res = model.chat(
        prompt=prompt,
        audio_files=audio_path,
        segs=None,
        tokenizer=tokenizer,
    )

    # Dict → normalize in place but preserve raw values for debugging.
    if isinstance(res, dict):
        out: Dict[str, Any] = dict(res)

        raw_prompt = str(out.get("prompt", "") or "")
        raw_lyrics = str(out.get("lyrics", "") or "")

        out["raw_prompt"] = out.get("raw_prompt", raw_prompt)
        out["raw_lyrics"] = out.get("raw_lyrics", raw_lyrics)

        normalized_prompt = _normalize_mufun_prompt(raw_prompt)
        normalized_lyrics = _normalize_mufun_lyrics(raw_lyrics)

        if force_instrumental:
            normalized_lyrics = "[inst]"

        out["prompt"] = normalized_prompt
        out["lyrics"] = normalized_lyrics

        return out

    # String → try to parse as JSON, then normalize; otherwise surface as raw_text.
    if isinstance(res, str):
        try:
            data = _json.loads(res)
        except Exception:
            # Not strict JSON; just return the raw text so the caller can see it.
            result: Dict[str, Any] = {"raw_text": res}
            if force_instrumental:
                result["lyrics"] = "[inst]"
            return result

        if not isinstance(data, dict):
            result = {"raw_text": res}
            if force_instrumental:
                result["lyrics"] = "[inst]"
            return result

        raw_prompt = str(data.get("prompt", "") or "")
        raw_lyrics = str(data.get("lyrics", "") or "")

        data["raw_prompt"] = data.get("raw_prompt", raw_prompt)
        data["raw_lyrics"] = data.get("raw_lyrics", raw_lyrics)

        normalized_prompt = _normalize_mufun_prompt(raw_prompt)
        normalized_lyrics = _normalize_mufun_lyrics(raw_lyrics)

        if force_instrumental:
            normalized_lyrics = "[inst]"

        data["prompt"] = normalized_prompt
        data["lyrics"] = normalized_lyrics

        return data

    # Fallback for any other type
    try:
        result = {"raw_text": str(res)}
    except Exception:
        result = {"raw_text": "MuFun returned an unprintable object."}

    if force_instrumental:
        # Even on weird outputs, guarantee the lyrics we write for an
        # instrumental dataset are [inst].
        result["lyrics"] = "[inst]"

    return result


if __name__ == "__main__":
    # Allow manual testing:
    #   python mufun_model_setup.py path/to/song.wav
    if len(sys.argv) < 2:
        print("Usage: python mufun_model_setup.py path/to/song.wav")
        sys.exit(1)

    audio = sys.argv[1]
    try:
        out = mufun_analyze_file(audio)
    except Exception as exc:
        print("[CDMF] MuFun analysis failed:", exc)
        sys.exit(1)

    print("[CDMF] MuFun analysis result:")
    print(out)
