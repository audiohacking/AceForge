# GitHub Copilot Custom Instructions for AceForge

## Project Overview

**AceForge** is a local-first AI music workstation for macOS Silicon that provides a comprehensive interface for AI-powered music generation, training, and audio processing. The project integrates multiple AI models including ACE-Step (text-to-music), Demucs (stem separation), XTTS v2 (voice cloning), and basic-pitch (MIDI generation).

### Key Characteristics
- **Platform**: macOS-first with Apple Silicon (M1/M2/M3/M4) optimization
- **Architecture**: Flask backend + React/TypeScript frontend
- **AI/ML Focus**: Heavy use of PyTorch with MPS (Metal Performance Shaders) acceleration
- **Deployment**: Both source-based and PyInstaller-bundled macOS app
- **Privacy**: 100% local processing - no cloud dependencies after model downloads

## Technology Stack

### Backend (Python)
- **Framework**: Flask with Blueprint-based architecture
- **ML/AI**: PyTorch (with MPS support), Transformers, ACE-Step, Demucs
- **Audio Processing**: pydub, audioread, soundfile, librosa
- **Dependencies**: See `requirements_ace_macos.txt`
- **Python Version**: 3.10+

### Frontend (TypeScript/React)
- **Framework**: React 19 with TypeScript
- **Build Tool**: Vite
- **UI Library**: Custom components with Lucide icons
- **State Management**: React hooks and context
- **Package Manager**: Bun (preferred) or npm

### Build & Distribution
- **Bundling**: PyInstaller for macOS app bundles
- **Code Signing**: Ad-hoc signing with optional Developer ID support
- **CI/CD**: GitHub Actions for automated builds and tests

## Code Style and Conventions

### Python Backend

#### File Organization
- Prefix module names with `cdmf_` for core functionality (e.g., `cdmf_generation.py`, `cdmf_training.py`)
- Use Blueprint pattern for Flask routes (e.g., `create_generation_blueprint()`)
- Keep business logic separate from route handlers

#### Type Hints
- Use `from __future__ import annotations` for forward references
- Prefer typed function signatures:
  ```python
  def create_blueprint(
      html_template: str,
      ui_defaults: Dict[str, Any],
      callback: Callable[..., Dict[str, Any]],
  ) -> Blueprint:
  ```

#### Error Handling
- Use try-except blocks with specific exception types
- Use Python's `logging` module for error logging and diagnostics
- For quick debugging, `print(..., flush=True)` is acceptable but prefer logging
- Return structured error responses in API endpoints:
  ```python
  import logging
  logger = logging.getLogger(__name__)
  
  try:
      # ... operation
  except Exception as e:
      logger.error(f"Operation failed: {e}", exc_info=True)
      return jsonify({"error": "Description", "details": str(e)}), 500
  ```

#### Documentation
- Use docstrings for functions explaining purpose, parameters, and return values
- Add inline comments for complex logic, especially ML/audio processing steps
- Document environment variables and configuration options

### TypeScript/React Frontend

#### Component Structure
- Use functional components with hooks
- Prefer named exports for components
- Co-locate types when component-specific, otherwise use `types.ts`

#### Type Safety
- Define interfaces for props and state
- Use discriminated unions for view states
- Avoid `any` type - use `unknown` when type is truly dynamic

#### State Management
- Use React Context for global state (auth, theme, responsive)
- Keep component state local when possible
- Use refs for imperative DOM access and intervals

#### API Calls
- Centralize API calls in `services/api.ts`
- Use async/await with proper error handling
- Show user-friendly error messages in UI

## Architecture Patterns

### Backend Architecture

#### Blueprint Pattern
Each major feature has its own Blueprint:
- `cdmf_generation.py` - Music generation
- `cdmf_training.py` - LoRA training
- `cdmf_stem_splitting.py` - Audio stem separation
- `cdmf_voice_cloning.py` - TTS voice cloning
- `cdmf_midi_generation.py` - Audio-to-MIDI transcription

#### State Management
- Global state in `cdmf_state.py` for model loading and training status
- Track library management in `cdmf_tracks.py`
- Path handling centralized in `cdmf_paths.py`

#### Model Loading
- Lazy loading: Models loaded on first use, not at startup
- Singleton pattern: One instance per model type
- MPS optimization: Automatic device selection (`mps`, `cuda`, `cpu`)

### Frontend Architecture

