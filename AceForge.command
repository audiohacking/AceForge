#!/bin/bash
# AceForge.command - Double-click this file to launch AceForge in Terminal
# This file should be placed next to AceForge.app

# Get the directory where this script lives
cd "$(dirname "$0")" || exit 1

# Check if AceForge.app exists
if [ ! -d "AceForge.app" ]; then
    echo "Error: AceForge.app not found in this directory"
    echo "Make sure this file is in the same folder as AceForge.app"
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
fi

# Run the launcher script from inside the app bundle
exec "./AceForge.app/Contents/MacOS/launch_in_terminal.sh"
