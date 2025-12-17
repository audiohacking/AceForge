# Candy Dungeon Music Forge (CDMF)

Candy Dungeon Music Forge (CDMF) is a **local-first AI music workstation for Windows**. It runs on your PC, uses your GPU, and keeps your prompts and audio on your hardware. CDMF is powered by **ACE-Step** (text → music diffusion) and includes a custom UI for generating tracks, managing a library, and training **LoRAs**.

Status: **v0.1**

## What you can do

- Generate music from a **prompt** (optionally with **lyrics**)
- Use a built-in **Music Player + library view** (sort, favorite, categorize)
- Save and reuse **presets**
- (Optional) **Stem separation** to rebalance vocals vs instrumentals
- Train **ACE-Step LoRAs** from your own datasets
- Dataset helpers:
  - Mass-create `_prompt.txt` / `_lyrics.txt` files
  - (Optional) Auto-tag datasets using **MuFun-ACEStep** (experimental)

## System requirements

Minimum:
- Windows 10/11 (64-bit)
- NVIDIA GPU (RTX strongly recommended)
- ~10–12 GB VRAM (more = more headroom)
- SSD with tens of GB free (models + audio + datasets)

Comfortable:
- RTX GPU with 12–24 GB VRAM
- 32 GB RAM
- Fast NVMe SSD
- Comfort reading console logs when something goes wrong

## Install and run (recommended)

1. Download the latest release (installer)
2. Run `CandyDungeonMusicForge-Setup.exe`
3. Launch **Candy Dungeon Music Forge** from the Start Menu

Default install location:
- `%LOCALAPPDATA%\CandyDungeonMusicForge`

### First launch notes

On first run, CDMF does real setup work:
- Creates a Python virtual environment (e.g. `venv_ace`)
- Installs packages from `requirements_ace.txt`
- Downloads ACE-Step and related models as needed
- Installs helpers like `audio-separator`

A console window (“server console”) appears and **must stay open** while CDMF runs. CDMF will open a loading page in your browser and then load the full UI when ready.

## Using CDMF (high-level workflow)

1. Launch CDMF and wait for the UI
2. Go to **Generate** → create tracks from prompt (and lyrics if desired)
3. Browse/manage tracks in **Music Player**
4. (Optional) Use stem controls to adjust vocal/instrumental balance
5. (Optional) Build a dataset and train a LoRA in **Training**

## Generation basics

- **Prompt**: your main ACE-Step tags / description (genre, instruments, mood, context)
- **Instrumental** mode:
  - Lyrics are not used
  - CDMF uses the `[inst]` token so ACE-Step focuses on backing tracks
- **Vocal** mode:
  - Provide lyrics using markers like `[verse]`, `[chorus]`, `[solo]`, etc.
- **Presets** let you save/load a whole “knob bundle” (text + sliders)

## Stem separation (vocals vs instrumentals)

CDMF can run `audio-separator` as a post-process step so you can rebalance:
- Vocals level (dB)
- Instrumental level (dB)

First use requires downloading a **large** stem model and adds a heavy processing step. For fast iteration: generate with both gains at `0 dB`, then only use stems once you like a track.

## LoRA training

Switch to the **Training** tab to configure and start LoRA runs.

### Dataset structure

Datasets must live under:

`<CDMF root>\training_datasets`

For each audio file (`foo.mp3` or `foo.wav`), provide:
- `foo_prompt.txt` — ACE-Step prompt/tags for that track
- `foo_lyrics.txt` — lyrics, or `[inst]` for instrumentals

CDMF includes tools to bulk-create these files (and optionally auto-generate them with MuFun-ACEStep).

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

- **First launch takes forever**: check console for pip/model download errors; verify disk space and network
- **No .wav files found**: generate a track; confirm Output Directory matches the Music Player folder
- **CUDA / VRAM OOM**:
  - Reduce target length during generation
  - Reduce max clip seconds during training
  - Lower batch/grad accumulation if you changed them

## Contributing

Issues and PRs welcome. If you’re changing anything related to training, model setup, or packaging, please include:
- what GPU/driver you tested on
- exact steps to reproduce any bug you fixed

(Consider adding `CONTRIBUTING.md` once you have preferred norms.)

## License

This project’s **source code** is licensed under the **Apache License 2.0**. See `LICENSE`.

Note: Model weights and third-party tools used by CDMF (ACE-Step, PyTorch, audio-separator, MuFun-ACEStep, any LLM backend, etc.) are covered by their own licenses/terms.

## Trademarks

“Candy Dungeon”, “Candy Dungeon Music Forge”, and associated logos/branding are **trademarks of the project owner** and are **not** granted under the Apache-2.0 license.

See `TRADEMARKS.md` for permitted use (e.g., descriptive references are fine; distributing a fork under the same name/logo is not).

## Support

If you find CDMF useful and want to support development, you can:
- email support@candydungeon.com for more info
- Contribute to the creator's Ko-Fi and buy him a coffee/cigar if you want: https://ko-fi.com/davidhagar
