# AceForge UI Development Documentation

**Version:** v0.1  
**Last Updated:** 2026-01-23  
**Purpose:** Complete reference for the current AceForge UI architecture, framework, and features for future UI rewrites.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Framework & Technology Stack](#2-framework--technology-stack)
3. [UI Structure & Components](#3-ui-structure--components)
4. [JavaScript Architecture](#4-javascript-architecture)
5. [API Endpoints](#5-api-endpoints)
6. [State Management](#6-state-management)
7. [Styling & CSS](#7-styling--css)
8. [Data Flow & Communication](#8-data-flow--communication)
9. [Features & Functionality](#9-features--functionality)
10. [Key Implementation Details](#10-key-implementation-details)

---

## 1. Architecture Overview

### 1.1 High-Level Architecture

AceForge uses a **Flask + pywebview** hybrid architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    aceforge_app.py                      │
│  (Main Entry Point - PyInstaller Bundle)               │
│  - Monkey-patches webview.start() as singleton         │
│  - Starts Flask server in background thread            │
│  - Creates pywebview window pointing to Flask server    │
│  - Handles window lifecycle and cleanup                 │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ imports
                   ▼
┌─────────────────────────────────────────────────────────┐
│                  music_forge_ui.py                      │
│  (Flask Application)                                     │
│  - Flask app initialization                             │
│  - Blueprint registration                               │
│  - Log streaming infrastructure                        │
│  - Static file serving                                  │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ serves HTML/CSS/JS
                   ▼
┌─────────────────────────────────────────────────────────┐
│              cdmf_template.py (HTML)                    │
│  - Single-page application template                     │
│  - Jinja2 template with embedded structure              │
│  - Loads external CSS/JS files                         │
└──────────────────┬──────────────────────────────────────┘
                   │
                   │ loads
                   ▼
┌─────────────────────────────────────────────────────────┐
│         static/scripts/*.js (JavaScript Modules)       │
│  - Modular JavaScript architecture                     │
│  - Each module handles specific UI concerns             │
│  - Communicates via window.CDMF global object          │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Execution Modes

**Frozen App Mode (Production):**
- Entry point: `aceforge_app.py`
- Flask server runs in background thread
- pywebview provides native macOS window
- No terminal window (console=False in PyInstaller spec)
- Window close triggers cleanup and exit

**Development Mode:**
- Entry point: `music_forge_ui.py` (when run directly)
- Can use pywebview OR browser fallback
- Terminal window shows server logs
- Useful for development and debugging

### 1.3 Communication Patterns

1. **Flask Backend → Frontend:**
   - Server-Sent Events (SSE) for log streaming (`/logs/stream`)
   - JSON API endpoints for data (`/tracks.json`, `/progress`, etc.)
   - HTML form submissions for generation/training

2. **Frontend → Flask Backend:**
   - `fetch()` calls to REST endpoints
   - Form submissions (POST) for generation/training
   - Hidden iframes for form submissions (legacy pattern)

3. **pywebview Bridge:**
   - `pywebview_bridge.js` intercepts `fetch()` calls
   - Maps to `window.pywebview.api` methods (serverless mode)
   - Falls back to real `fetch()` if pywebview API unavailable

---

## 2. Framework & Technology Stack

### 2.1 Backend Framework

**Flask (Python Web Framework)**
- **Version:** Latest (from requirements)
- **Purpose:** HTTP server, routing, template rendering
- **Server:** Waitress (WSGI server) - production-ready, multi-threaded
- **Port:** 5056 (hardcoded)
- **Host:** 127.0.0.1 (localhost only)

**Key Flask Components:**
- **Blueprints:** Modular route organization
  - `cdmf_generation` - Generation endpoints
  - `cdmf_tracks` - Track management
  - `cdmf_training` - LoRA training
  - `cdmf_models` - Model download/management
  - `cdmf_mufun` - MuFun analyzer
  - `cdmf_lyrics` - Lyrics generation

### 2.2 Frontend Framework

**Vanilla JavaScript (No Framework)**
- **Architecture:** Modular, namespace-based
- **Global Object:** `window.CDMF` - main namespace
- **State Management:** Shared state object in `window.CDMF.state`
- **No Build Step:** Direct script includes in HTML

**pywebview Integration:**
- **Library:** `pywebview` (Python package)
- **Version:** 5.1
- **Purpose:** Native macOS window wrapper
- **Bridge:** `pywebview_bridge.js` - shims fetch() to pywebview API

### 2.3 Template Engine

**Jinja2 (via Flask)**
- **Template File:** `cdmf_template.py` (contains HTML string)
- **Rendering:** `render_template_string()` in Flask
- **Variables:** Passed from Flask routes to template
- **Static Files:** Served via Flask's `url_for('static', ...)`

### 2.4 Styling

**CSS (Vanilla, No Preprocessor)**
- **File:** `static/scripts/cdmf.css`
- **Approach:** Utility classes, component-based
- **Theme:** Dark mode (color-scheme: dark)
- **Design System:** Custom, not using external framework

---

## 3. UI Structure & Components

### 3.1 HTML Structure (from cdmf_template.py)

The UI is a **single-page application** with the following structure:

```html
<body>
  <div class="page">
    <!-- 1. Titlebar -->
    <div class="cd-titlebar">
      - Logo + "AceForge" title (gradient text)
      - Version badge (v0.1)
      - Exit button
    </div>

    <!-- 2. Tagline -->
    <p class="tagline">Description text</p>

    <!-- 3. Console Panel (Collapsible) -->
    <div class="card" id="consoleCard">
      - Collapsible server console logs
      - Real-time log streaming
    </div>

    <!-- 4. Settings Panel (Collapsible) -->
    <div class="card" id="settingsCard">
      - Models folder configuration
    </div>

    <!-- 5. Music Player Card -->
    <div class="card">
      - Track list (sortable, filterable)
      - Category filter chips
      - Player controls (play, pause, stop, loop, mute)
      - Progress slider
      - Volume slider
      - Audio element (<audio id="audioPlayer">)
    </div>

    <!-- 6. Mode Tabs -->
    <div class="tab-row">
      - "Generate" tab (active by default)
      - "Training" tab
    </div>

    <!-- 7. Generation Form (mode: generate) -->
    <form id="generateForm" class="card card-mode" data-mode="generate">
      - Loading bar
      - Model status notice
      - Core/Advanced tab switcher
      - Core knobs (prompt, lyrics, presets, sliders)
      - Advanced knobs (scheduler, CFG, LoRA, etc.)
      - Saved presets section
      - Output directory
      - Generate button
    </form>

    <!-- 8. Training Form (mode: train) -->
    <form id="trainForm" class="card card-mode" data-mode="train">
      - Training status banner
      - Dataset selection
      - LoRA config selection
      - Training parameters
      - Start/Pause/Resume/Cancel buttons
    </form>

    <!-- 9. Dataset Tagging Card (mode: train) -->
    <div id="datasetTagCard" class="card card-mode" data-mode="train">
      - Mass tagging tools
    </div>

    <!-- 10. MuFun Card (mode: train) -->
    <div id="mufunCard" class="card card-mode" data-mode="train">
      - MuFun analyzer controls
    </div>

    <!-- 11. Modals -->
    - Auto prompt/lyrics modal
    - LoRA config help modal
    - Lyrics generation overlay

    <!-- 12. Hidden Elements -->
    - <iframe> elements for form submissions (legacy)
    - <select id="trackList"> for audio player
  </div>
</body>
```

### 3.2 Component Hierarchy

```
page
├── cd-titlebar (header)
├── tagline (description)
├── consoleCard (collapsible)
├── settingsCard (collapsible)
├── Music Player Card
│   ├── Track list header (sortable)
│   ├── Track list panel (filterable)
│   ├── Progress controls
│   └── Player controls
├── Mode Tabs (Generate/Training)
├── generateForm (card-mode, data-mode="generate")
│   ├── Core/Advanced tabs
│   ├── Core knobs section
│   └── Advanced knobs section
├── trainForm (card-mode, data-mode="train")
├── datasetTagCard (card-mode, data-mode="train")
└── mufunCard (card-mode, data-mode="train")
```

### 3.3 Key UI Components

**Cards:**
- `.card` - Main container component
- `.card-header-row` - Card title and actions
- `.card-mode` - Mode-specific cards (show/hide based on mode)

**Form Rows:**
- `.row` - Horizontal form row (label + input)
- `.slider-row` - Row with range slider + number input
- `.row-progress` - Progress bar container

**Buttons:**
- `.btn` - Base button style
- `.btn.primary` - Primary action button
- `.btn.secondary` - Secondary action
- `.btn.danger` - Destructive action
- `.btn:disabled` - Disabled state

**Tabs:**
- `.tab-row` - Tab container
- `.tab-btn` - Tab button
- `.tab-btn-active` - Active tab

**Presets:**
- `.preset-buttons` - Container for preset buttons
- Preset buttons use icons + labels

**Track List:**
- `.track-list-header` - Sortable column headers
- `.track-list-panel` - Track rows container
- `.track-row` - Individual track row
- `.track-fav-btn` - Favorite button
- `.track-delete-btn` - Delete button

---

## 4. JavaScript Architecture

### 4.1 Module Structure

JavaScript is organized into **modular files**, each handling specific UI concerns:

**Core Modules:**
- `cdmf_main.js` - Main orchestration, knob tabs, training controls
- `cdmf_generation_ui.js` - Generation form logic, progress updates
- `cdmf_player_ui.js` - Audio player controls and track management
- `cdmf_tracks_ui.js` - Track list rendering, sorting, filtering
- `cdmf_presets_ui.js` - Preset management (load/save/delete)
- `cdmf_mode_ui.js` - Mode switching (Generate/Training)
- `cdmf_training_ui.js` - Training form logic and status updates
- `cdmf_lora_ui.js` - LoRA selection and management
- `cdmf_mufun_ui.js` - MuFun analyzer UI
- `cdmf_console.js` - Console log streaming and display
- `pywebview_bridge.js` - pywebview API bridge (fetch shim)

### 4.2 Global Namespace Pattern

All modules use a shared global namespace:

```javascript
const CDMF = (window.CDMF = window.CDMF || {});
```

**Shared State Object:**
```javascript
CDMF.state = {
  candyModelsReady: boolean,
  candyModelStatusState: string,
  candyModelStatusMessage: string,
  candyIsGenerating: boolean,
  candyGenerationCounter: number,
  candyActiveGenerationToken: number,
  candyTrackSortKey: string | null,
  candyTrackSortDir: "asc" | "desc",
  candyTrackFilterCategories: Set,
  progressTimer: Timer | null,
  // ... more state
};
```

**Function Exposure:**
```javascript
CDMF.switchKnobTab = function(which) { ... };
CDMF.onSubmitForm = function(event) { ... };
CDMF.setPreset = function(presetId) { ... };
// ... more functions
```

### 4.3 Module Responsibilities

**cdmf_main.js:**
- Initializes shared state
- Handles Core/Advanced tab switching
- Training pause/resume/cancel controls
- Global utility functions

**cdmf_generation_ui.js:**
- Generation form submission
- Progress bar updates (via polling `/progress`)
- Loading bar animation
- Model status polling
- Lyrics generation UI
- Form validation

**cdmf_player_ui.js:**
- HTML5 audio element management
- Play/pause/stop/rewind/loop controls
- Volume control
- Time display formatting
- Progress slider synchronization
- Track selection from list

**cdmf_tracks_ui.js:**
- Track list rendering
- Sorting (by name, length, category, created)
- Filtering by category
- Favorite toggling
- Track deletion
- Category editing (right-click context menu)
- Metadata loading (length, category)

**cdmf_presets_ui.js:**
- Preset button click handlers
- Preset application (fills form fields)
- Random preset selection
- Instrumental/vocal preset group switching

**cdmf_mode_ui.js:**
- Mode tab switching (Generate/Training)
- Shows/hides mode-specific cards
- Updates active tab styling

**cdmf_training_ui.js:**
- Training form submission
- Training status polling
- Progress bar updates
- Pause/resume/cancel handlers
- LoRA config loading

**cdmf_lora_ui.js:**
- LoRA selection dropdown
- LoRA file browser
- LoRA weight input
- LoRA application to form

**cdmf_mufun_ui.js:**
- MuFun model status
- Dataset folder selection
- Analysis progress
- Results display

**cdmf_console.js:**
- Server-Sent Events (SSE) connection to `/logs/stream`
- Log message parsing and filtering
- Console panel show/hide
- Progress bar extraction from tqdm output

**pywebview_bridge.js:**
- Detects pywebview environment
- Intercepts `fetch()` calls
- Maps endpoints to `window.pywebview.api` methods
- Provides Response-like objects for compatibility

### 4.4 Initialization Flow

1. **HTML loads** → Scripts load in order (see template)
2. **cdmf_main.js** → Initializes `window.CDMF` and shared state
3. **Other modules** → Attach functions to `window.CDMF`
4. **DOMContentLoaded** → Modules initialize event listeners
5. **Bootstrap data** → `window.CDMF_BOOT` provides initial state
6. **Polling starts** → Model status, progress, training status

### 4.5 Event Handling Patterns

**Inline Handlers (Template):**
```html
<button onclick="CDMF.switchMode('generate')">Generate</button>
```

**DOM Listeners (JavaScript):**
```javascript
document.getElementById('btnPlay').addEventListener('click', function() { ... });
```

**Form Submission:**
```html
<form onsubmit="return CDMF.onSubmitForm(event)">
```

**Custom Events:**
- None currently used (could be added for decoupling)

---

## 5. API Endpoints

### 5.1 Main Routes (music_forge_ui.py)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Main UI page (renders template) |
| GET | `/healthz` | Health check endpoint |
| GET | `/loading` | Loading page (splash screen) |
| GET | `/logs/stream` | Server-Sent Events log stream |
| POST | `/shutdown` | Gracefully shutdown server |

### 5.2 Generation Routes (cdmf_generation.py)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Index page (same as main `/`) |
| POST | `/generate` | Start ACE-Step generation |
| POST | `/prompt_lyrics/generate` | Generate prompt/lyrics from concept |

**Generation Request (POST `/generate`):**
```python
Form data:
- prompt: str (genre/style description)
- lyrics: str (optional, with [verse], [chorus] markers)
- instrumental: bool (checkbox)
- target_seconds: float
- fade_in: float
- fade_out: float
- steps: int
- guidance_scale: float
- seed: int
- seed_random: bool
- bpm: int | None
- vocal_gain_db: float
- instrumental_gain_db: float
- scheduler_type: str ("euler" | "heun" | "pingpong")
- cfg_type: str ("apg" | "cfg" | "cfg_star")
- omega_scale: float
- lora_name_or_path: str
- lora_weight: float
- ref_audio_file: File (optional)
- ref_audio_strength: float
- # ... more advanced params
```

### 5.3 Track Management Routes (cdmf_tracks.py)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/music/<filename>` | Serve audio file |
| GET | `/progress` | Get generation progress (JSON) |
| GET | `/tracks.json` | List all tracks (JSON) |
| GET/POST | `/tracks/meta` | Get/set track metadata |
| GET/POST | `/user_presets` | Get/save user presets |
| POST | `/tracks/rename` | Rename track file |
| POST | `/tracks/delete` | Delete track file |

**Progress Response (GET `/progress`):**
```json
{
  "stage": "generating" | "ace_load" | "done" | "error",
  "current": 0.0-1.0,
  "total": 1.0,
  "done": boolean,
  "error": boolean,
  "message": string
}
```

**Tracks Response (GET `/tracks.json`):**
```json
{
  "tracks": [
    {
      "name": "filename.wav",
      "path": "/path/to/file.wav",
      "url": "/music/filename.wav"
    }
  ]
}
```

### 5.4 Training Routes (cdmf_training.py)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/train_lora` | Start LoRA training |
| GET | `/train_lora/status` | Get training status |
| GET | `/train_lora/configs` | List LoRA config files |
| POST | `/train_lora/pause` | Pause training |
| POST | `/train_lora/resume` | Resume training |
| POST | `/train_lora/cancel` | Cancel training |
| POST | `/dataset_mass_tag` | Mass-create prompt/lyrics files |

### 5.5 Model Management Routes (cdmf_models.py)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/models/status` | Get model download status |
| POST | `/models/ensure` | Download/verify ACE-Step models |
| GET/POST | `/models/folder` | Get/set models folder path |

### 5.6 MuFun Routes (cdmf_mufun.py)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/mufun/status` | Get MuFun model status |
| POST | `/mufun/ensure` | Download/verify MuFun model |
| POST | `/mufun/analyze_dataset` | Analyze dataset folder |

### 5.7 Lyrics Routes (cdmf_lyrics.py)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/lyrics/status` | Get lyrics model status |
| POST | `/lyrics/ensure` | Download/verify lyrics model |
| POST | `/lyrics/generate` | Generate lyrics from concept |

---

## 6. State Management

### 6.1 Client-Side State

**Global State Object (`window.CDMF.state`):**
```javascript
{
  // Model status
  candyModelsReady: boolean,
  candyModelStatusState: "unknown" | "absent" | "downloading" | "ready" | "error",
  candyModelStatusMessage: string,
  candyModelStatusTimer: Timer | null,

  // Generation state
  candyIsGenerating: boolean,
  candyGenerationCounter: number,
  candyActiveGenerationToken: number,
  candyHasSeenWork: boolean,
  progressTimer: Timer | null,

  // Track list state
  candyTrackSortKey: string | null,
  candyTrackSortDir: "asc" | "desc",
  candyTrackFilterCategories: Set<string>,

  // Lyrics model state
  lyricsModelState: "unknown" | "absent" | "downloading" | "ready" | "error",
  lyricsModelMessage: string,
  lyricsModelStatusTimer: Timer | null,

  // UI state
  candyGenerateButtonDefaultHTML: string | null,
  candyTrainButtonDefaultHTML: string | null,
  autoPromptLyricsDefaultHTML: string | null
}
```

**Backward Compatibility Globals:**
```javascript
window.candyModelsReady = CDMF.state.candyModelsReady;
window.candyModelStatusState = CDMF.state.candyModelStatusState;
window.candyIsGenerating = CDMF.state.candyIsGenerating;
```

### 6.2 Server-Side State (cdmf_state.py)

**Module:** `cdmf_state.py`

**Shared State Objects:**
```python
# Model status
MODEL_STATUS = {
    "state": "unknown" | "absent" | "downloading" | "ready" | "error",
    "message": string
}
MODEL_LOCK = threading.Lock()

# Generation progress
GENERATION_PROGRESS = {
    "stage": string,
    "current": float,
    "total": float,
    "done": boolean,
    "error": boolean,
    "message": string
}
PROGRESS_LOCK = threading.Lock()

# Training status
TRAINING_STATUS = {
    "state": "idle" | "running" | "paused" | "cancelled" | "error",
    "message": string,
    "progress": float
}
TRAINING_LOCK = threading.Lock()
```

### 6.3 State Synchronization

**Client → Server:**
- Form submissions (POST)
- Polling (GET requests every N seconds)
- Server-Sent Events (SSE) for logs

**Server → Client:**
- JSON responses to polling requests
- Server-Sent Events for real-time logs
- Progress updates via `/progress` endpoint

**Polling Intervals:**
- Model status: ~2-3 seconds
- Generation progress: ~0.5-1 second (during generation)
- Training status: ~1-2 seconds (during training)

---

## 7. Styling & CSS

### 7.1 Design System

**Color Palette:**
```css
:root {
  --cd-accent: #f97316;        /* Orange accent */
  --cd-text-dim: #cbd5e1;     /* Dimmed text */
  --cd-border: #334155;        /* Border color */
}

Background: #020617 (very dark blue-black)
Text: #e5e7eb (light gray)
Cards: #020617 with border #111827
```

**Typography:**
- Font: `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- Title: Gradient text (orange → purple → blue → cyan)
- Body: Light gray (#e5e7eb)
- Small text: #6b7280 (muted gray)

### 7.2 Component Classes

**Cards:**
- `.card` - Main container (dark background, rounded, border, shadow)
- `.card-header-row` - Flex row for title + actions
- `.card-mode` - Mode-specific visibility

**Form Elements:**
- `.row` - Horizontal form row (label + input)
- `.slider-row` - Row with range slider
- `.row label` - Form label (min-width: 120px)
- `.row input[type="text"]` - Text input styling
- `.row textarea` - Textarea styling

**Buttons:**
- `.btn` - Base button (padding, border-radius, cursor)
- `.btn.primary` - Primary action (accent color)
- `.btn.secondary` - Secondary action
- `.btn.danger` - Destructive action (red)
- `.btn:disabled` - Disabled state (opacity, no pointer)
- `.btn:hover:not(:disabled)` - Hover effect

**Tabs:**
- `.tab-row` - Tab container (flex, gap)
- `.tab-btn` - Tab button (padding, border, background)
- `.tab-btn-active` - Active tab (accent border)

**Track List:**
- `.track-list-header` - Sortable header row
- `.track-list-panel` - Track rows container
- `.track-row` - Individual track (hover effects)
- `.track-row.active` - Currently playing track
- `.track-fav-btn` - Favorite button (star)
- `.track-delete-btn` - Delete button (trash)

**Loading/Progress:**
- `.loading-bar` - Progress bar container
- `.loading-bar-inner` - Animated inner bar (candystripe)
- `.loading-bar.active` - Active state (shows animation)

**Presets:**
- `.preset-buttons` - Container for preset buttons
- Preset buttons use `.btn` class with icons

### 7.3 Responsive Design

**Current State:**
- Fixed max-width: 960px (centered)
- Not fully responsive (designed for desktop)
- Flexbox for layout
- No mobile breakpoints

**Layout:**
- Single column
- Cards stack vertically
- Form rows wrap on smaller screens

### 7.4 Animations

**Loading Bar:**
- Candystripe animation (rainbow gradient moving)
- CSS keyframes: `@keyframes cdmf-candystripe`
- Used during generation and model downloads

**Spinner:**
- CSS animation: `cdmf-spin` (rotation)
- Used in lyrics generation overlay

---

## 8. Data Flow & Communication

### 8.1 Generation Flow

```
User clicks "Generate"
  ↓
cdmf_generation_ui.js: onSubmitForm()
  ↓
Form submission (POST /generate)
  ↓
cdmf_generation.py: generate()
  ↓
generate_ace.py: generate_track_ace()
  ↓
Progress callbacks → cdmf_state.GENERATION_PROGRESS
  ↓
Client polls /progress endpoint
  ↓
cdmf_generation_ui.js: updateLoadingBarFraction()
  ↓
UI updates progress bar
```

### 8.2 Log Streaming Flow

```
Server logs → QueueHandler → LOG_QUEUE
  ↓
SSE endpoint (/logs/stream)
  ↓
cdmf_console.js: EventSource connection
  ↓
Parse log messages
  ↓
Filter noisy messages (task queue, client disconnected)
  ↓
Extract tqdm progress bars
  ↓
Display in console panel
```

### 8.3 Track List Updates

```
User action (favorite, delete, etc.)
  ↓
cdmf_tracks_ui.js: Event handler
  ↓
fetch() to /tracks/meta or /tracks/delete
  ↓
cdmf_tracks.py: Route handler
  ↓
Update file system / metadata
  ↓
Return JSON response
  ↓
cdmf_tracks_ui.js: Refresh track list
  ↓
fetch() to /tracks.json
  ↓
Re-render track list
```

### 8.4 Preset Management

```
User clicks preset button
  ↓
cdmf_presets_ui.js: setPreset()
  ↓
Fills form fields from preset data
  ↓
User clicks "Save" preset
  ↓
fetch() POST /user_presets
  ↓
cdmf_tracks.py: save_user_preset()
  ↓
Stores in JSON file
  ↓
Returns updated preset list
  ↓
cdmf_presets_ui.js: Updates preset dropdown
```

---

## 9. Features & Functionality

### 9.1 Music Generation

**Core Features:**
- Text prompt input (genre/style description)
- Lyrics input (optional, with structure markers)
- Instrumental mode toggle
- Preset buttons (quick style selection)
- Target length slider (15-240 seconds)
- Fade in/out controls
- Inference steps control
- Guidance scale control
- Seed control (random or fixed)
- BPM hint (optional)

**Advanced Features:**
- Scheduler selection (Euler, Heun, Ping-pong)
- CFG mode (APG, CFG, CFG★)
- Omega scale
- Guidance interval/decay
- ERG switches (Tag, Lyric, Diffusion)
- Custom steps (OSS)
- Repaint/extend tasks
- Audio2Audio (reference track)
- LoRA adapter selection
- Vocal/instrumental gain adjustment (post-process)

**Presets:**
- Built-in presets (instrumental and vocal)
- User-saved presets
- Random preset selection
- Preset categories

### 9.2 Music Player

**Features:**
- Track list with metadata (name, length, category, created date)
- Sortable columns (favorite, name, length, category, created)
- Category filtering (chips)
- Favorite toggling (★ button)
- Track deletion
- Category editing (right-click context menu)
- Play/pause/stop controls
- Rewind button
- Loop toggle
- Mute toggle
- Volume slider
- Progress slider (seek)
- Time display (current/total)

**Track Management:**
- Automatic discovery of .wav files in output directory
- Metadata stored in JSON files (favorites, categories)
- Track renaming
- Category assignment

### 9.3 LoRA Training

**Features:**
- Dataset folder selection
- Experiment name input
- LoRA config selection (JSON presets)
- Training parameters:
  - Max steps
  - Max epochs
  - Learning rate
  - Max clip seconds
  - SSL loss weight
  - Instrumental-only toggle
  - Save frequency
- Advanced trainer settings:
  - Precision (32-bit, 16-mixed, bf16-mixed)
  - Gradient accumulation
  - Gradient clipping
  - DataLoader reload frequency
  - Validation check interval
  - Device count
- Training controls:
  - Start training
  - Pause training
  - Resume training
  - Cancel training
- Progress indication (candystripe bar)

### 9.4 Dataset Tools

**Mass Tagging:**
- Dataset folder selection
- Base tags input
- Create prompt files
- Create [inst] lyrics files
- Overwrite existing files option

**MuFun Analyzer:**
- MuFun model status/installation
- Dataset folder selection
- Base tags input
- Instrumental-only toggle
- Analyze folder (auto-creates prompt/lyrics files)
- Results display

### 9.5 Model Management

**ACE-Step Models:**
- Model status display
- Download models button
- Models folder configuration
- Progress indication during download

**MuFun Model:**
- Model status display
- Install/check button
- Large download (~16.5GB)

**Lyrics Model:**
- Model status display
- Install/check button
- Used for prompt/lyrics generation

### 9.6 Prompt/Lyrics Generation

**Features:**
- Modal dialog for concept input
- Generate mode selection:
  - Prompt only
  - Lyrics only
  - Prompt + lyrics
- Auto-fills form fields
- Loading overlay during generation

### 9.7 Console Logs

**Features:**
- Collapsible console panel
- Real-time log streaming (SSE)
- Filtered messages (removes noise)
- Progress bar extraction from tqdm
- Useful for troubleshooting

---

## 10. Key Implementation Details

### 10.1 Form Submission Pattern

**Legacy Pattern (Hidden Iframes):**
```html
<form target="generation_frame" onsubmit="return CDMF.onSubmitForm(event)">
  <!-- form fields -->
</form>
<iframe id="generation_frame" name="generation_frame" style="display:none;"></iframe>
```

**Why Iframes:**
- Prevents page navigation on form submit
- Allows server to return HTML response (for errors)
- Legacy pattern, could be modernized to fetch()

### 10.2 Progress Updates

**Polling Pattern:**
```javascript
function pollProgress() {
  fetch('/progress')
    .then(r => r.json())
    .then(data => {
      updateLoadingBarFraction(data.current / data.total);
      if (!data.done) {
        setTimeout(pollProgress, 500);
      }
    });
}
```

**Server-Side:**
- Progress stored in `cdmf_state.GENERATION_PROGRESS`
- Updated via callbacks from `generate_ace.py`
- Thread-safe (uses locks)

### 10.3 Track Metadata

**Storage:**
- JSON files in output directory: `{trackname}.meta.json`
- Contains: `favorite`, `category`, `created`, etc.
- Loaded on track list refresh

**File Structure:**
```
output_dir/
  ├── track1.wav
  ├── track1.meta.json
  ├── track2.wav
  ├── track2.meta.json
  └── ...
```

### 10.4 Preset System

**Built-in Presets:**
- Defined in `presets.json` (loaded by `cdmf_tracks.load_presets()`)
- Two groups: `instrumental` and `vocal`
- Each preset has: `id`, `label`, `icon`, `prompt`, `seed_vibe`, etc.

**User Presets:**
- Stored in `user_presets.json` (in output directory)
- Saved via `/user_presets` POST endpoint
- Loaded on page load

### 10.5 Mode Switching

**Implementation:**
```javascript
CDMF.switchMode = function(mode) {
  // Hide all mode-specific cards
  document.querySelectorAll('.card-mode').forEach(card => {
    card.style.display = 'none';
  });
  
  // Show cards for selected mode
  document.querySelectorAll(`.card-mode[data-mode="${mode}"]`).forEach(card => {
    card.style.display = '';
  });
  
  // Update tab styling
  document.querySelectorAll('.mode-tab-btn').forEach(btn => {
    btn.classList.toggle('tab-btn-active', btn.dataset.mode === mode);
  });
};
```

### 10.6 pywebview Integration

**Bridge Pattern:**
- `pywebview_bridge.js` intercepts `fetch()` calls
- Maps to `window.pywebview.api` methods
- Provides Response-like objects for compatibility
- Falls back to real `fetch()` if pywebview unavailable

**Window Control API:**
- `WindowControlAPI` class in `aceforge_app.py`
- Exposed via `js_api` parameter to `webview.create_window()`
- Methods: `minimize()`, `restore()`, `maximize()`
- Called from JavaScript via `window.pywebview.api.minimize()`

### 10.7 Static File Serving

**Frozen App:**
```python
if getattr(sys, 'frozen', False):
    static_folder = Path(sys._MEIPASS) / 'static'
    app = Flask(__name__, static_folder=str(static_folder))
```

**Development:**
```python
else:
    app = Flask(__name__)  # Uses default 'static' folder
```

**URL Generation:**
```html
<link rel="stylesheet" href="{{ url_for('static', filename='scripts/cdmf.css') }}">
<script src="{{ url_for('static', filename='scripts/cdmf_main.js') }}"></script>
```

### 10.8 Log Streaming

**Server-Side:**
```python
LOG_QUEUE = queue.Queue(maxsize=1000)

class QueueHandler(logging.Handler):
    def emit(self, record):
        LOG_QUEUE.put_nowait(self.format(record))

@app.route("/logs/stream")
def stream_logs():
    def generate():
        while True:
            try:
                msg = LOG_QUEUE.get(timeout=1)
                yield f"data: {json.dumps({'message': msg})}\n\n"
            except queue.Empty:
                yield "data: {}\n\n"  # Keep-alive
    return Response(generate(), mimetype='text/event-stream')
```

**Client-Side:**
```javascript
const eventSource = new EventSource('/logs/stream');
eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  if (data.message) {
    appendLogMessage(data.message);
  }
};
```

### 10.9 Error Handling

**Form Validation:**
- Client-side: Basic checks in `onSubmitForm()`
- Server-side: Parameter validation in route handlers
- Error messages displayed in toast notifications

**Error Display:**
```html
<div class="toast error">
  {{ short_message }}
  <button onclick="CDMF.toggleDetails()">Details</button>
</div>
<div id="detailsPanel" class="details-panel">
  {{ details }}
</div>
```

### 10.10 Bootstrap Data

**Template Injection:**
```html
<script>
  window.CDMF_BOOT = {
    presets: {{ presets | tojson | safe }},
    modelsReady: {{ models_ready | tojson | safe }},
    modelState: {{ model_state | tojson | safe }},
    modelMessage: {{ model_message | tojson | safe }},
    autoplayUrl: {{ autoplay_url or '' | tojson | safe }},
    urls: {
      trainStatus: "{{ url_for('cdmf_training.train_lora_status') }}",
      mufunStatus: "{{ url_for('cdmf_mufun.mufun_status') }}",
      // ...
    }
  };
</script>
```

**Backward Compatibility:**
```javascript
window.CANDY_PRESETS = window.CDMF_BOOT.presets;
window.CANDY_MODELS_READY = window.CDMF_BOOT.modelsReady;
// ...
```

---

## 11. File Structure Reference

### 11.1 Backend Files

```
aceforge_app.py          # Main entry point (PyInstaller bundle)
music_forge_ui.py        # Flask app initialization
cdmf_template.py         # HTML template (Jinja2 string)
cdmf_generation.py       # Generation blueprint
cdmf_tracks.py           # Track management blueprint
cdmf_training.py         # Training blueprint
cdmf_models.py           # Model management blueprint
cdmf_mufun.py            # MuFun analyzer blueprint
cdmf_lyrics.py           # Lyrics generation blueprint
cdmf_state.py            # Shared state management
cdmf_paths.py            # Path configuration
generate_ace.py          # ACE-Step generation logic
```

### 11.2 Frontend Files

```
static/
  ├── scripts/
  │   ├── cdmf_main.js           # Main orchestration
  │   ├── cdmf_generation_ui.js  # Generation form
  │   ├── cdmf_player_ui.js      # Audio player
  │   ├── cdmf_tracks_ui.js      # Track list
  │   ├── cdmf_presets_ui.js     # Preset management
  │   ├── cdmf_mode_ui.js        # Mode switching
  │   ├── cdmf_training_ui.js    # Training form
  │   ├── cdmf_lora_ui.js        # LoRA selection
  │   ├── cdmf_mufun_ui.js       # MuFun analyzer
  │   ├── cdmf_console.js        # Console logs
  │   ├── pywebview_bridge.js    # pywebview bridge
  │   └── cdmf.css               # Stylesheet
  ├── aceforge_logo.png          # App logo
  ├── aceforge.ico               # Windows icon
  └── loading.html               # Splash screen
```

### 11.3 Configuration Files

```
presets.json              # Built-in presets
user_presets.json         # User-saved presets (in output dir)
CDMF.spec                 # PyInstaller spec file
requirements_ace_macos.txt # Python dependencies
```

---

## 12. Known Limitations & Technical Debt

### 12.1 Current Limitations

1. **No Build Step:**
   - JavaScript files loaded directly (no bundling/minification)
   - No TypeScript or modern JS features
   - No module system (uses global namespace)

2. **Legacy Patterns:**
   - Hidden iframes for form submission
   - Polling instead of WebSockets
   - Inline event handlers in HTML

3. **Responsive Design:**
   - Fixed width (960px max)
   - No mobile breakpoints
   - Not optimized for small screens

4. **State Management:**
   - Global state object (not reactive)
   - Manual synchronization between modules
   - No state persistence (except presets)

5. **Error Handling:**
   - Basic error display
   - No error recovery mechanisms
   - Limited user feedback on failures

### 12.2 Technical Debt

1. **Code Organization:**
   - Large HTML template (1700+ lines)
   - JavaScript modules could be more modular
   - Some duplicate code between modules

2. **Performance:**
   - Polling intervals could be optimized
   - No request debouncing
   - Large track lists not virtualized

3. **Accessibility:**
   - Limited ARIA labels
   - Keyboard navigation not fully implemented
   - Screen reader support minimal

4. **Testing:**
   - No unit tests
   - No integration tests
   - Manual testing only

---

## 13. Migration Notes for UI Rewrite

### 13.1 What to Preserve

**Core Functionality:**
- All generation parameters and controls
- Track management features
- Preset system
- Training workflow
- Model management

**User Experience:**
- Collapsible panels (console, settings)
- Mode switching (Generate/Training)
- Core/Advanced tab pattern
- Progress indication
- Real-time log streaming

**API Compatibility:**
- Keep existing Flask routes (or provide migration path)
- Maintain JSON response formats
- Preserve form parameter names

### 13.2 What Can Be Improved

**Architecture:**
- Modern JavaScript framework (React, Vue, Svelte)
- Build system (Vite, Webpack, etc.)
- TypeScript for type safety
- Component-based architecture

**State Management:**
- Reactive state (Redux, Zustand, Pinia)
- Proper state persistence
- Optimistic updates

**Communication:**
- WebSockets instead of polling
- GraphQL or REST API
- Better error handling

**UI/UX:**
- Modern design system
- Responsive layout
- Better accessibility
- Improved animations
- Dark/light theme toggle

**Performance:**
- Code splitting
- Lazy loading
- Virtual scrolling for track lists
- Request debouncing

---

## 14. Development Workflow

### 14.1 Local Development

1. **Run Flask server:**
   ```bash
   python music_forge_ui.py
   ```

2. **Edit files:**
   - HTML: Edit `cdmf_template.py`
   - CSS: Edit `static/scripts/cdmf.css`
   - JS: Edit `static/scripts/*.js`
   - Python: Edit `*.py` files

3. **Reload browser:**
   - Hard refresh (Cmd+Shift+R) to clear cache

### 14.2 Testing Bundled App

1. **Build app:**
   ```bash
   bash build_local.sh
   ```

2. **Run app:**
   ```bash
   open dist/AceForge.app
   ```

3. **Check logs:**
   - Console logs in UI (if console panel open)
   - System logs (Console.app on macOS)

### 14.3 Debugging

**Client-Side:**
- Browser DevTools (F12)
- `console.log()` in JavaScript
- Network tab for API calls

**Server-Side:**
- Terminal output (if running from source)
- Console panel in UI (log streaming)
- Python debugger (pdb)

---

## 15. Conclusion

This document provides a comprehensive reference for the current AceForge UI architecture. When rewriting the UI, use this as a guide to:

1. **Understand the current implementation** - How things work now
2. **Preserve functionality** - What features must be maintained
3. **Identify improvements** - What can be modernized
4. **Plan migration** - How to transition from old to new

The current UI is functional but uses older patterns. A modern rewrite should:
- Use a modern JavaScript framework
- Implement proper state management
- Improve responsive design
- Enhance accessibility
- Optimize performance
- Maintain API compatibility (or provide migration)

**Key Files to Reference:**
- `cdmf_template.py` - HTML structure
- `static/scripts/cdmf_*.js` - JavaScript modules
- `static/scripts/cdmf.css` - Styling
- `music_forge_ui.py` - Flask routes
- `cdmf_*.py` - Blueprint implementations

---

**End of Document**
