# ACE-Step Music Creation Guide

> This guide contains professional music creation knowledge extracted from ACE-Step Tutorial. Use this as reference when creating music with ACE-Step.

---

## Input Control: What Do You Want?

This is the part where you communicate "creative intent" with the model—what kind of music you want to generate.

| Category | Parameter | Function |
|----------|-----------|----------|
| **Task Type** | `task_type` | Determines generation mode: text2music, cover, repaint, lego, extract, complete |
| **Text Input** | `caption` | Description of overall music elements: style, instruments, emotion, atmosphere, timbre, vocal gender, progression, etc. |
| | `lyrics` | Temporal element description: lyric content, music structure evolution, vocal changes, vocal/instrument performance style, start/end style, articulation, etc. (use `[Instrumental]` for instrumental music) |
| **Music Metadata** | `bpm` | Tempo (30–300) |
| | `keyscale` | Key (e.g., C Major, Am) |
| | `timesignature` | Time signature (4/4, 3/4, 6/8) |
| | `vocal_language` | Vocal language |
| | `duration` | Target duration (seconds) |
| **Audio Reference** | `reference_audio` | Global reference for timbre or style (for cover, style transfer) |
| | `src_audio` | Source audio for non-text2music tasks (text2music defaults to silence, no input needed) |
| | `audio_codes` | Semantic codes input to model in Cover mode (advanced: reuse codes for variants, convert songs to codes for extension, combine like DJ mixing) |
| **Interval Control** | `repainting_start/end` | Time interval for operations (repaint redraw area / lego new track area) |

---

## About Caption: The Most Important Input

**Caption is the most important factor affecting generated music.**

It supports multiple input formats: simple style words, comma-separated tags, complex natural language descriptions. We've trained to be compatible with various formats, ensuring text format doesn't significantly affect model performance.

### Common Dimensions for Caption Writing

| Dimension | Examples |
|-----------|----------|
| **Style/Genre** | pop, rock, jazz, electronic, hip-hop, R&B, folk, classical, lo-fi, synthwave |
| **Emotion/Atmosphere** | melancholic, uplifting, energetic, dreamy, dark, nostalgic, euphoric, intimate |
| **Instruments** | acoustic guitar, piano, synth pads, 808 drums, strings, brass, electric bass |
| **Timbre Texture** | warm, bright, crisp, muddy, airy, punchy, lush, raw, polished |
| **Era Reference** | 80s synth-pop, 90s grunge, 2010s EDM, vintage soul, modern trap |
| **Production Style** | lo-fi, high-fidelity, live recording, studio-polished, bedroom pop |
| **Vocal Characteristics** | female vocal, male vocal, breathy, powerful, falsetto, raspy, choir |
| **Speed/Rhythm** | slow tempo, mid-tempo, fast-paced, groovy, driving, laid-back |
| **Structure Hints** | building intro, catchy chorus, dramatic bridge, fade-out ending |

### Practical Principles for Caption Writing

1. **Specific beats vague** — "sad piano ballad with female breathy vocal" works better than "a sad song."

2. **Combine multiple dimensions** — Single-dimension descriptions give the model too much room to play; combining style+emotion+instruments+timbre can more precisely anchor your desired direction.

3. **Use references well** — "in the style of 80s synthwave" or "reminiscent of Bon Iver" can quickly convey complex aesthetic preferences.

4. **Texture words are useful** — Adjectives like warm, crisp, airy, punchy can influence mixing and timbre tendencies.

5. **Don't pursue perfect descriptions** — Caption is a starting point, not an endpoint. Write a general direction first, then iterate based on results.

6. **Description granularity determines freedom** — More omitted descriptions give the model more room to play, more random factor influence; more detailed descriptions constrain the model more. Decide specificity based on your needs—want surprises? Write less. Want control? Write more details.

7. **Avoid conflicting words** — Conflicting style combinations easily lead to degraded output. For example, wanting both "classical strings" and "hardcore metal" simultaneously—the model will try to fuse but usually not ideal.

 **Ways to resolve conflicts:**
 - **Repetition reinforcement** — Strengthen the elements you want more in mixed styles by repeating certain words
 - **Conflict to evolution** — Transform style conflicts into temporal style evolution. For example: "Start with soft strings, middle becomes noisy dynamic metal rock, end turns to hip-hop"—this gives the model clear guidance on how to handle different styles, rather than mixing them into a mess

---

## About Lyrics: The Temporal Script

If Caption describes the music's "overall portrait"—style, atmosphere, timbre—then **Lyrics is the music's "temporal script"**, controlling how music unfolds over time.

Lyrics is not just lyric content. It carries:
- The lyric text itself
- **Structure tags** ([Verse], [Chorus], [Bridge]...)
- **Vocal style hints** ([raspy vocal], [whispered]...)
- **Instrumental sections** ([guitar solo], [drum break]...)
- **Energy changes** ([building energy], [explosive drop]...)

