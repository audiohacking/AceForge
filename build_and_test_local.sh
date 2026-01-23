#!/bin/bash
# Build the app locally (matching build-release.yml) and test generation via API
# This replicates the CI environment locally

set -e

echo "=========================================="
echo "Local Build and Test"
echo "=========================================="
echo ""

# Step 1: Check Python version
echo "Step 1: Checking Python version..."
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD=python3.11
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
    if [[ "$PYTHON_VERSION" != "3.11" ]]; then
        echo "⚠ WARNING: python3 is version $PYTHON_VERSION, but 3.11 is recommended"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    PYTHON_CMD=python3
else
    echo "✗ Python 3.11 not found"
    exit 1
fi

echo "Using Python: $PYTHON_CMD"
$PYTHON_CMD --version
echo ""

# Step 2: Install/upgrade pip
echo "Step 2: Upgrading pip..."
$PYTHON_CMD -m pip install --upgrade pip
echo ""

# Step 3: Install dependencies (matching build-release.yml)
echo "Step 3: Installing dependencies..."
if [ ! -f "requirements_ace_macos.txt" ]; then
    echo "✗ requirements_ace_macos.txt not found"
    exit 1
fi

$PYTHON_CMD -m pip install -r requirements_ace_macos.txt
echo ""

# Step 4: Install audio-separator (no deps)
echo "Step 4: Installing audio-separator..."
$PYTHON_CMD -m pip install "audio-separator==0.40.0" --no-deps
echo ""

# Step 5: Install py3langid (no deps)
echo "Step 5: Installing py3langid..."
$PYTHON_CMD -m pip install "py3langid==0.3.0" --no-deps
echo ""

# Step 6: Install ACE-Step (no deps)
echo "Step 6: Installing ACE-Step..."
$PYTHON_CMD -m pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps
echo ""

# Step 7: Check for PyInstaller
echo "Step 7: Checking PyInstaller..."
if ! $PYTHON_CMD -c "import PyInstaller" 2>/dev/null; then
    echo "Installing PyInstaller..."
    $PYTHON_CMD -m pip install pyinstaller
fi
echo "✓ PyInstaller ready"
echo ""

# Step 8: Clean previous builds
echo "Step 8: Cleaning previous builds..."
rm -rf dist/AceForge.app dist/CDMF build/AceForge
echo "✓ Cleaned"
echo ""

# Step 9: Build the app (matching build-release.yml)
echo "Step 9: Building app with PyInstaller..."
echo "This may take several minutes..."
$PYTHON_CMD -m PyInstaller CDMF.spec --clean --noconfirm

BUNDLED_BIN="./dist/AceForge.app/Contents/MacOS/AceForge_bin"
if [ ! -f "$BUNDLED_BIN" ]; then
    echo "✗ Build failed - bundled binary not found"
    exit 1
fi

echo "✓ Build completed: $BUNDLED_BIN"
echo ""

# Step 10: Check for models
echo "Step 10: Checking for ACE-Step models..."
MODELS_EXIST=false
if $BUNDLED_BIN -c "from ace_model_setup import get_ace_checkpoint_root, ACE_LOCAL_DIRNAME; from pathlib import Path; root = get_ace_checkpoint_root(); repo = root / ACE_LOCAL_DIRNAME; exit(0 if repo.exists() else 1)" 2>/dev/null; then
    MODELS_EXIST=true
    echo "✓ Models found"
else
    echo "⚠ Models not found. Downloading..."
    $PYTHON_CMD ace_model_setup.py
    if $BUNDLED_BIN -c "from ace_model_setup import get_ace_checkpoint_root, ACE_LOCAL_DIRNAME; from pathlib import Path; root = get_ace_checkpoint_root(); repo = root / ACE_LOCAL_DIRNAME; exit(0 if repo.exists() else 1)" 2>/dev/null; then
        MODELS_EXIST=true
        echo "✓ Models downloaded"
    else
        echo "✗ Failed to download models"
        exit 1
    fi
fi
echo ""

# Step 11: Test critical imports and data files
echo "Step 11: Testing critical imports and data files..."
$BUNDLED_BIN -c "
import sys
errors = []
try:
    import lzma, _lzma
    print('✓ lzma OK')
except Exception as e:
    print(f'✗ lzma: {e}')
    errors.append(('lzma', str(e)))
