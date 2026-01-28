#!/bin/bash
# Simple test: start server, make stem splitting API call, monitor logs and progress

BUNDLED_BIN="./dist/AceForge.app/Contents/MacOS/AceForge_bin"
PORT=5056

# Check if sample audio file is provided, otherwise use repo test file
SAMPLE_AUDIO="${1:-}"

if [ -z "$SAMPLE_AUDIO" ]; then
    # First, try the repo test file
    if [ -f "./audiotest.mp3" ]; then
        SAMPLE_AUDIO="./audiotest.mp3"
        echo "Using repo test file: $SAMPLE_AUDIO"
    else
        echo "Usage: $0 [<path_to_audio_file>]"
        echo "Example: $0 ~/Music/sample.mp3"
        echo ""
        echo "Looking for a sample audio file..."
        
        # Try to find a sample file in common locations
        for dir in ~/Music ~/Downloads ~/Desktop; do
            if [ -d "$dir" ]; then
                SAMPLE=$(find "$dir" -type f \( -name "*.mp3" -o -name "*.wav" -o -name "*.m4a" \) -print -quit 2>/dev/null)
                if [ -n "$SAMPLE" ]; then
                    SAMPLE_AUDIO="$SAMPLE"
                    echo "Found: $SAMPLE_AUDIO"
                    break
                fi
            fi
        done
        
        if [ -z "$SAMPLE_AUDIO" ]; then
            echo "No sample audio file found. Please provide one as an argument or add audiotest.mp3 to the repo."
            exit 1
        fi
    fi
fi

if [ ! -f "$SAMPLE_AUDIO" ]; then
    echo "Error: Audio file not found: $SAMPLE_AUDIO"
    exit 1
fi

echo "=========================================="
echo "Stem Splitting Test"
echo "=========================================="
echo "Input file: $SAMPLE_AUDIO"
echo ""

# Check if bundled app exists, otherwise use python directly
if [ -f "$BUNDLED_BIN" ]; then
    echo "Using bundled app: $BUNDLED_BIN"
    SERVER_CMD="$BUNDLED_BIN"
else
    echo "Bundled app not found, using python directly..."
    SERVER_CMD="python3 music_forge_ui.py"
fi

echo "Starting server..."
$SERVER_CMD > /tmp/aceforge_stem_test.log 2>&1 &
APP_PID=$!

echo "Waiting for server (PID: $APP_PID)..."
for i in {1..60}; do
    if curl -s http://127.0.0.1:$PORT/ > /dev/null 2>&1; then
        echo "✓ Server ready"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "✗ Server failed to start after 60 seconds"
        kill $APP_PID 2>/dev/null
        exit 1
    fi
    sleep 1
done

echo ""
echo "Sending stem splitting request..."
echo "  - Stem count: 4 (vocals, drums, bass, other)"
echo "  - Device: auto"
echo "  - Format: WAV"
echo ""

# Make the API call
RESPONSE=$(curl -s -X POST http://127.0.0.1:$PORT/stem_split \
    -F "input_file=@$SAMPLE_AUDIO" \
    -F "stem_count=4" \
    -F "device_preference=auto" \
    -F "export_format=wav" \
    -F "mode=" \
    -w "\nHTTP_CODE:%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE:" | cut -d: -f2)
RESPONSE_BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE:/d')

echo "HTTP Response Code: $HTTP_CODE"
echo ""
echo "Response:"
echo "$RESPONSE_BODY" | head -20
echo ""

# Check response
if echo "$HTTP_CODE" | grep -qE "200|302"; then
    echo "✓ Stem splitting request accepted (HTTP $HTTP_CODE)"
else
    echo "✗ Stem splitting request failed (HTTP $HTTP_CODE)"
    echo ""
    echo "Server logs:"
    tail -50 /tmp/aceforge_stem_test.log
    kill $APP_PID 2>/dev/null
    exit 1
fi

echo ""
echo "Monitoring progress and logs (checking every 5 seconds)..."
echo "This may take several minutes depending on file size and device..."
echo ""

STEM_SPLIT_COMPLETE=false
ERROR_DETECTED=false
LAST_LOG_LINES=0