#### Component Hierarchy
```
App.tsx (main container)
├── Sidebar (navigation)
├── CreatePanel (music generation UI)
├── LibraryView (track browser)
├── TrainingPanel (LoRA training UI)
├── StemSplittingPanel (Demucs UI)
├── VoiceCloningPanel (XTTS UI)
├── MidiPanel (basic-pitch UI)
├── Player (audio playback)
└── RightSidebar (queue/info)
```

#### View Management
- Single `currentView` state determines which panel is visible
- Views: `'create'`, `'library'`, `'training'`, `'stem-splitting'`, `'voice-cloning'`, `'midi'`
- Responsive design with mobile/desktop layouts

## AI/ML Specific Guidelines

### Model Integration
- **Check for bundled execution**: Set `TORCH_JIT=0` to disable JIT in frozen apps
- **MPS optimization**: Use `torch.device("mps")` for Apple Silicon
- **Memory management**: Implement cleanup with `torch.mps.empty_cache()`
- **Model paths**: Use `cdmf_paths.py` functions for consistent path resolution

### Audio Processing
- **Format handling**: Support MP3, WAV, FLAC via pydub/librosa
- **Normalization**: Apply consistent audio normalization across pipelines
- **Sample rates**: Be aware of model-specific sample rate requirements (e.g., ACE-Step uses 24kHz)
- **Stem separation**: Use audio-separator or Demucs depending on use case

### Training
- **LoRA training**: Focus on lightweight adapter training, not full model fine-tuning
- **Dataset structure**: Require `_prompt.txt` and `_lyrics.txt` files alongside audio
- **Checkpointing**: Save periodic checkpoints to prevent data loss
- **PyTorch Lightning**: Use Lightning for training orchestration

## Testing Guidelines

### Backend Testing
- Test files in `tests/` directory
- Use pytest for test execution
- Test API endpoints with sample requests
- Mock heavy ML operations for unit tests
- Integration tests should use small, fast models when possible

### Shell Script Tests
- Prefix test scripts with `test_` (e.g., `test_generation_simple.sh`)
- Test bundled app functionality separately (`test_bundled_app.sh`)
- Include cleanup in tests (remove generated files)

### CI/CD Testing
- GitHub Actions workflows in `.github/workflows/`
- Test on macOS runners only (Apple Silicon specific)
- Workflows:
  - `build-release.yml` - Build and release macOS app
  - `macos-tests.yml` - Run test suite
  - `test-ace-generation.yml` - Test music generation
  - `installation-test.yml` - Verify installation process

## Security Considerations

### API Security
- Validate user inputs before processing
- Sanitize file paths using `secure_filename()` or path validation
- Limit file upload sizes for audio/model files
- Validate audio file formats before processing

### Model Security
- Verify model checksums when downloading (if implemented)
- Sandbox model execution when possible
- Limit resource usage (memory, disk) for user operations

### Local-First Privacy
- No telemetry or analytics
- No external API calls except for model downloads
- All processing happens locally
- Clear documentation of data handling

## Performance Optimization

### Apple Silicon (MPS) Optimization
- Use MPS backend for PyTorch when available
- Set `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` to prevent OOM
- Monitor unified memory usage
- Implement progressive processing for long audio files

### Memory Management
- Clear GPU/unified memory after heavy operations
- Use streaming for large audio files when possible
- Implement max clip duration limits in training
- Provide user controls for memory-intensive operations

### UI Performance
- Lazy load components and data
- Debounce API calls for search/filter operations
- Use virtual scrolling for large track lists
- Optimize audio player with proper buffering

## Platform-Specific Guidelines

### macOS Specific
- **MPS Support**: Leverage Metal Performance Shaders for GPU acceleration
- **Code Signing**: Support both ad-hoc and Developer ID signing
- **App Bundle**: Handle PyInstaller frozen app considerations
- **Gatekeeper**: Document workarounds for non-notarized apps
- **File Paths**: Use `pathlib.Path` for cross-platform compatibility

### Frozen App Considerations
- **Resource Access**: Use `sys._MEIPASS` for bundled resources
- **TorchScript**: Disable JIT compilation (`TORCH_JIT=0`)
- **TTS Models**: Handle TOS agreements programmatically
- **Module Inspection**: Avoid `inspect.getsource()` in frozen apps

## Documentation Standards

### Code Comments
- Explain **why**, not **what** (code should be self-documenting for "what")
- Document ML/audio processing algorithms with references
- Add TODO comments with issue numbers when applicable
- Mark experimental features clearly

