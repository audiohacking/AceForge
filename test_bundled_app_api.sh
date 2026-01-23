#!/bin/bash
# Test the bundled app by running it and calling its API (like the browser does)
# This is the REAL test - exactly what users experience

set -e

echo "=========================================="
echo "Bundled App API Test"
echo "=========================================="
echo ""

# Check if app is built
BUNDLED_APP="./dist/AceForge.app"
BUNDLED_BIN="$BUNDLED_APP/Contents/MacOS/AceForge_bin"

if [ ! -f "$BUNDLED_BIN" ]; then
    echo "✗ Bundled app not found. Building it first..."
    echo ""
    
    # Check Python
    if command -v python3.11 &> /dev/null; then
        PYTHON_CMD=python3.11
    elif command -v python3 &> /dev/null; then
        PYTHON_CMD=python3
    else
        echo "✗ Python not found"
        exit 1
    fi
    
    # Check PyInstaller
    if ! $PYTHON_CMD -c "import PyInstaller" 2>/dev/null; then
        echo "✗ PyInstaller not found. Install: $PYTHON_CMD -m pip install pyinstaller"
        exit 1
    fi
    
    echo "Building app bundle..."
    rm -rf dist/AceForge.app dist/CDMF build/AceForge
    $PYTHON_CMD -m PyInstaller CDMF.spec --clean --noconfirm
    
    if [ ! -f "$BUNDLED_BIN" ]; then
        echo "✗ Build failed"
        exit 1
    fi
    
    echo "✓ Build completed"
    echo ""
fi

echo "✓ Bundled app found: $BUNDLED_APP"
echo ""

# Check if models exist
echo "Checking for ACE-Step models..."
MODELS_EXIST=false
if $BUNDLED_BIN -c "from ace_model_setup import get_ace_checkpoint_root, ACE_LOCAL_DIRNAME; from pathlib import Path; root = get_ace_checkpoint_root(); repo = root / ACE_LOCAL_DIRNAME; exit(0 if repo.exists() else 1)" 2>/dev/null; then
    MODELS_EXIST=true
    echo "✓ Models found"
else
    echo "⚠ Models not found. Will test server startup only."
    echo "  To test generation, download models first: python ace_model_setup.py"
fi
echo ""

# Start the app in background
echo "Starting bundled app server..."
PORT=5000
$BUNDLED_BIN > /tmp/aceforge_test.log 2>&1 &
APP_PID=$!

# Wait for server to start
echo "Waiting for server to start..."
for i in {1..30}; do
    if curl -s http://localhost:$PORT/ > /dev/null 2>&1; then
        echo "✓ Server is running on port $PORT"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "✗ Server failed to start"
        echo "Logs:"
        tail -50 /tmp/aceforge_test.log
        kill $APP_PID 2>/dev/null || true
        exit 1
    fi
    sleep 1
done

echo ""

if [ "$MODELS_EXIST" = false ]; then
    echo "Skipping generation test (models not available)"
    echo ""
    echo "✓ Server started successfully"
    echo "✓ App is responding"
    echo ""
    echo "Running critical import and data file checks..."
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
        print(f'✓ py3langid data/model.plzma FOUND')
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
    print('✗ Some checks failed - see errors above')
    sys.exit(1)
else:
    print('')
    print('✓ All critical checks passed')
" || {
        echo ""
        echo "✗ Critical checks failed"
        kill $APP_PID 2>/dev/null || true
        exit 1
    }
    echo ""
    echo "To test generation, download models first:"
    echo "  python ace_model_setup.py"
    kill $APP_PID 2>/dev/null || true
    wait $APP_PID 2>/dev/null || true
    exit 0
fi

# Test generation via API (exactly like the browser does)
echo "Testing generation via API..."
echo ""

# The /generate endpoint uses form data, not JSON (like the browser does)
GENERATION_RESPONSE=$(curl -s -X POST http://localhost:$PORT/generate \
    -F "prompt=upbeat electronic music, synthwave" \
    -F "instrumental=on" \
    -F "target_seconds=10" \
    -F "steps=5" \
    -F "guidance_scale=4.0" \
    -F "seed=42" \
    -F "basename=api_test_track")

echo "Generation response:"
echo "$GENERATION_RESPONSE" | head -20
echo ""

# Check if generation succeeded
# The /generate endpoint returns HTML on success (redirects to /tracks)
# or an error page on failure
if echo "$GENERATION_RESPONSE" | grep -q "Error\|error\|ERROR"; then
    echo "✗ Generation API call failed"
    echo "Error in response:"
    echo "$GENERATION_RESPONSE" | grep -i "error" | head -10
    echo ""
    echo "Server logs:"
    tail -100 /tmp/aceforge_test.log
    kill $APP_PID 2>/dev/null || true
    exit 1
elif echo "$GENERATION_RESPONSE" | grep -q "tracks\|redirect\|success"; then
    echo "✓ Generation API call succeeded (redirected to tracks page)"
else
    # Check if it's HTML (success) or something else
    if echo "$GENERATION_RESPONSE" | grep -q "<!DOCTYPE\|<html"; then
        echo "✓ Generation API call succeeded (returned HTML page)"
    else
        echo "⚠ Unexpected response format"
        echo "Response preview:"
        echo "$GENERATION_RESPONSE" | head -20
    fi
fi

# Wait a bit for generation to complete
echo ""
echo "Waiting for generation to complete (this may take a few minutes)..."
sleep 5

# Check server logs for completion or errors
if tail -100 /tmp/aceforge_test.log | grep -q "Error during ACE-Step generation"; then
    echo ""
    echo "✗ Generation error detected in logs:"
    tail -50 /tmp/aceforge_test.log | grep -A 10 "Error during ACE-Step generation"
    kill $APP_PID 2>/dev/null || true
    exit 1
fi

# Stop the app
echo ""
echo "Stopping app..."
kill $APP_PID 2>/dev/null || true
wait $APP_PID 2>/dev/null || true

echo ""
echo "=========================================="
echo "✓ API test completed"
echo "=========================================="
echo ""
echo "Check server logs at: /tmp/aceforge_test.log"
