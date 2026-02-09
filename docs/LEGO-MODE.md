# Lego Mode (ACE-Step 1.5)

Lego mode adds a new instrument track on top of backing audio (e.g. add guitar to a beat). It requires the **Base** DiT model.

## Known limitations and workarounds

We align with findings from [ACE-Step-1.5 issue #117](https://github.com/ace-step/ACE-Step-1.5/issues/117) (BPM/timing drift and MPS crashes):

1. **Timing drift**  
   Generated tracks are not strictly BPM-locked to the source; onsets can drift (20–80 ms). Workarounds that help:
   - Match **duration** to the source (e.g. 4 bars at 135 BPM → duration ≈ 7.1 s: `4 * (60/135) * 4` for 4/4).
   - Use **shorter segments** (e.g. 4 bars) then duplicate if needed; less time for drift.
   - We use **shift=3.0** for lego (recommended in the issue for better timing vs shift=1.0).

2. **Apple Silicon (MPS)**  
   On Mac:
   - **`ref_audio_strength` (backing influence) &lt; 1.0** can crash with a batch dimension mismatch at the cover→text2music transition. We **default to 1.0** for lego so Apple Silicon users don’t hit this. Lower values (0.2–0.5) can improve “new instrument” feel on non-MPS.
   - **Thinking (LM)** is **disabled for lego** so the backing drives context; with thinking on, LLM-generated codes can override the source and hurt timing/context.

3. **Caption and BPM**  
   Include style, key, and BPM in the caption (e.g. “electric guitar, C major, 135 BPM, 4 bars”) and set **BPM** in the API so metadata matches the backing.

## AceForge defaults (lego)

| Parameter              | Default | Note |
|------------------------|--------|------|
| `ref_audio_strength`   | 1.0    | Avoids MPS crash; UI “Backing influence” |
| `thinking`             | false  | Forced off for lego so src_audio drives context |
| `shift`                | 3.0    | Better timing than 1.0/6.0 for lego |
| `use_cot_caption`      | false  | Keep instruction verbatim (“Generate the X track…”) |

Users can still lower backing influence on non-Apple Silicon if they want more “new instrument” and accept the risk of drift or (on MPS) crash.
