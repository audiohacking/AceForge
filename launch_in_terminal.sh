#!/bin/bash
# ---------------------------------------------------------------------------
#  AceForge - Backend Server Runner
#  This script runs the AceForge backend in a Terminal window
# ---------------------------------------------------------------------------

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Determine if we're in an app bundle or source directory
if [[ "$SCRIPT_DIR" == *"/Contents/MacOS"* ]]; then
    # Running from app bundle
    EXEC_PATH="${SCRIPT_DIR}/AceForge"
else
    # This shouldn't happen for bundled app, but handle it anyway
    EXEC_PATH="${SCRIPT_DIR}/AceForge"
fi

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🎵 AceForge - AI Music Generation Server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Starting AceForge server..."
echo ""
echo "📋 Instructions:"
echo "  • Your browser will open automatically when the server is ready"
echo "  • To stop AceForge: Press Ctrl+C or use the 'Exit' button in browser"
echo "  • This terminal window MUST stay open while using AceForge"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run the AceForge executable
"$EXEC_PATH"

# Capture exit status
EXIT_CODE=$?

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ✅ AceForge stopped gracefully"
else
    echo "  ⚠️  AceForge exited with code: $EXIT_CODE"
fi
echo ""
echo "  You can now close this window"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Keep window open so user can see the message
read -n 1 -s -r -p "Press any key to close this window..."
echo ""
