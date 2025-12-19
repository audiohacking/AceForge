# macOS Port Documentation

This document describes the macOS port of AceForge and provides guidance for maintaining and updating this fork.

## Overview

This fork of CDMF is optimized exclusively for macOS with Apple Metal (MPS) GPU acceleration. It supports both Apple Silicon (M1/M2/M3) and Intel Macs with compatible AMD GPUs.

## Key Changes from Original

### 1. Device Selection and GPU Acceleration

**File: `cdmf_pipeline_ace_step.py`**

The device selection logic now properly supports MPS (Metal Performance Shaders):

```python
device = (
    torch.device(f"cuda:{device_id}")
    if torch.cuda.is_available()
    else torch.device("cpu")
)
if device.type == "cpu" and torch.backends.mps.is_available():
    device = torch.device("mps")
```

**Data type handling for MPS:**
- MPS doesn't support `bfloat16`, so we automatically use `float16` or `float32`
- Users can override via `ACE_PIPELINE_DTYPE` environment variable

**Memory management:**
- Added MPS cache clearing: `torch.mps.empty_cache()`
- Maintains CUDA logic for reference when porting updates

### 2. Backend Configuration

**File: `cdmf_pipeline_ace_step.py` (lines 53-58)**

CUDA-specific backend settings are now conditional:

```python
# Configure CUDA backends if available
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = True
torch.set_float32_matmul_precision("high")
```

### 3. Training with Device-Agnostic Autocast

**File: `cdmf_trainer.py`**

The hardcoded `device_type="cuda"` in autocast has been replaced with dynamic device detection:

```python
# Use device-agnostic autocast - get device type from tensor device
device_type = device.type if device.type in ["cuda", "cpu", "mps"] else "cpu"
with torch.amp.autocast(device_type=device_type, dtype=dtype):
    # training code...
```

### 4. Dependencies

**Files:**
- `requirements_ace_macos.txt` - macOS dependencies (default)
- `requirements_ace_windows_reference.txt` - Original Windows deps (reference only)

**Removed packages:**
- `pywin32-ctypes==0.2.3` - Windows-specific
- `win32_setctime==1.2.0` - Windows-specific

**PyTorch installation:**
- Uses standard PyPI index (no CUDA-specific wheels)
- Includes native MPS support: `torch==2.4.0`, `torchvision==0.19.0`, `torchaudio==2.4.0`

### 5. Launcher Script

**Files:**
- `CDMF.sh` - macOS launcher (primary)
- `CDMF.bat` - Windows launcher (reference only)

The bash script handles:
- Python version detection (requires 3.10+)
- Virtual environment creation
- Dependency installation
- Browser opening with macOS `open` command
- Proper error handling

### 6. UI and Browser Opening

**File: `music_forge_ui.py`**

Simplified browser opening logic for macOS:
- Removed `os.startfile()` (Windows-only)
- Uses `webbrowser.open()` for all cases
- Cleaner, more maintainable code

## Porting Updates from Upstream

When merging changes from the original Windows version:

### 1. Identify Changed Files

```bash
# Compare with upstream
git remote add upstream <original-repo-url>
git fetch upstream
git diff upstream/main HEAD
```

### 2. Focus on Core Logic

Priority files to merge:
- Model and pipeline logic
- UI and generation features  
- Dataset and training functionality
- Bug fixes and improvements

### 3. Adapt Device-Specific Code

When you see CUDA-specific code:

**Before (upstream):**
```python
torch.backends.cudnn.benchmark = False
with torch.amp.autocast(device_type="cuda"):
    # code
```

**After (macOS fork):**
```python
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = False
device_type = device.type if device.type in ["cuda", "cpu", "mps"] else "cpu"
with torch.amp.autocast(device_type=device_type):
    # code
```

### 4. Update Dependencies Carefully

When upstream updates `requirements_ace.txt`:

1. Review changes in `requirements_ace_windows_reference.txt`
2. Apply non-Windows-specific changes to `requirements_ace_macos.txt`
3. Skip any CUDA-specific wheel URLs
4. Test thoroughly with MPS backend

### 5. Testing Checklist

After porting updates:

- [ ] Run syntax check: `python -m py_compile *.py`
- [ ] Test device selection: Verify MPS is selected on macOS
- [ ] Test generation: Create a short audio sample
- [ ] Test training: Verify LoRA training works
- [ ] Run CI workflows: Check GitHub Actions pass
- [ ] Memory management: Verify no memory leaks
- [ ] Browser opening: Test launcher script

## Common Issues and Solutions

### Issue: MPS Operations Not Supported

Some PyTorch operations may not be implemented for MPS yet.

**Solution:**
- Operations will automatically fall back to CPU
- Monitor performance and consider optimizations
- Check PyTorch release notes for MPS updates

### Issue: Data Type Errors with MPS

MPS has different precision support than CUDA.

**Solution:**
```bash
# Set environment variable
export ACE_PIPELINE_DTYPE=float32
./CDMF.sh
```

### Issue: Memory Management

Unified memory on Apple Silicon behaves differently than discrete GPU VRAM.

**Solution:**
- Start with conservative memory settings
- Gradually increase based on your Mac's configuration
- Use Activity Monitor to watch memory pressure

## Performance Optimization

### Apple Silicon Specific

1. **Unified Memory**: Leverage efficient CPU-GPU memory sharing
2. **Batch Sizes**: Start small, increase incrementally
3. **Precision**: Use float32 for stability, float16 for speed (when supported)
4. **Generation Length**: Scale up gradually based on memory

### Monitoring

```bash
# Watch memory usage
watch -n 1 'ps aux | grep python'

# Monitor GPU activity (macOS Ventura+)
sudo powermetrics --samplers gpu_power -i 1000
```

## CI/CD Workflows

### macOS Tests (`macos-tests.yml`)

Tests:
- Dependency installation
- PyTorch MPS availability
- Import checks
- Syntax validation
- Device selection logic

### Installation Test (`installation-test.yml`)

Tests:
- Script executability
- Bash syntax
- Requirements file presence
- Python version detection

## File Structure Reference

```
CDMF-Fork/
├── CDMF.sh                              # macOS launcher (PRIMARY)
├── CDMF.bat                             # Windows launcher (REFERENCE)
├── requirements_ace_macos.txt           # macOS deps (DEFAULT)
├── requirements_ace_windows_reference.txt  # Windows deps (REFERENCE)
├── cdmf_pipeline_ace_step.py           # Device selection & MPS support
├── cdmf_trainer.py                      # Training with device-agnostic autocast
├── music_forge_ui.py                    # UI with macOS browser opening
├── .github/workflows/
│   ├── macos-tests.yml                  # Main test workflow
│   └── installation-test.yml            # Installation validation
└── MACOS_PORT.md                        # This file
```

## Support and Contributing

- Test on both Apple Silicon and Intel Macs when possible
- Document MPS-specific issues and workarounds
- Keep upstream references for future porting
- Maintain CI workflows for automated testing

## Resources

- [PyTorch MPS Backend](https://pytorch.org/docs/stable/notes/mps.html)
- [Apple Metal Performance Shaders](https://developer.apple.com/metal/pytorch/)
- [Original CDMF Repository](https://github.com/original-repo-link)
- [ACE-Step Model](https://github.com/ace-step/ACE-Step)
