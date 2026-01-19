#!/bin/bash
# ---------------------------------------------------------------------------
#  AceForge - Terminal Launcher Wrapper
#  This script opens Terminal.app and runs the launch_in_terminal.sh script
#  This is the actual executable that gets placed as "AceForge" in MacOS/
#  
#  The wrapper stays alive to keep the app visible in the dock, and monitors
#  the actual server process to exit gracefully when it's done.
# ---------------------------------------------------------------------------

# Get the directory where this script lives (Contents/MacOS/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCH_SCRIPT="${SCRIPT_DIR}/launch_in_terminal.sh"

# Configuration for process monitoring
PROCESS_NAME="AceForge_bin"
POLL_INTERVAL=3  # seconds between process checks
STARTUP_TIMEOUT=10  # seconds to wait for process to start (enough for PyInstaller bootloader + Python initialization)

# Check if launch script exists
if [ ! -f "$LAUNCH_SCRIPT" ]; then
    echo "Error: launch_in_terminal.sh not found at $LAUNCH_SCRIPT"
    exit 1
fi

# Create a marker file to track if we launched the Terminal
MARKER_FILE="/tmp/aceforge_launcher_$$"
touch "$MARKER_FILE"

# Cleanup function to remove marker file on exit
cleanup() {
    rm -f "$MARKER_FILE"
}
trap cleanup EXIT

# Launch Terminal with our script using AppleScript
osascript <<EOF
tell application "Terminal"
    do script "cd $(printf %q "$SCRIPT_DIR") && exec './launch_in_terminal.sh'"
    activate
end tell
EOF

# Give the process a moment to start
sleep 2

# Keep this process alive to maintain app visibility in the dock
# We monitor the server process and exit when it's done
while [ -f "$MARKER_FILE" ]; do
    # Check if the server process is running
    if pgrep -f "$PROCESS_NAME" > /dev/null 2>&1; then
        # Process is running, continue waiting
        sleep $POLL_INTERVAL
    else
        # Process not found - check if it's still starting up or has finished
        # Wait a bit longer to distinguish between "not started yet" and "finished"
        sleep $POLL_INTERVAL
        if ! pgrep -f "$PROCESS_NAME" > /dev/null 2>&1; then
            # Still not running after grace period - it likely finished or failed
            # Check if we've been running long enough for startup
            if [ $SECONDS -gt $STARTUP_TIMEOUT ]; then
                # We've been running long enough, process has ended
                break
            fi
        fi
    fi
done

exit 0
