#!/bin/bash
# ---------------------------------------------------------------------------
#  AceForge - Local Build Script
#  Builds the PyInstaller app bundle for local testing
# ---------------------------------------------------------------------------

set -e  # Exit on error

echo "=========================================="
echo "AceForge - Local Build"
echo "=========================================="
echo ""

# App root = folder this script lives in
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

# Check Python version
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
    if [[ "$PYTHON_VERSION" == "3.11" ]]; then
        PYTHON_CMD="python3"
    else
        echo "WARNING: python3 is version $PYTHON_VERSION, but 3.11 is recommended"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
        PYTHON_CMD="python3"
    fi
else
    echo "ERROR: Python 3.11 not found. Please install Python 3.11."
    exit 1
fi

echo "[Build] Using Python: $($PYTHON_CMD --version)"
echo ""

# Virtual environment
VENV_DIR="${APP_DIR}/venv_build"
VENV_PY="${VENV_DIR}/bin/python"

# Create/activate virtual environment
if [ ! -f "$VENV_PY" ]; then
    echo "[Build] Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

echo "[Build] Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

# Upgrade pip
echo "[Build] Upgrading pip..."
$PYTHON_CMD -m pip install --upgrade pip --quiet

# Install dependencies
echo "[Build] Installing dependencies..."
$PYTHON_CMD -m pip install -r requirements_ace_macos.txt --quiet

# Install additional dependencies
echo "[Build] Installing additional dependencies..."
$PYTHON_CMD -m pip install "audio-separator==0.40.0" --no-deps --quiet
$PYTHON_CMD -m pip install "py3langid==0.3.0" --no-deps --quiet
$PYTHON_CMD -m pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps --quiet
$PYTHON_CMD -m pip install "rotary_embedding_torch" --quiet
$PYTHON_CMD -m pip install "pyinstaller>=6.0" --quiet

# Check for PyInstaller
if ! $PYTHON_CMD -m PyInstaller --version &> /dev/null; then
    echo "ERROR: PyInstaller not found. Please install it:"
    echo "  $PYTHON_CMD -m pip install pyinstaller"
    exit 1
fi

echo "[Build] PyInstaller version: $($PYTHON_CMD -m PyInstaller --version)"
echo ""

# Clean previous builds
echo "[Build] Cleaning previous builds..."
rm -rf dist/AceForge.app dist/CDMF build/AceForge

# Build with PyInstaller
echo "[Build] Building app bundle with PyInstaller..."
echo "This may take several minutes..."
$PYTHON_CMD -m PyInstaller CDMF.spec --clean --noconfirm

# Check if build succeeded
BUNDLED_APP="${APP_DIR}/dist/AceForge.app"
BUNDLED_BIN="${BUNDLED_APP}/Contents/MacOS/AceForge_bin"

if [ ! -f "$BUNDLED_BIN" ]; then
    echo ""
    echo "ERROR: Build failed - binary not found at: $BUNDLED_BIN"
    exit 1
fi

# For serverless pywebview app, we don't need launcher scripts
# The binary (AceForge_bin) should be the main executable
# Rename it to AceForge for cleaner app bundle structure
echo ""
echo "[Build] Setting up app bundle executable..."
if [ -f "${BUNDLED_BIN}" ]; then
    # Create a symlink or copy so the app can be launched as "AceForge"
    # The Info.plist CFBundleExecutable should point to "AceForge"
    if [ ! -f "${BUNDLED_APP}/Contents/MacOS/AceForge" ]; then
        cp "${BUNDLED_BIN}" "${BUNDLED_APP}/Contents/MacOS/AceForge"
        chmod +x "${BUNDLED_APP}/Contents/MacOS/AceForge"
    fi
fi

# Code sign the app bundle (critical for macOS - must be LAST step)
echo ""
echo "[Build] Code signing app bundle..."
if [ -f "${APP_DIR}/build/macos/codesign.sh" ]; then
    chmod +x "${APP_DIR}/build/macos/codesign.sh"
    MACOS_SIGNING_IDENTITY="-" "${APP_DIR}/build/macos/codesign.sh" "$BUNDLED_APP"
    if [ $? -eq 0 ]; then
        echo "[Build] ✓ Code signing completed"
        
        # Remove quarantine attributes (allows app to run without Gatekeeper blocking)
        echo "[Build] Removing quarantine attributes..."
        xattr -cr "$BUNDLED_APP" 2>/dev/null || true
        
        # Verify the signature
        echo "[Build] Verifying code signature..."
        if codesign --verify --deep --strict --verbose=2 "$BUNDLED_APP" &> /dev/null; then
            echo "[Build] ✓ Code signature verified"
        else
            echo "[Build] ⚠ Code signature verification had warnings"
        fi
    else
        echo "[Build] ⚠ Code signing had warnings, but continuing..."
    fi
else
    echo "[Build] ⚠ WARNING: codesign.sh not found, skipping code signing"
    echo "[Build]   App may show security warnings when launched"
fi

echo ""
echo "=========================================="
echo "✓ Build successful!"
echo "=========================================="
echo ""
echo "App bundle: $BUNDLED_APP"
echo "Binary: $BUNDLED_BIN"
echo ""
echo "⚠ IMPORTANT: macOS Gatekeeper may block adhoc-signed apps"
echo "   If you see 'app is damaged' warning:"
echo "   1. Right-click the app → Open (bypasses Gatekeeper)"
echo "   2. Or run: xattr -cr \"$BUNDLED_APP\""
echo ""
echo "To test the app:"
echo "  1. Check for ACE-Step models:"
echo "     python ace_model_setup.py"
echo ""
echo "  2. Run the app (right-click → Open if blocked):"
echo "     open \"$BUNDLED_APP\""
echo ""
echo "  3. Or run directly:"
echo "     \"$BUNDLED_BIN\""
echo ""