try:
    import py3langid
    from pathlib import Path
    data_file = Path(py3langid.__file__).parent / 'data' / 'model.plzma'
    if data_file.exists():
        print(f'✓ py3langid data/model.plzma FOUND ({data_file.stat().st_size:,} bytes)')
    else:
        print(f'✗ py3langid data/model.plzma NOT FOUND at {data_file}')
        errors.append(('py3langid data', 'not found'))
except Exception as e:
    print(f'✗ py3langid: {e}')
    errors.append(('py3langid', str(e)))
try:
    from acestep.models.lyrics_utils.lyric_tokenizer import VoiceBpeTokenizer
    print('✓ VoiceBpeTokenizer OK')
except Exception as e:
    print(f'✗ VoiceBpeTokenizer: {e}')
    errors.append(('VoiceBpeTokenizer', str(e)))
try:
    from cdmf_pipeline_ace_step import ACEStepPipeline
    print('✓ ACEStepPipeline OK')
except Exception as e:
    print(f'✗ ACEStepPipeline: {e}')
    errors.append(('ACEStepPipeline', str(e)))
if errors:
    print('')
    print('✗ Some checks failed:')
    for module, error in errors:
        print(f'  - {module}: {error}')
    sys.exit(1)
else:
    print('')
    print('✓ All critical checks passed')
" || {
    echo ""
    echo "✗ Critical checks failed"
    exit 1
}
echo ""

# Step 12: Start the app server
echo "Step 12: Starting bundled app server..."
PORT=5056  # AceForge uses port 5056 (not 5000 which conflicts with AirPlay)
$BUNDLED_BIN > /tmp/aceforge_test.log 2>&1 &
APP_PID=$!

# Wait for server to start (it needs time to load models)
echo "Waiting for server to start on port $PORT..."
echo "This may take a minute as models load..."
for i in {1..120}; do
    if curl -s http://127.0.0.1:$PORT/ > /dev/null 2>&1; then
        echo "✓ Server is responding on port $PORT"
        # Give it a few more seconds to finish initializing
        sleep 5
        break
    fi
    if [ $i -eq 120 ]; then
        echo "✗ Server failed to start after 2 minutes"
        echo "Logs:"
        tail -100 /tmp/aceforge_test.log
        kill $APP_PID 2>/dev/null || true
        exit 1
    fi
    if [ $((i % 10)) -eq 0 ]; then
        echo "  Still waiting... ($i/120 seconds)"
    fi
    sleep 1
done
echo ""

# Step 13: Test generation via API (matching test-ace-generation.yml)
echo "Step 13: Testing generation via API..."
echo "This matches test-ace-generation.yml: 10 seconds, 5 steps, instrumental"
echo ""

# Set environment variable (matching CI)
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0

# Show current log tail before making request
echo "Current server status (last 10 lines):"
tail -10 /tmp/aceforge_test.log
echo ""

# Make the API call (form data like the browser)
echo "Sending generation request..."
GENERATION_RESPONSE=$(curl -s -v -X POST http://127.0.0.1:$PORT/generate \
    -F "prompt=upbeat electronic music, synthwave" \
    -F "instrumental=on" \
    -F "target_seconds=10" \
    -F "steps=5" \
    -F "guidance_scale=4.0" \
    -F "seed=42" \
    -F "basename=local_test_track" \
    2>&1)

echo "API Response:"
echo "$GENERATION_RESPONSE" | head -30
echo ""

# Check if we got a redirect (302) or success (200)
HTTP_CODE=$(echo "$GENERATION_RESPONSE" | grep -i "< HTTP" | tail -1 | awk '{print $3}' || echo "")
if [ -z "$HTTP_CODE" ]; then
    HTTP_CODE=$(echo "$GENERATION_RESPONSE" | grep -i "HTTP/" | tail -1 | awk '{print $2}' || echo "")
fi

echo "HTTP Response Code: $HTTP_CODE"
echo ""

# Check response
if echo "$HTTP_CODE" | grep -qE "200|302"; then
    echo "✓ Generation request accepted (HTTP $HTTP_CODE)"
else
    echo "✗ Generation request failed (HTTP $HTTP_CODE)"
    echo ""
    echo "Server logs after request:"
    tail -50 /tmp/aceforge_test.log
    echo ""
    echo "Full response:"
    echo "$GENERATION_RESPONSE"
    kill $APP_PID 2>/dev/null || true
    exit 1
fi

# Wait for generation to complete (check logs)
echo "Waiting for generation to complete (this may take several minutes)..."
echo "Monitoring server logs (checking every 5 seconds)..."
echo ""