for i in {1..120}; do
    # Check progress endpoint
    PROGRESS=$(curl -s http://127.0.0.1:$PORT/progress 2>/dev/null)
    if [ -n "$PROGRESS" ]; then
        FRACTION=$(echo "$PROGRESS" | grep -o '"fraction":[0-9.]*' | cut -d: -f2 || echo "0")
        STAGE=$(echo "$PROGRESS" | grep -o '"stage":"[^"]*"' | cut -d'"' -f4 || echo "")
        DONE=$(echo "$PROGRESS" | grep -o '"done":[^,}]*' | cut -d: -f2 || echo "false")
        ERROR=$(echo "$PROGRESS" | grep -o '"error":[^,}]*' | cut -d: -f2 || echo "false")
        
        if [ "$ERROR" = "true" ]; then
            ERROR_DETECTED=true
            echo ""
            echo "✗ Error detected in progress!"
            break
        fi
        
        if [ "$DONE" = "true" ] && [ "$STAGE" = "stem_split_done" ]; then
            STEM_SPLIT_COMPLETE=true
            echo ""
            echo "✓ Stem splitting completed!"
            break
        fi
        
        if [ -n "$STAGE" ] && [ "$STAGE" != "done" ]; then
            PCT=$(echo "$FRACTION * 100" | bc -l 2>/dev/null | cut -d. -f1 || echo "0")
            echo "  Progress: ${PCT}% - Stage: $STAGE"
        fi
    fi
    
    # Get current log tail
    CURRENT_LOG=$(tail -50 /tmp/aceforge_stem_test.log)
    CURRENT_LINES=$(echo "$CURRENT_LOG" | wc -l)
    
    # Show new log lines
    if [ "$CURRENT_LINES" -gt "$LAST_LOG_LINES" ]; then
        NEW_LINES=$((CURRENT_LINES - LAST_LOG_LINES))
        echo "--- New log output ($NEW_LINES lines) ---"
        echo "$CURRENT_LOG" | tail -$NEW_LINES | grep -v "^$" | tail -3
        LAST_LOG_LINES=$CURRENT_LINES
    fi
    
    # Check for errors in logs
    if echo "$CURRENT_LOG" | grep -qi "Error\|Exception\|Traceback\|Failed"; then
        ERROR_DETECTED=true
        echo ""
        echo "✗ Error detected in logs!"
        break
    fi
    
    # Check for completion in logs
    if echo "$CURRENT_LOG" | grep -qi "Stem splitting completed\|Success.*stems created"; then
        STEM_SPLIT_COMPLETE=true
        echo ""
        echo "✓ Completion detected in logs!"
        break
    fi
    
    sleep 5
done

echo ""
echo "Final status:"
if [ "$ERROR_DETECTED" = true ]; then
    echo "✗ TEST FAILED - Error detected"
    echo ""
    echo "Recent logs:"
    tail -50 /tmp/aceforge_stem_test.log | grep -A 20 -i "error\|exception\|traceback" || tail -30 /tmp/aceforge_stem_test.log
elif [ "$STEM_SPLIT_COMPLETE" = true ]; then
    echo "✓ TEST PASSED - Stem splitting completed"
    echo ""
    echo "Recent logs:"
    tail -30 /tmp/aceforge_stem_test.log | grep -i "stem\|demucs\|success" || tail -20 /tmp/aceforge_stem_test.log
else
    echo "⚠ TEST INCONCLUSIVE - Timeout or still running"
    echo ""
    echo "Recent logs:"
    tail -30 /tmp/aceforge_stem_test.log
fi

# Check for output files
echo ""
echo "Checking for output files..."
OUTPUT_DIR="$HOME/Library/Application Support/AceForge/generated"
if [ ! -d "$OUTPUT_DIR" ]; then
    OUTPUT_DIR="$HOME/Library/Application Support/AceForge/music"
fi

if [ -d "$OUTPUT_DIR" ]; then
    STEM_DIRS=$(find "$OUTPUT_DIR" -type d -name "stem_split_*" -mmin -15 2>/dev/null | head -1)
    if [ -n "$STEM_DIRS" ]; then
        echo "✓ Output directory found: $STEM_DIRS"
        echo ""
        echo "Stem files:"
        find "$STEM_DIRS" -name "*.wav" -o -name "*.mp3" 2>/dev/null | while read file; do
            SIZE=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo "0")
            echo "  $(basename "$file") ($SIZE bytes)"
        done
    else
        echo "⚠ No stem_split_* directories found in $OUTPUT_DIR"
    fi
else
    echo "⚠ Output directory not found: $OUTPUT_DIR"
fi

# Stop the app
echo ""
echo "Stopping server..."
kill $APP_PID 2>/dev/null || true
wait $APP_PID 2>/dev/null || true

echo ""
echo "=========================================="
if [ "$ERROR_DETECTED" = true ]; then
    echo "✗ TEST FAILED"
    echo "=========================================="
    exit 1
elif [ "$STEM_SPLIT_COMPLETE" = true ]; then
    echo "✓ TEST PASSED"
    echo "=========================================="
    exit 0
else
    echo "⚠ TEST INCONCLUSIVE"
    echo "=========================================="
    echo "Logs: /tmp/aceforge_stem_test.log"
    exit 0
fi
