<img height="250" alt="image" src="https://github.com/user-attachments/assets/000f485b-3bb1-48c4-8031-cd941eec6bf7" />

# AceForge

AceForge is a **local-first AI music workstation for macOS Silicon** powered by **[ACE-Step](https://github.com/ace-step/ACE-Step)**<br>

> Status: **ALPHA**

## Features

- 100% Local _(only needs to download models once)_
- Music Generation with **ACE-Step** prompts
  - Use **Stem separation** to rebalance vocals vs instrumentals
  - Use existing **Audio** as reference _(optional)_ 
  - Train **ACE-Step LoRAs** from your own datasets
    - Mass-create `_prompt.txt` / `_lyrics.txt` files
    - Auto-tag datasets using **MuFun-ACEStep** _(experimental)_
- Voice Cloning TTS using **XTTS v2**
- Embedded **Music Player** to explore generation catalog
- Manage and reuse **prompt presets**

## System requirements

### Minimum

- macOS 12.0 (Monterey) or later
- Apple Silicon (M1/M2/M3) or Intel Mac with AMD GPU
- 16 GB unified memory (for Apple Silicon) or 16 GB RAM
- ~10–12 GB VRAM/unified memory (more = more headroom)
- SSD with tens of GB free (models + audio + datasets)

### Recommended

- Apple Silicon M1 Pro/Max/Ultra, M2 Pro/Max/Ultra, or M3 Pro/Max
- 32 GB+ unified memory
- Fast SSD
- Comfort reading terminal logs when something goes wrong

## Install and run

### Option 1: Download Pre-built Release for OSX

Pre-built macOS application bundles are available from the [Releases page](https://github.com/audiohacking/AceForge/releases).

**Installation:**
1. Download `AceForge-macOS.dmg` from the latest release
2. Open the DMG file
3. Drag `AceForge.app` to your Applications folder (or any location on your Mac)

**To Launch:**

- Double-click `AceForge.app`

> **Note:** On first launch, macOS may show a security warning because the app is not notarized by Apple. Go to `System Settings > Privacy & Security` and click `Open Anyway`. This is normal for apps downloaded from the internet that are not distributed through the Mac App Store.

> **Note:** If macOS prevents the app from opening with a "damaged" error execute the following command:  
```sudo xattr -cr /Applications/AceForge.app```

> **Note:** The app bundle does NOT include the large model files. On first run, it will download the ACE-Step models (several GB) automatically. You can monitor the download progress in the Terminal window or in the Server Console panel in the web interface.

## Using AceForge (high-level workflow)

1. Launch AceForge and wait for the UI
2. Go to **Generate** → create tracks from prompt (and lyrics if desired)
3. Browse/manage tracks in **Music Player**
4. (Optional) Use stem controls to adjust vocal/instrumental balance
5. (Optional) **Voice Clone**: TTS voice cloning using reference clips
6. (Optional) Build a dataset and train a LoRA in **Training**



## Generation basics

- **Prompt**: your main ACE-Step tags / description (genre, instruments, mood, context)
- **Instrumental** mode:
  - Lyrics are not used
  - AceForge uses the `[inst]` token so ACE-Step focuses on backing tracks
- **Vocal** mode:
  - Provide lyrics using markers like `[verse]`, `[chorus]`, `[solo]`, etc.
- **Presets** let you save/load a whole “knob bundle” (text + sliders)

## Stem separation (vocals vs instrumentals)

AceForge can run `audio-separator` as a post-process step so you can rebalance:
- Vocals level (dB)
- Instrumental level (dB)

First use requires downloading a **large** stem model and adds a heavy processing step. For fast iteration: generate with both gains at `0 dB`, then only use stems once you like a track.

## Voice cloning (XTTS v2)

The **Voice Clone** tab uses Coqui TTS (XTTS v2) to synthesize speech in a cloned voice. Upload a short reference (MP3, WAV, M4A, or FLAC), enter the text, and generate. Output is saved as MP3 256k and appears in the Music Player. On first use, the XTTS model (~1.9 GB) is downloaded automatically. **ffmpeg** must be installed (e.g. `brew install ffmpeg`) for non-WAV references.

## LoRA training

Switch to the **Training** tab to configure and start LoRA runs.

### Dataset structure

Datasets must live under:

`<AceForge root>\training_datasets`

For each audio file (`foo.mp3` or `foo.wav`), provide:
- `foo_prompt.txt` — ACE-Step prompt/tags for that track
- `foo_lyrics.txt` — lyrics, or `[inst]` for instrumentals

AceForge includes tools to bulk-create these files (and optionally auto-generate them with MuFun-ACEStep).

### Training parameters (examples)

- Adapter name (experiment name)
- LoRA config preset (JSON from `training_config`)
- Epochs / max steps
- Learning rate (commonly `1e-4` to `1e-5`)
- Max clip seconds (lower can reduce VRAM and speed up training)
- Optional SSL loss weighting (set to 0 for some instrumental datasets)
- Checkpoint/save cadence

## Experimental: MuFun-ACEStep dataset analyzer

MuFun-ACEStep can auto-generate `_prompt.txt` and `_lyrics.txt` files from audio. It’s powerful but:
- The model is large (tens of GB)
- Outputs aren’t perfect—skim and correct weird tags/lyrics before training

## Troubleshooting

### Common Issues

- **First launch takes forever**: Check terminal for pip/model download errors; verify disk space and network
- **No tracks found**: Generate a track or run Voice Clone; confirm Output Directory matches the Music Player folder
- **Memory issues**: 
  - Reduce target length during generation
  - Reduce max clip seconds during training
  - Lower batch/grad accumulation if you changed them

## Performance Tips for Apple Silicon

- **Unified memory management**: Apple Silicon Macs with unified memory can efficiently share memory between CPU and GPU
- **Batch sizes**: Start with smaller batch sizes and gradually increase to find optimal performance
- **Model precision**: The pipeline automatically selects appropriate precision for MPS (float32 instead of bfloat16)
- **Generation length**: Longer generation times may require more memory; start with shorter durations and scale up

## Building Releases

Pre-built macOS application bundles are automatically created via GitHub Actions. To build locally use the provided scripts.


**Code Signing:** The build includes automated code signing to prevent macOS security warnings that would otherwise require running `sudo xattr -cr /Applications/AceForge.app`. By default, the script uses ad-hoc signing (no Apple Developer certificate required). For distribution, you can provide a Developer ID certificate. See `build/macos/README.md` for detailed documentation on code signing options.

The build process creates a self-contained macOS application that includes:
- Python runtime and all dependencies
- Static files (HTML, CSS, JS)
- Configuration files
- Documentation

**Note:** The app bundle does NOT include the large AI model files (~several GB). These are downloaded automatically on first run.

## Contributing

Issues and PRs welcome. If you’re changing anything related to training, model setup, or packaging, please include:
- what GPU/driver you tested on
- exact steps to reproduce any bug you fixed

(Consider adding `CONTRIBUTING.md` once you have preferred norms.)

## License

This project’s **source code** is licensed under the **Apache License 2.0**. See `LICENSE`.