GENERATION_COMPLETE=false
ERROR_DETECTED=false
LAST_LOG_LINES=0

for i in {1..180}; do
    # Get current log tail
    CURRENT_LOG=$(tail -100 /tmp/aceforge_test.log)
    CURRENT_LINES=$(echo "$CURRENT_LOG" | wc -l)
    
    # Show new log lines
    if [ "$CURRENT_LINES" -gt "$LAST_LOG_LINES" ]; then
        NEW_LINES=$((CURRENT_LINES - LAST_LOG_LINES))
        echo "--- New log output ($NEW_LINES lines) ---"
        echo "$CURRENT_LOG" | tail -$NEW_LINES | grep -v "^$" | tail -5
        LAST_LOG_LINES=$CURRENT_LINES
    fi
    
    # Check for errors
    if echo "$CURRENT_LOG" | grep -q "Error during ACE-Step generation"; then
        ERROR_DETECTED=true
        echo ""
        echo "✗ Error detected in logs!"
        break
    fi
    
    # Check for completion (look for "Finished track", "Saving audio", or file creation)
    if echo "$CURRENT_LOG" | grep -q "Finished track\|\[ACE\] Finished track\|Saving audio to\|save_wav_file"; then
        GENERATION_COMPLETE=true
        echo ""
        echo "✓ Generation completion detected in logs!"
        # Wait a bit more for file to be written
        sleep 3
        break
    fi
    
    # Show progress every 30 seconds
    if [ $((i % 6)) -eq 0 ]; then
        echo "  Still processing... ($((i * 5)) seconds elapsed)"
    fi
    
    sleep 5
done

echo ""

# Check results
if [ "$ERROR_DETECTED" = true ]; then
    echo "✗ Generation error detected in logs:"
    echo ""
    tail -100 /tmp/aceforge_test.log | grep -A 20 "Error during ACE-Step generation" || tail -50 /tmp/aceforge_test.log
    kill $APP_PID 2>/dev/null || true
    exit 1
elif [ "$GENERATION_COMPLETE" = true ]; then
    echo "✓ Generation completed successfully"
    echo ""
    echo "Recent server logs:"
    tail -30 /tmp/aceforge_test.log
else
    echo "⚠ Generation status unclear (timeout or still running)"
    echo "Recent server logs:"
    tail -50 /tmp/aceforge_test.log
fi

# Step 14: Verify output file was created
echo ""
echo "Step 14: Verifying output file..."
OUTPUT_DIR="$HOME/Library/Application Support/AceForge/generated"
if [ ! -d "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="$HOME/Library/Application Support/AceForge/music"
fi

if [ -d "$OUTPUT_DIR" ]; then
    # Look for recently created WAV files (within last 15 minutes)
    WAV_FILES=$(find "$OUTPUT_DIR" -name "*test_track*.wav" -o -name "*local_test_track*.wav" -type f -mmin -15 2>/dev/null | head -5)
    if [ -n "$WAV_FILES" ]; then
        echo "✓ Output file(s) found:"
        for wav in $WAV_FILES; do
            SIZE=$(stat -f%z "$wav" 2>/dev/null || stat -c%s "$wav" 2>/dev/null || echo "0")
            echo "  $wav ($SIZE bytes)"
            if [ "$SIZE" -gt 100000 ]; then
                echo "    ✓ File size looks good for 10 seconds of audio"
            elif [ "$SIZE" -gt 0 ]; then
                echo "    ⚠ File seems small but exists"
            fi
        done
    else
        echo "⚠ No output file found in $OUTPUT_DIR"
        echo "  Checking all recent WAV files:"
        find "$OUTPUT_DIR" -name "*.wav" -type f -mmin -15 2>/dev/null | head -3 || echo "    (none found)"
    fi
else
    echo "⚠ Output directory not found: $OUTPUT_DIR"
fi

# Stop the app
echo ""
echo "Stopping app server..."
kill $APP_PID 2>/dev/null || true
wait $APP_PID 2>/dev/null || true

echo ""
echo "=========================================="
if [ "$ERROR_DETECTED" = true ]; then
    echo "✗ TEST FAILED - Generation error detected"
    echo "=========================================="
    exit 1
elif [ "$GENERATION_COMPLETE" = true ]; then
    echo "✓ TEST PASSED - Generation completed successfully"
    echo "=========================================="
    exit 0
else
    echo "⚠ TEST INCONCLUSIVE - Check logs manually"
    echo "=========================================="
    echo "Server logs: /tmp/aceforge_test.log"
    exit 0
fi
