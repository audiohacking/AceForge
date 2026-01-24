# Welcome to AceForge

AceForge is a **local-first AI music workstation for macOS Silicon** powered by **[ACE-Step](https://github.com/ace-step/ACE-Step)**. Generate unlimited custom music with simple prompts, train custom LoRAs, and manage your music library—all running locally on your Mac.

> **Status:** ALPHA

## Quick Links

- [Installation](#installation)
- [Launching AceForge](#launching-aceforge)
- [Basic Workflows](#basic-workflows)
- [Features](#features)
- [System Requirements](#system-requirements)
- [Troubleshooting](#troubleshooting)

---

## Features

- **100% Local** - Only needs to download models once, then everything runs offline
- **Music Generation** with ACE-Step prompts
  - Stem separation to rebalance vocals vs instrumentals
  - Use existing audio as reference (optional)
  - Train custom ACE-Step LoRAs from your own datasets
    - Mass-create `_prompt.txt` / `_lyrics.txt` files
    - Auto-tag datasets using MuFun-ACEStep (experimental)
- **Voice Cloning TTS** using XTTS v2
- **Embedded Music Player** to explore your generation catalog
- **Preset Management** - Save and reuse prompt configurations

---

## System Requirements

### Minimum

- macOS 12.0 (Monterey) or later
- Apple Silicon (M1/M2/M3) or Intel Mac with AMD GPU
- 16 GB unified memory (for Apple Silicon) or 16 GB RAM
- ~10–12 GB VRAM/unified memory (more = more headroom)
- SSD with tens of GB free (for models + audio + datasets)

### Recommended

- Apple Silicon M1 Pro/Max/Ultra, M2 Pro/Max/Ultra, or M3 Pro/Max
- 32 GB+ unified memory
- Fast SSD
- Comfort reading terminal logs when troubleshooting

---

## Installation

### Option 1: Download Pre-built Release (Recommended)

Pre-built macOS application bundles are available from the [Releases page](https://github.com/audiohacking/AceForge/releases).

**Steps:**

1. Download `AceForge-macOS.dmg` from the latest release
2. Open the DMG file
3. Drag `AceForge.app` to your Applications folder (or any location on your Mac)

**Important Notes:**

- **Security Warning:** On first launch, macOS may show a security warning because the app is not notarized by Apple. Go to `System Settings > Privacy & Security` and click `Open Anyway`. This is normal for apps downloaded from the internet that are not distributed through the Mac App Store.

- **"Damaged" Error:** If macOS prevents the app from opening with a "damaged" error, execute the following command in Terminal:
  ```bash
  sudo xattr -cr /Applications/AceForge.app
  ```

- **Model Downloads:** The app bundle does NOT include the large model files. On first run, it will download the ACE-Step models (several GB) automatically. You can monitor the download progress in the Terminal window or in the Server Console panel in the web interface.

### Option 2: Run from Source

1. **Ensure Python 3.10+ is installed:**
   ```bash
   # Check Python version
   python3 --version
   
   # If not installed, install via Homebrew
   brew install python@3.10
   ```

2. **Clone the repository:**
   ```bash
   git clone https://github.com/audiohacking/AceForge.git
   cd AceForge
   ```

3. **Make the launcher script executable:**
   ```bash
   chmod +x CDMF.sh
   ```

4. **Run the launcher:**
   ```bash
   ./CDMF.sh
   ```

---

## Launching AceForge

### First Launch

1. **Launch the app:**
   - From pre-built: Double-click `AceForge.app`
   - From source: Run `./CDMF.sh` in Terminal

2. **Terminal window appears:**
   - A terminal window titled "AceForge – Server Console" will open
   - **Keep this window open** while AceForge is running
   - This shows server logs and status messages

3. **Browser opens automatically:**
   - AceForge opens a loading page in your default browser
   - The page shows "Starting AceForge..." while the backend initializes

4. **First-time setup (may take several minutes):**
   - Creates `venv_ace` virtual environment
   - Installs packages from `requirements_ace_macos.txt`
   - Installs ACE-Step with PyTorch (including MPS support for Apple Silicon)
   - Sets up audio-separator and other tools

5. **Ready to use:**
   - Once setup completes, your browser displays the full AceForge UI
   - You can now start generating music!

**Important:** Don't close the terminal window during first-time setup. If you see Python or pip errors, read the last messages carefully. Many issues (disk space, network connectivity) will show up here.

### Subsequent Launches

On later launches, AceForge will:
- Reuse the existing `venv_ace` virtual environment
- Skip package installations if everything is already present
- Start much faster (typically under a minute)
- Only download new models when you use a feature for the first time (e.g., MuFun)

---

## Basic Workflows

### 1. Generate Your First Track

**Simple Generation:**

1. Navigate to the **Generate** tab (default view)
2. Enter a prompt in the **Genre / Style Prompt** field:
   ```
   Upbeat electronic dance music, synth leads, driving bass, energetic
   ```
3. Check **Instrumental** if you want instrumental music (no vocals)
4. Click **Generate** and wait for the track to complete
5. The track appears in the **Music Player** above the Generate section

**With Lyrics:**

1. Uncheck **Instrumental** to reveal the Lyrics field
2. Enter your prompt and lyrics using markers:
   ```
   Lyrics:
   [verse]
   Dancing through the night
   Under neon lights
   [chorus]
   We're alive, we're free
   This is where we're meant to be
   ```
3. Click **Generate**

**Using Presets:**

- Choose from **Instrumental** or **Vocal** preset buttons below the prompt field
- Each preset configures optimal settings for different music styles
- Click **Random** to explore curated preset variations

### 2. Manage Your Music Library

The **Music Player** card at the top shows all your generated tracks:

- **Play tracks:** Click on any track name to play
- **Favorite tracks:** Click the ★ icon to mark favorites
- **Filter by category:** Use the colored category chips above the track list
- **Sort tracks:** Click column headers (Name, Length, Category, Created) to sort
- **Delete tracks:** Click the trash icon to remove tracks from disk
- **Player controls:** Use Rewind, Play, Stop, Loop, and Mute buttons
- **Adjust volume:** Use the volume slider for playback level

### 3. Adjust Vocal and Instrumental Balance

**Post-generation stem separation:**

1. Generate a track you like
2. In the **Core** section of Generate, find:
   - **Vocals level (dB)** slider
   - **Instrumental level (dB)** slider
3. Adjust sliders (0 dB = original mix, negative = quieter, positive = louder)
4. Regenerate to create a new version with adjusted balance

**Note:** First use downloads a large stem separation model and adds processing time. For fast iteration, leave both at 0 dB initially.

### 4. Save and Load Presets

**Save your settings:**

1. Configure your desired prompt, lyrics, and generation parameters
2. Scroll to **Saved presets** section at the bottom
3. Click **Save** and enter a preset name
4. Your preset is now available in the **My presets** dropdown

**Load a preset:**

1. Select a preset from the **My presets** dropdown
2. Click **Load**
3. All fields update to the saved values
4. Click **Generate** to create a track with these settings

### 5. Train a Custom LoRA

**Prepare your dataset:**

1. Create a folder under `<AceForge root>/training_datasets/`
   ```bash
   mkdir training_datasets/my_lofi_style
   ```

2. Add your audio files (`.mp3` or `.wav`) to this folder

3. For each audio file (e.g., `track01.mp3`), create:
   - `track01_prompt.txt` - ACE-Step tags for the track
   - `track01_lyrics.txt` - Lyrics, or `[inst]` for instrumentals

**Quick dataset tagging:**

1. Switch to the **Training** tab
2. In **Dataset Mass Tagging** section:
   - Browse to your dataset folder
   - Enter **Base tags** (e.g., "lofi hip hop, chill, jazzy")
   - Click **Create prompt files** and **Create [inst] lyrics files**

**Start training:**

1. In the **Training Configuration** section:
   - Enter an **Experiment/adapter name** (e.g., `my_lofi_v1`)
   - Select a **LoRA config (JSON)** preset
   - Set **Max epochs** (e.g., 20)
   - Set **Learning rate** (e.g., `1e-4`)
   - Browse to your **Dataset folder**
2. Click **Start Training**
3. Monitor progress in the terminal and UI
4. Training saves checkpoints and final adapter to `custom_lora/`

**Use your trained LoRA:**

1. Return to the **Generate** tab
2. Switch to the **Advanced** tab
3. Find the **LoRA Adapter** section
4. Select your trained LoRA from the dropdown
5. Set **LoRA weight** (typically 0.5 - 2.0)
6. Generate tracks with your custom style!

### 6. Voice Cloning

**Generate TTS with a cloned voice:**

1. Switch to the **Voice Clone** tab
2. Upload a short **reference audio clip** (MP3 or WAV)
   - 3-10 seconds of clear speech works best
   - The voice should be representative of what you want to clone
3. Enter the **text** you want to synthesize
4. Click **Generate**
5. Wait for processing (first use downloads XTTS v2 model ~1.9 GB)
6. The result appears in the Music Player

**Note:** Requires ffmpeg for non-WAV files: `brew install ffmpeg`

---

## Generation Settings Explained

### Core Settings

- **Base filename:** Prefix for your output WAV files
- **Genre / Style Prompt:** Main ACE-Step prompt describing genre, instruments, mood, tempo
- **Instrumental toggle:** When checked, generates instrumental tracks using `[inst]` token
- **Lyrics:** Enter lyrics with markers like `[verse]`, `[chorus]`, `[solo]`, `[bridge]`
- **Target length (seconds):** Approximate duration of the generated track
- **Fade in/out (seconds):** Audio fades at start and end (0.5-2.0 seconds typical)
- **Inference steps:** 50-125 is a good range (higher = slower, not always better quality)
- **Guidance scale:** How strongly ACE-Step follows your text (extreme values can add noise)
- **BPM (optional):** Adds tempo hint to tags (e.g., "tempo 120 bpm")
- **Seed:** Random seed for generation (uncheck Random to lock seed for variations)

### Advanced Settings

- **Scheduler type:** Euler, Heun, or ping-pong scheduling
- **CFG mode:** APG, CFG, or CFG★ with related parameters
- **ERG switches:** Tag, lyric, and diffusion expert-routing gates
- **Repaint/extend:** Modify existing audio segments or extend tracks
- **Audio2Audio:** Use reference audio to guide generation
- **LoRA adapter:** Apply trained LoRAs with custom weights

---

## Troubleshooting

### First launch takes forever

- Check the terminal for pip or download errors
- Verify sufficient free disk space (needs tens of GB)
- Check network connectivity for model downloads
- Be patient - first setup downloads several GB of models

### "No .wav files found yet" in Music Player

- Generate a track first from the Generate tab
- Verify the **Output directory** field points to the correct folder
- Check that generation completed successfully (watch terminal logs)

### Out of memory errors

- Reduce **Target length** for generation
- Reduce **Max clip seconds** for training
- Lower batch or gradient accumulation values
- Close other applications to free unified memory

### macOS security warnings

- Go to `System Settings > Privacy & Security`
- Click `Open Anyway` for AceForge.app
- Or run: `sudo xattr -cr /Applications/AceForge.app`

### Browser doesn't open automatically

- Manually navigate to `http://127.0.0.1:5056/` in your browser
- Check terminal for error messages
- Ensure no other application is using port 5056

### Python version issues

```bash
# Check Python version (needs 3.10+)
python3 --version

# Install via Homebrew if needed
brew install python@3.10
```

### Permission denied when running CDMF.sh

```bash
chmod +x CDMF.sh
```

### Virtual environment issues

```bash
# Remove and recreate venv
rm -rf venv_ace
./CDMF.sh
```

### MPS (Metal) backend errors

- Ensure macOS 12.0+ for MPS support
- Some operations may fall back to CPU
- Try setting environment variable:
  ```bash
  export ACE_PIPELINE_DTYPE=float32
  ./CDMF.sh
  ```

---

## Performance Tips for Apple Silicon

- **Unified memory:** Apple Silicon efficiently shares memory between CPU and GPU
- **Batch sizes:** Start small and gradually increase to find optimal performance
- **Model precision:** Pipeline automatically uses float32 for MPS compatibility
- **Generation length:** Longer tracks require more memory; start short and scale up
- **Close other apps:** Free up unified memory for better generation performance

---

## Additional Resources

- **Detailed User Guide:** See [USAGE.md](../USAGE.md) in the repository
- **macOS Port Notes:** See [MACOS_PORT.md](../MACOS_PORT.md) for platform-specific details
- **UI Development:** See [UIDEV.md](../UIDEV.md) for interface development notes
- **GitHub Repository:** [audiohacking/AceForge](https://github.com/audiohacking/AceForge)
- **ACE-Step Project:** [ace-step/ACE-Step](https://github.com/ace-step/ACE-Step)
- **Report Issues:** [GitHub Issues](https://github.com/audiohacking/AceForge/issues)

---

## Contributing

Issues and Pull Requests are welcome! If you're changing anything related to training, model setup, or packaging, please include:
- What GPU/hardware you tested on
- Exact steps to reproduce any bug you fixed
- Performance impact of your changes

---

## License

This project's source code is licensed under the **Apache License 2.0**. See [LICENSE.txt](../LICENSE.txt) for full details.

---

**Happy Music Making! 🎵**
