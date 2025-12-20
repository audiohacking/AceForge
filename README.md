<img width="235" height="250" alt="image" src="https://github.com/user-attachments/assets/d19e1f9c-511e-424e-97ed-20b2a7035b75" />

# AceForge

AceForge is a **local-first AI music workstation for macOS**. It runs on your Mac, uses Apple Metal (MPS) GPU acceleration, and keeps your prompts and audio on your hardware. AceForge is powered by **ACE-Step** (text → music diffusion) and includes a custom UI for generating tracks, managing a library, and training **LoRAs**.

This fork is optimized for macOS with Apple Metal support, designed for both Apple Silicon (M1/M2/M3) and Intel Macs.

Status: **v0.1-macos**

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

### Minimum

- macOS 12.0 (Monterey) or later
- Apple Silicon (M1/M2/M3) or Intel Mac with AMD GPU
- 16 GB unified memory (for Apple Silicon) or 16 GB RAM
- ~10–12 GB VRAM/unified memory (more = more headroom)
- SSD with tens of GB free (models + audio + datasets)
- Python 3.11 or later

### Recommended

- Apple Silicon M1 Pro/Max/Ultra, M2 Pro/Max/Ultra, or M3 Pro/Max
- 32 GB+ unified memory
- Fast SSD
- Comfort reading terminal logs when something goes wrong

**Note:** Apple Metal (MPS) support enables GPU acceleration on both Apple Silicon and Intel Macs with compatible AMD GPUs. Performance is optimized for Apple Silicon with unified memory architecture.

## Install and run

### Option 1: Download Pre-built Release (Easiest)

