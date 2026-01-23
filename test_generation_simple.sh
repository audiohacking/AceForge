#!/bin/bash
# Simple test: start server, make API call, monitor logs

BUNDLED_BIN="./dist/AceForge.app/Contents/MacOS/AceForge_bin"
PORT=5056

echo "Starting server..."
$BUNDLED_BIN > /tmp/aceforge_simple.log 2>&1 &
APP_PID=$!

echo "Waiting for server (PID: $APP_PID)..."
for i in {1..60}; do
    if curl -s http://127.0.0.1:$PORT/ > /dev/null 2>&1; then
        echo "✓ Server ready"
        break
    fi
    sleep 1
done

echo ""
echo "Sending generation request..."
curl -X POST http://127.0.0.1:$PORT/generate \
    -F "prompt=upbeat electronic music, synthwave" \
    -F "instrumental=on" \
    -F "target_seconds=10" \
    -F "steps=5" \
    -F "guidance_scale=4.0" \
    -F "seed=42" \
    -F "basename=test_track" \
    -v 2>&1 | head -20

echo ""
echo "Monitoring logs for 60 seconds..."
for i in {1..12}; do
    echo "--- Log check $i (after $((i*5)) seconds) ---"
    tail -20 /tmp/aceforge_simple.log | grep -E "GENERATE|Error|Finished|ACE" || echo "  (no relevant log entries)"
    sleep 5
done

echo ""
echo "Final log tail:"
tail -30 /tmp/aceforge_simple.log

kill $APP_PID 2>/dev/null