### Common Structure Tags

| Category | Tag | Description |
|----------|-----|-------------|
| **Basic Structure** | `[Intro]` | Opening, establish atmosphere |
| | `[Verse]` / `[Verse 1]` | Verse, narrative progression |
| | `[Pre-Chorus]` | Pre-chorus, build energy |
| | `[Chorus]` | Chorus, emotional climax |
| | `[Bridge]` | Bridge, transition or elevation |
| | `[Outro]` | Ending, conclusion |
| **Dynamic Sections** | `[Build]` | Energy gradually rising |
| | `[Drop]` | Electronic music energy release |
| | `[Breakdown]` | Reduced instrumentation, space |
| **Instrumental Sections** | `[Instrumental]` | Pure instrumental, no vocals |
| | `[Guitar Solo]` | Guitar solo |
| | `[Piano Interlude]` | Piano interlude |
| **Special Tags** | `[Fade Out]` | Fade out ending |
| | `[Silence]` | Silence |

### Combining Tags: Use Moderately

Structure tags can be combined with `-` for finer control:

```
[Chorus - anthemic]
This is the chorus lyrics
Dreams are burning

[Bridge - whispered]
Whisper those words softly
```

⚠️ **Note: Don't stack too many tags.**

```
❌ Not recommended:
[Chorus - anthemic - stacked harmonies - high energy - powerful - epic]

✅ Recommended:
[Chorus - anthemic]
```

**Principle**: Keep structure tags concise; put complex style descriptions in Caption.

### ⚠️ Key: Maintain Consistency Between Caption and Lyrics

**Models are not good at resolving conflicts.** If descriptions in Caption and Lyrics contradict, the model gets confused and output quality decreases.

**Checklist:**
- Instruments in Caption ↔ Instrumental section tags in Lyrics
- Emotion in Caption ↔ Energy tags in Lyrics
- Vocal description in Caption ↔ Vocal control tags in Lyrics

Think of Caption as "overall setting" and Lyrics as "shot script"—they should tell the same story.

### Vocal Control Tags

| Tag | Effect |
|-----|--------|
| `[raspy vocal]` | Raspy, textured vocals |
| `[whispered]` | Whispered |
| `[falsetto]` | Falsetto |
| `[powerful belting]` | Powerful, high-pitched singing |
| `[spoken word]` | Rap/recitation |
| `[harmonies]` | Layered harmonies |
| `[call and response]` | Call and response |
| `[ad-lib]` | Improvised embellishments |

### Energy and Emotion Tags

| Tag | Effect |
|-----|--------|
| `[high energy]` | High energy, passionate |
| `[low energy]` | Low energy, restrained |
| `[building energy]` | Increasing energy |
| `[explosive]` | Explosive energy |
| `[melancholic]` | Melancholic |
| `[euphoric]` | Euphoric |
| `[dreamy]` | Dreamy |
| `[aggressive]` | Aggressive |

### Lyric Text Writing Tips

**1. Control Syllable Count**

**6-10 syllables per line** usually works best. The model aligns syllables to beats—if one line has 6 syllables and the next has 14, rhythm becomes strange.

**Tip**: Keep similar syllable counts for lines in the same position (e.g., first line of each verse) (±1-2 deviation).

**2. Use Case to Control Intensity**

Uppercase indicates stronger vocal intensity:

```
[Verse]
walking through the empty streets (normal intensity)

[Chorus]
WE ARE THE CHAMPIONS! (high intensity, shouting)
```

**3. Use Parentheses for Background Vocals**

```
[Chorus]
We rise together (together)
Into the light (into the light)
```

Content in parentheses is processed as background vocals or harmonies.

**4. Extend Vowels**

You can extend sounds by repeating vowels:

```
Feeeling so aliiive
```

But use cautiously—effects are unstable, sometimes ignored or mispronounced.

**5. Clear Section Separation**

Separate each section with blank lines:

```
[Verse 1]
First verse lyrics
Continue first verse

[Chorus]
Chorus lyrics
Chorus continues
```

### Avoiding "AI-flavored" Lyrics

These characteristics make lyrics seem mechanical and lack human touch:

| Red Flag 🚩 | Description |
|-------------|-------------|
| **Adjective stacking** | "neon skies, electric hearts, endless dreams"—filling a section with vague imagery |
| **Rhyme chaos** | Inconsistent rhyme patterns, or forced rhymes causing semantic breaks |
| **Blurred section boundaries** | Lyric content crosses structure tags, Verse content "flows" into Chorus |
| **No breathing room** | Each line too long, can't sing in one breath |
| **Mixed metaphors** | First verse uses water imagery, second suddenly becomes fire, third is flying—listeners can't anchor |

