#!/bin/bash
# ---------------------------------------------------------------------------
# Test Bundled App Generation Locally
# 
# This script builds the macOS app bundle and tests generation using
# the actual frozen binary. This catches all PyInstaller bundling issues
# at once instead of discovering them one by one.
#
# Usage:
#   ./test_bundled_app.sh
# ---------------------------------------------------------------------------

set -e  # Exit on error

echo "=================================================="
echo "AceForge - Bundled App Generation Test"
echo "=================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "CDMF.spec" ]; then
    echo "Error: CDMF.spec not found. Please run this script from the project root."
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.11 or later."
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "Python: $PYTHON_VERSION"
echo ""

# Step 1: Check dependencies
echo "Step 1: Checking dependencies..."
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "⚠ PyInstaller not found."
    echo ""
    echo "Please install PyInstaller first:"
    echo "  pip3 install pyinstaller==6.17.0"
    echo ""
    echo "Or if you're using a virtual environment:"
    echo "  source venv_ace/bin/activate"
    echo "  pip install pyinstaller==6.17.0"
    echo ""
    exit 1
else
    PYINSTALLER_VERSION=$(python3 -c "import PyInstaller; print(PyInstaller.__version__)" 2>/dev/null || echo "unknown")
    echo "✓ PyInstaller found (version: $PYINSTALLER_VERSION)"
fi

# Step 2: Build the app bundle
echo ""
echo "Step 2: Building app bundle with PyInstaller..."
if [ -d "dist/AceForge.app" ]; then
    echo "Removing existing build..."
    rm -rf dist/AceForge.app
fi

pyinstaller CDMF.spec

if [ ! -d "dist/AceForge.app" ]; then
    echo "✗ Build failed: dist/AceForge.app not found"
    exit 1
fi

echo "✓ App bundle built successfully"
echo ""

# Step 3: Add launcher scripts
echo "Step 3: Setting up launcher scripts..."
cp launch_in_terminal.sh dist/AceForge.app/Contents/MacOS/
chmod +x dist/AceForge.app/Contents/MacOS/launch_in_terminal.sh

cp macos_terminal_launcher.sh dist/AceForge.app/Contents/MacOS/AceForge
chmod +x dist/AceForge.app/Contents/MacOS/AceForge

echo "✓ Launcher scripts configured"
echo ""

# Step 4: Code sign (optional, but recommended)
echo "Step 4: Code signing app bundle..."
if [ -f "build/macos/codesign.sh" ]; then
    chmod +x build/macos/codesign.sh
    MACOS_SIGNING_IDENTITY="-" ./build/macos/codesign.sh dist/AceForge.app
    echo "✓ App bundle signed"
else
    echo "⚠ Code signing script not found, skipping..."
fi
echo ""

# Step 5: Test imports
echo "Step 5: Testing bundled app imports..."
BUNDLED_BIN="./dist/AceForge.app/Contents/MacOS/AceForge_bin"

if [ ! -f "$BUNDLED_BIN" ]; then
    echo "✗ Bundled binary not found at $BUNDLED_BIN"
    exit 1
fi

echo "Testing critical imports..."
"$BUNDLED_BIN" -c "
import sys
print('Python version:', sys.version)
print('Frozen:', getattr(sys, 'frozen', False))

errors = []

try:
    import lzma
    import _lzma
    print('✓ lzma imported successfully')
except Exception as e:
    print(f'✗ lzma import failed: {e}')
    errors.append(('lzma', str(e)))

try:
    from acestep.models.lyrics_utils.lyric_tokenizer import VoiceBpeTokenizer
    print('✓ VoiceBpeTokenizer imported successfully')
except Exception as e:
    print(f'✗ VoiceBpeTokenizer import failed: {e}')
    errors.append(('VoiceBpeTokenizer', str(e)))

try:
    from cdmf_pipeline_ace_step import ACEStepPipeline
    print('✓ ACEStepPipeline imported successfully')
except Exception as e:
    print(f'✗ ACEStepPipeline import failed: {e}')
    errors.append(('ACEStepPipeline', str(e)))

if errors:
    print('')
    print('✗ Import errors detected:')
    for module, error in errors:
        print(f'  - {module}: {error}')
    sys.exit(1)

print('✓ All critical imports successful')
" || {
    echo ""
    echo "✗ Import test failed"
    exit 1
}

echo ""

# Step 6: Test generation (if models are available)
echo "Step 6: Testing generation with bundled app..."
echo "Note: This requires ACE-Step models to be downloaded."
echo "      Run 'python ace_model_setup.py' first if needed."
echo ""

# Check if models exist
MODELS_EXIST=false
if python3 -c "from ace_model_setup import get_ace_checkpoint_root, ACE_LOCAL_DIRNAME; from pathlib import Path; root = get_ace_checkpoint_root(); repo = root / ACE_LOCAL_DIRNAME; exit(0 if repo.exists() else 1)" 2>/dev/null; then
    MODELS_EXIST=true
    echo "✓ Models found, proceeding with generation test..."
else
    echo "⚠ Models not found. Skipping generation test."
    echo "  To test generation, run: python ace_model_setup.py"
    echo ""
    echo "✓ Bundled app import test PASSED"
    echo "  (Generation test skipped - models not available)"
    exit 0
fi

# Create test script
cat > test_bundled_generation.py << 'TESTSCRIPT'
import sys
import os
from pathlib import Path

# Set environment
os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'] = '0.0'

print("=" * 60)
print("Bundled App Generation Test")
print("=" * 60)
print(f"Python executable: {sys.executable}")
print(f"Frozen: {getattr(sys, 'frozen', False)}")
print("=" * 60)

try:
    from generate_ace import generate_track_ace
    print("✓ generate_track_ace imported successfully")
except Exception as e:
    print(f"✗ Failed to import generate_track_ace: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("")
print("Starting generation test (10 seconds, 5 steps)...")
try:
    result = generate_track_ace(
        genre_prompt="upbeat electronic music, synthwave",
        instrumental=True,
        target_seconds=10,
        steps=5,
        guidance_scale=4.0,
        seed=42,
        out_dir=Path("test_output_bundled"),
        basename="local_test_bundled_track"
    )
    
    print("")
    print("✓ Generation completed successfully")
    
    output_dir = Path("test_output_bundled")
    wav_files = list(output_dir.glob("*.wav"))
    if not wav_files:
        print(f"✗ No WAV files found in {output_dir}")
        sys.exit(1)
    
    for wav_file in wav_files:
        size = wav_file.stat().st_size
        print(f"✓ Generated file: {wav_file.name} ({size:,} bytes)")
        if size == 0:
            print(f"✗ File is empty: {wav_file.name}")
            sys.exit(1)
    
    print("")
    print("=" * 60)
    print("✓ Bundled app generation test PASSED")
    print("=" * 60)
        
except Exception as e:
    print("")
    print("=" * 60)
    print("✗ Generation failed")
    print("=" * 60)
    print(f"Error: {e}")
    print("")
    import traceback
    traceback.print_exc()
    sys.exit(1)
TESTSCRIPT

# Run generation test
"$BUNDLED_BIN" test_bundled_generation.py || {
    echo ""
    echo "✗ Generation test failed"
    echo "Check the error messages above to identify the issue."
    rm -f test_bundled_generation.py
    exit 1
}

# Cleanup
rm -f test_bundled_generation.py

echo ""
echo "=================================================="
echo "✓ All tests PASSED"
echo "=================================================="
echo ""
echo "The bundled app is working correctly!"
echo "You can find it at: dist/AceForge.app"