Pre-built macOS application bundles are available from the [Releases page](https://github.com/audiohacking/AceForge/releases).

**Installation:**
1. Download `AceForge-macOS.dmg` from the latest release
2. Open the DMG file
3. Copy both `AceForge.app` and `AceForge.command` to a location on your Mac

**To Launch:**

**Method A (Recommended): With Terminal Window**
- Double-click `AceForge.command` 
- A Terminal window will open showing server logs
- Your browser will open automatically when ready
- Keep the Terminal window open while using AceForge
- To stop: Press Ctrl+C in Terminal or use the "Exit" button in browser

**Method B: Background Mode**
- Right-click `AceForge.app` and select "Open" (first time only, to bypass Gatekeeper)
- The app runs in the background
- Open browser to `http://127.0.0.1:5056/`
- To stop: Use the "Exit" button in the web interface

**Note:** The app bundle does not include the large model files. On first run, it will download the ACE-Step models (several GB) automatically. You can monitor the download progress in the Terminal window (Method A) or in the Console Panel in the web interface.

### Option 2: Run from Source

#### Prerequisites

Ensure you have Python 3.11 or later installed:
```bash
# Check Python version
python3 --version

# If not installed, install via Homebrew
brew install python@3.10
```

#### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/audiohacking/AceForge-Fork.git
   cd AceForge-Fork
   ```

2. Make the launcher script executable:
   ```bash
   chmod +x CDMF.sh
   ```

3. Run the launcher:
   ```bash
   ./CDMF.sh
   ```

4. On first run, the script will:
   - Create a Python virtual environment (`venv_ace`)
   - Install packages from `requirements_ace_macos.txt`
   - Download ACE-Step and related models as needed
   - Install helpers like `audio-separator`
   - Open the UI in your default browser

The terminal window must remain open while AceForge is running. Press Ctrl+C to stop the server.

On first run, AceForge does real setup work:
- Creates a Python virtual environment (e.g. `venv_ace`)
- Installs packages from `requirements_ace.txt`
- Downloads ACE-Step and related models as needed
- Installs helpers like `audio-separator`

A console window (“server console”) appears and **must stay open** while AceForge runs. AceForge will open a loading page in your browser and then load the full UI when ready.

## Using AceForge (high-level workflow)

1. Launch AceForge and wait for the UI
2. Go to **Generate** → create tracks from prompt (and lyrics if desired)
3. Browse/manage tracks in **Music Player**
4. (Optional) Use stem controls to adjust vocal/instrumental balance
5. (Optional) Build a dataset and train a LoRA in **Training**
6. **To Exit**: Click the "Exit" button in the top-right corner or press Ctrl+C in the terminal

### New UI Features

**Server Console Panel** (v0.1+)
- Click "▼ Server Console" at the top of the page to expand/collapse
- View real-time server logs directly in the browser
- Useful for troubleshooting errors and monitoring model downloads
- Logs are displayed in a terminal-style interface with auto-scrolling

**Exit Button** (v0.1+)
- Located in the top-right corner of the UI
- Gracefully shuts down the AceForge server
- Closes all services and terminates the backend
- Safe to use instead of force-closing the terminal window

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
- **No .wav files found**: Generate a track; confirm Output Directory matches the Music Player folder
- **Memory issues**: 
  - Reduce target length during generation
  - Reduce max clip seconds during training
  - Lower batch/grad accumulation if you changed them

### macOS-Specific

- **MPS (Metal) backend errors**: 
  - Ensure you're running macOS 12.0+ for MPS support
  - Some operations may fall back to CPU if not yet supported on MPS
  - Try setting `ACE_PIPELINE_DTYPE=float32` environment variable if you encounter precision issues:
    ```bash
    export ACE_PIPELINE_DTYPE=float32
    ./CDMF.sh
    ```

- **Python version issues**:
  ```bash
  # Ensure you have Python 3.11 or later
  python3 --version
  
  # Install via Homebrew if needed
  brew install python@3.11
  ```

- **Permission denied when running CDMF.sh**:
  ```bash
  chmod +x CDMF.sh
  ```

- **Browser doesn't open automatically**: 
  - Manually navigate to `http://127.0.0.1:5056/` in your browser
  - Check if the terminal shows any error messages

- **Virtual environment issues**:
  ```bash
  # Remove existing venv and recreate
  rm -rf venv_ace
  ./CDMF.sh
  ```

## Performance Tips for Apple Silicon

- **Unified memory management**: Apple Silicon Macs with unified memory can efficiently share memory between CPU and GPU
- **Batch sizes**: Start with smaller batch sizes and gradually increase to find optimal performance
- **Model precision**: The pipeline automatically selects appropriate precision for MPS (float32 instead of bfloat16)
- **Generation length**: Longer generation times may require more memory; start with shorter durations and scale up

## About This Fork

This is a **macOS-optimized** version specifically designed for Apple Metal (MPS) GPU acceleration. This fork focuses exclusively on macOS support and does not maintain Windows compatibility.

### Differences from Original

- **Apple Metal (MPS) GPU support**: Optimized for Apple Silicon and Intel Macs with AMD GPUs
- **Device-agnostic code**: Automatic device selection (MPS → CPU fallback)
- **macOS launcher**: Native bash script (`CDMF.sh`) instead of Windows batch file
- **Unified memory optimizations**: Leverages Apple Silicon's unified memory architecture
- **macOS-specific dependencies**: Windows-specific packages removed

### Porting Updates from Upstream

To port updates from the original Windows version:

1. The original Windows requirements are preserved in `requirements_ace_windows_reference.txt`
2. The original Windows launcher is in `AceForge.bat`
3. When merging updates, focus on:
   - Core model and pipeline logic
   - UI and generation features
   - Dataset and training functionality
4. Adapt any Windows-specific or CUDA-only code to be device-agnostic
5. Test thoroughly with MPS backend

Key files for cross-platform compatibility:
- `cdmf_pipeline_ace_step.py` - Device selection and memory management
- `cdmf_trainer.py` - Training with device-agnostic autocast
- `music_forge_ui.py` - Browser opening logic

## Building Releases

Pre-built macOS application bundles are automatically created via GitHub Actions. To build locally or create a new release:

### Automated Build (GitHub Actions)

1. Create a new release on GitHub
2. The build workflow will automatically trigger
3. DMG and ZIP files will be attached to the release

Or manually trigger the build:
```bash
# Via GitHub Actions UI:
# Go to Actions > Build macOS Release > Run workflow
```

### Manual Build (Local)

Requirements:
- macOS system with Python 3.11+
- All dependencies installed (`requirements_ace_macos.txt`)

Steps:
```bash
# Install dependencies
pip install -r requirements_ace_macos.txt
pip install "audio-separator==0.40.0" --no-deps
pip install "py3langid==0.3.0" --no-deps
pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps

# Build with PyInstaller
pyinstaller AceForge.spec

# The .app bundle will be in dist/AceForge.app

# Optional: Create DMG
hdiutil create -volname "AceForge" \
  -srcfolder dist/AceForge.app \
  -ov -format UDZO \
  AceForge-macOS.dmg
```

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
## Trademarks

This project was originally forked from a project with trademarked branding ("Candy Dungeon" and "Candy Dungeon Music Forge"). All such trademarked names and branding have been removed from this fork to comply with trademark regulations. This project is now known as "AceForge".

## Support

If you find AceForge useful and want to support development, you can open issues or contribute via pull requests on GitHub.