### User Documentation
- **README.md**: High-level overview and quick start
- **USAGE.md**: Detailed user guide with examples
- **UIDEV.md**: UI development guide
- **Build docs**: In `build/macos/README.md`

### API Documentation
- Document Flask endpoints with expected inputs/outputs
- Include example requests and responses
- Document error codes and messages
- Keep API versioning in mind for future compatibility

## Common Pitfalls to Avoid

### Backend
- ❌ Don't load all models at startup (lazy loading only)
- ❌ Don't process very long audio without chunking
- ❌ Don't assume `mps` backend is always available
- ❌ Don't hard-code paths (use `cdmf_paths.py`)
- ❌ Don't use blocking operations in Flask routes (use background threads)

### Frontend
- ❌ Don't store large data in component state
- ❌ Don't make API calls in render functions
- ❌ Don't forget to clean up intervals/timeouts
- ❌ Don't hardcode backend URL (use relative paths or config)
- ❌ Don't ignore mobile/responsive design

### General
- ❌ Don't commit model files to git (use .gitignore)
- ❌ Don't include secrets or API keys
- ❌ Don't ignore cross-platform path handling
- ❌ Don't skip error handling in ML/audio pipelines

## Contribution Workflow

When suggesting code changes:

1. **Understand context**: Review related files and recent changes
2. **Minimal changes**: Prefer small, focused modifications
3. **Test implications**: Consider what tests might be affected
4. **Documentation**: Update docs if changing user-facing behavior
5. **Platform compatibility**: Ensure changes work on macOS with Apple Silicon
6. **Performance**: Consider memory and compute implications for ML operations

## Review Guidelines

When reviewing code:

1. **Functionality**: Does it solve the intended problem?
2. **Performance**: Is it efficient for the target hardware (Apple Silicon)?
3. **Memory**: Does it handle large models/audio files safely?
4. **Error handling**: Are edge cases handled gracefully?
5. **Testing**: Can this be tested? Are tests included?
6. **Documentation**: Is it clear how to use this feature?
7. **Security**: Are inputs validated and sanitized?
8. **Maintainability**: Is the code readable and well-structured?

## Example Code Patterns

### Backend: Creating a new feature blueprint

```python
from __future__ import annotations
from typing import Dict, Any
import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

def create_feature_blueprint() -> Blueprint:
    """Create blueprint for new feature."""
    bp = Blueprint("feature_name", __name__)
    
    @bp.route("/api/feature", methods=["POST"])
    def handle_feature():
        try:
            # Validate input
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided"}), 400
            
            # Process
            result = process_feature(data)
            
            # Return success
            return jsonify({"status": "success", "result": result}), 200
            
        except Exception as e:
            logger.error(f"[Feature] Error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    return bp
```

### Frontend: Creating a new panel component

```typescript
import React, { useState, useEffect } from 'react';
import { featureApi } from '../services/api';

interface FeaturePanelProps {
  onComplete?: (result: any) => void;
}

export function FeaturePanel({ onComplete }: FeaturePanelProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setIsProcessing(true);
    setError(null);
    
    try {
      const result = await featureApi.process({
        // ... parameters
      });
      onComplete?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="feature-panel">
      {/* UI elements */}
      {error && <div className="error">{error}</div>}
    </div>
  );
}
```

## Quick Reference

### Important Files
- `music_forge_ui.py` - Main Flask application entry point
- `aceforge_app.py` - PyInstaller bundled app launcher
- `cdmf_paths.py` - Path management and configuration
- `cdmf_state.py` - Global state for models and training
- `ui/App.tsx` - Main React application
- `ui/services/api.ts` - API client functions

### Key Commands
- `./run_local.sh` - Run from source (development)
- `./build_local.sh` - Build macOS app bundle
- `./build_and_test_local.sh` - Build and run tests
- `cd ui && bun run build` - Build frontend only

### Environment Variables
- `TORCH_JIT=0` - Disable JIT (required for frozen apps)
- `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` - MPS memory management
- `COQUI_TOS_AGREED=1` - Skip TTS TOS prompt
- `HF_HUB_DISABLE_SYMLINKS=1` - Disable symlinks for models

---

**Remember**: AceForge is designed for musicians and audio professionals who value local processing and privacy. Keep the user experience smooth, the code maintainable, and the documentation clear.