**Metaphor discipline**: Stick to one core metaphor per song, exploring its multiple aspects.

---

## About Music Metadata: Optional Fine Control

**Most of the time, you don't need to manually set metadata.**

When you enable `thinking` mode (or enable `use_cot_metas`), LM automatically infers appropriate BPM, key, time signature, etc. based on your Caption and Lyrics. This is usually good enough.

But if you have clear ideas, you can also manually control them:

| Parameter | Control Range | Description |
|-----------|--------------|-------------|
| `bpm` | 30–300 | Tempo. Common distribution: slow songs 60–80, mid-tempo 90–120, fast songs 130–180 |
| `keyscale` | Key | e.g., `C Major`, `Am`, `F# Minor`. Affects overall pitch and emotional color |
| `timesignature` | Time signature | `4/4` (most common), `3/4` (waltz), `6/8` (swing feel) |
| `vocal_language` | Language | Vocal language. LM usually auto-detects from lyrics |
| `duration` | Seconds | Target duration. Actual generation may vary slightly |

### Understanding Control Boundaries

These parameters are **guidance** rather than **precise commands**:

- **BPM**: Common range (60–180) works well; extreme values (like 30 or 280) have less training data, may be unstable
- **Key**: Common keys (C, G, D, Am, Em) are stable; rare keys may be ignored or shifted
- **Time signature**: `4/4` is most reliable; `3/4`, `6/8` usually OK; complex signatures (like `5/4`, `7/8`) are advanced, effects vary by style
- **Duration**: Short songs (30–60s) and medium length (2–4min) are stable; very long generation may have repetition or structure issues

### When Do You Need Manual Settings?

| Scenario | Suggestion |
|----------|------------|
| Daily generation | Don't worry, let LM auto-infer |
| Clear tempo requirement | Manually set `bpm` |
| Specific style (e.g., waltz) | Manually set `timesignature=3/4` |
| Need to match other material | Manually set `bpm` and `duration` |
| Pursue specific key color | Manually set `keyscale` |

**Tip**: If you manually set metadata but generation results clearly don't match—check if there's conflict with Caption/Lyrics. For example, Caption says "slow ballad" but `bpm=160`, the model gets confused.

**Recommended Practice**: Don't write tempo, BPM, key, and other metadata information in Caption. These should be set through dedicated metadata parameters (`bpm`, `keyscale`, `timesignature`, etc.), not described in Caption. Caption should focus on style, emotion, instruments, timbre, and other musical characteristics, while metadata information is handled by corresponding parameters.

---

## Duration Calculation Guidelines

When creating music, you MUST calculate appropriate duration based on lyrics content and song structure:

### Estimation Method

- **Per line of lyrics**: 3-5 seconds
- **Intro/Outro**: 5-10 seconds each
- **Instrumental sections**: 5-15 seconds each
- **Typical song structures**:
 - 2 verses + 2 choruses: 120-150 seconds minimum
 - 2 verses + 2 choruses + bridge: 180-240 seconds minimum
 - Full song with intro/outro: 210-270 seconds (3.5-4.5 minutes)

### Common Pitfalls

❌ **DON'T**: Set duration too short for the lyrics amount
- Example: 10 lines of lyrics with 120 seconds → rushed, compressed

✅ **DO**: Calculate realistic duration
- Example: 10 lines of lyrics → ~40 seconds of vocals + 20 seconds intro/outro = 60 seconds minimum

### BPM and Duration Relationship

The BPM affects how quickly lyrics are sung:
- **Slower BPM (60-80)**: Need MORE duration for same lyrics
- **Medium BPM (100-130)**: Standard duration
- **Faster BPM (150-180)**: Can fit more lyrics in less time, but still need breathing room

**Rule of thumb**: When in doubt, estimate longer rather than shorter. A song that's too short will feel rushed and incomplete.

---

## Complete Example

Assuming Caption is: `female vocal, piano ballad, emotional, intimate atmosphere, strings, building to powerful chorus`

```
[Intro - piano]

[Verse 1]
月光洒在窗台上
我听见你的呼吸
城市在远处沉睡
只有我们还醒着

[Pre-Chorus]
这一刻如此安静
却藏着汹涌的心

[Chorus - powerful]
让我们燃烧吧
像夜空中的烟火
短暂却绚烂
这就是我们的时刻

[Verse 2]
时间在指尖流过
我们抓不住什么
但至少此刻拥有
彼此眼中的火焰

[Bridge - whispered]
如果明天一切消散
至少我们曾经闪耀

[Final Chorus]
让我们燃烧吧
像夜空中的烟火
短暂却绚烂
THIS IS OUR MOMENT!

[Outro - fade out]
```

Note: In this example, Lyrics tags (piano, powerful, whispered) are consistent with Caption descriptions (piano ballad, building to powerful chorus, intimate), with no conflicts.

---
