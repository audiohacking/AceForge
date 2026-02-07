# Packaging Python Apps as Native macOS Applications

**A Complete Guide to Turning Python Apps into Stand-Alone macOS Applications**

This document captures the complete method used by AceForge to package Python applications with PyWebView and PyInstaller, create native macOS .app bundles with custom icons, package them as DMG files, and apply code signing to make them distributable. This guide is intended as a reference for packaging other Python projects using the same techniques.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Step-by-Step Guide](#step-by-step-guide)
   - [Step 1: Application Entry Point](#step-1-application-entry-point)
   - [Step 2: PyInstaller Spec File](#step-2-pyinstaller-spec-file)
   - [Step 3: Icon Creation](#step-3-icon-creation)
   - [Step 4: PyInstaller Hooks](#step-4-pyinstaller-hooks)
   - [Step 5: Build Script](#step-5-build-script)
   - [Step 6: Code Signing](#step-6-code-signing)
   - [Step 7: DMG Creation](#step-7-dmg-creation)
   - [Step 8: CI/CD Integration](#step-8-cicd-integration)
5. [Advanced Topics](#advanced-topics)
6. [Troubleshooting](#troubleshooting)
7. [References](#references)

---

## Overview

This packaging method produces **native macOS applications** from Python code that:
- Launch without requiring a terminal window
- Have custom application icons
- Run without Python installation on the target system
- Avoid "app is damaged" security warnings through code signing
- Can be distributed as DMG disk images or ZIP archives
- Include all dependencies (Python runtime, libraries, data files)
- Support optional UI frameworks (Flask + PyWebView for native windows)

### Key Technologies

- **PyInstaller**: Bundles Python app and all dependencies into a standalone executable
- **PyWebView**: Creates native macOS windows (uses WebKit under the hood)
- **Flask**: Provides local web server for the UI (optional - any Python app works)
- **Code Signing**: Prevents macOS security warnings
- **DMG Creation**: Standard macOS distribution format

---

## Prerequisites

### Required Tools

1. **macOS**: Version 12.0 (Monterey) or later recommended
2. **Python 3.11**: Exact version recommended for consistency
3. **PyInstaller**: Version 6.0 or later
4. **Xcode Command Line Tools**: For code signing
   ```bash
   xcode-select --install
   ```

### Optional Tools

- **Bun**: For building modern web UIs (if your app has a web interface)
- **Apple Developer ID**: For distribution outside the App Store (optional for local builds)

---

## Architecture

### Application Structure

```
YourPythonApp/
├── your_app.py                 # Main entry point
├── your_app.spec               # PyInstaller spec file
├── build/
│   └── macos/
│       ├── YourApp.icns        # macOS icon file
│       ├── YourApp.iconset/    # Source PNG icons (multiple sizes)
│       ├── codesign.sh         # Code signing script
│       ├── entitlements.plist  # Security entitlements
│       ├── README.md           # Build documentation
│       └── pyinstaller_hooks/  # Custom PyInstaller hooks
│           └── hook-*.py       # Package-specific hooks
├── build_local.sh              # Local build script
├── requirements.txt            # Python dependencies
└── .github/
    └── workflows/
        └── build-release.yml   # CI/CD workflow
```

### Build Flow

```
Source Code → PyInstaller → .app Bundle → Code Sign → DMG/ZIP → Distribution
```

1. **Source Preparation**: Organize code, resources, and dependencies
2. **PyInstaller Bundling**: Create standalone .app with all dependencies
3. **Binary Setup**: Configure CFBundleExecutable for native launch
4. **Code Signing**: Sign all binaries and the app bundle
5. **Packaging**: Create DMG with app, symlinks, and documentation
6. **Distribution**: Upload to GitHub releases or other channels

---

## Step-by-Step Guide

### Step 1: Application Entry Point

Create a main Python file that serves as the entry point for your frozen application.

**Key Considerations:**

1. **Prevent Multiple Execution**: Guard against module re-execution
2. **Set Environment Variables Early**: Before importing heavy dependencies
3. **Handle Frozen vs. Development Mode**: Detect if running as PyInstaller bundle
4. **Native Window Integration**: Use PyWebView for GUI apps

**Example Entry Point** (`your_app.py`):

```python
#!/usr/bin/env python3
"""
YourApp - Native macOS Application
"""

import sys
import os
from pathlib import Path

# Prevent multiple execution (critical for frozen apps)
if hasattr(sys.modules.get(__name__, None), '_app_executed'):
    print("CRITICAL: Entry point is being re-executed! Exiting.", flush=True)
    sys.exit(1)
sys.modules[__name__]._app_executed = True

# Set environment variables early (before importing torch, etc.)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")

# Detect if running as PyInstaller bundle
def is_frozen():
    """Check if running as PyInstaller frozen app"""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

def get_bundle_dir():
    """Get the base directory of the bundle"""
    if is_frozen():
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return Path(sys._MEIPASS)
    return Path(__file__).parent

# For PyWebView applications
def main():
    """Main entry point"""
    import webview
    from your_flask_app import create_app
    
    # Create Flask app
    app = create_app()
    
    # Start Flask in a background thread
    import threading
    flask_thread = threading.Thread(
        target=lambda: app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    
    # Create native window
    webview.create_window(
        title='Your App Name',
        url='http://127.0.0.1:5000',
        width=1200,
        height=800,
        resizable=True
    )
    
    # Start webview (blocks until window closes)
    webview.start()

if __name__ == '__main__':
    main()
```

**For Non-GUI Applications:**

```python
#!/usr/bin/env python3
"""
CLI or background service application
"""

import sys
import os

def main():
    """Main entry point"""
    # Your application logic here
    print("Hello from frozen app!")
    
if __name__ == '__main__':
    main()
```

---

### Step 2: PyInstaller Spec File

The `.spec` file is the heart of the PyInstaller build process. It defines what gets included, how the app is structured, and macOS-specific settings.

**Create Your Spec File** (`YourApp.spec`):

```python
# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for YourApp (macOS)
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

block_cipher = None

# Determine paths
spec_root = Path(SPECPATH)
icon_path = spec_root / 'build' / 'macos' / 'YourApp.icns'
static_dir = spec_root / 'static'  # If you have static web files

# Collect dynamic libraries for packages with C extensions
# Example: collecting binaries for packages that have native extensions
_lzma_binaries = []
try:
    _lzma_binaries = collect_dynamic_libs('_lzma')
    if _lzma_binaries:
        print(f"[Spec] Collected _lzma binaries: {len(_lzma_binaries)} files")
except Exception as e:
    print(f"[Spec] WARNING: collect_dynamic_libs('_lzma') failed: {e}")

# Collect data files for packages that need them
_package_data = []
try:
    _package_data = collect_data_files('your_package')
    if _package_data:
        print(f"[Spec] Collected package data: {len(_package_data)} files")
except Exception as e:
    print(f"[Spec] WARNING: collect_data_files('your_package') failed: {e}")

a = Analysis(
    ['your_app.py'],  # Entry point
    pathex=[],
    binaries=_lzma_binaries + [
        # Add additional binaries here if needed
    ],
    datas=[
        # Include static files, configs, etc.
        (str(static_dir), 'static'),  # (source, destination_in_bundle)
        ('config.json', '.'),
        ('VERSION', '.'),
    ] + _package_data,
    hiddenimports=[
        # Packages that PyInstaller might miss
        'your_package',
        'your_package.submodule',
        # Collect all submodules for critical packages
        *collect_submodules('some_complex_package'),
        # Common hidden imports
        'flask',
        'waitress',
        'webview',
    ],
    hookspath=['build/macos/pyinstaller_hooks'],  # Custom hooks directory
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude large packages you don't need to reduce bundle size
        'matplotlib',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YourApp_bin',  # Internal binary name
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to False to hide terminal window (GUI apps)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YourApp',
)

# macOS app bundle
app = BUNDLE(
    coll,
    name='YourApp.app',
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier='com.yourcompany.yourapp',  # Unique identifier
    info_plist={
        'CFBundleName': 'YourApp',
        'CFBundleDisplayName': 'Your App Display Name',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,  # Support Retina displays
        'LSMinimumSystemVersion': '12.0',  # Minimum macOS version
        'NSRequiresAquaSystemAppearance': False,  # Support dark mode
        'LSUIElement': False,  # Show in dock (True = menu bar app only)
        'LSBackgroundOnly': False,  # Run in foreground
        'CFBundlePackageType': 'APPL',
        'NSAppTransportSecurity': {
            'NSAllowsLocalNetworking': True,  # Allow localhost (for Flask)
        },
        'CFBundleExecutable': 'YourApp',  # Must match the binary name after copying
    },
)
```

**Key Sections Explained:**

1. **Analysis**: Discovers all code, data, and binary dependencies
   - `binaries`: Native libraries (.dylib, .so files)
   - `datas`: Data files, configs, static assets
   - `hiddenimports`: Modules PyInstaller can't auto-detect
   - `hookspath`: Custom hooks for problematic packages

2. **EXE**: Creates the executable binary
   - `console=False`: Hides terminal window for GUI apps
   - `name='YourApp_bin'`: Internal name (will be renamed)

3. **BUNDLE**: Creates the macOS .app structure
   - `icon`: Path to .icns file
   - `bundle_identifier`: Reverse-DNS style unique ID
   - `info_plist`: macOS app metadata

---

### Step 3: Icon Creation

macOS apps require icons in multiple resolutions packaged as an `.icns` file.

#### A. Create Source Images

Create a square PNG image in the highest resolution you need (1024x1024 recommended).

#### B. Create iconset Directory

```bash
mkdir -p build/macos/YourApp.iconset
```

#### C. Generate All Required Sizes

Using ImageMagick, Photoshop, or any image editor, create these exact files in the iconset:

```
YourApp.iconset/
├── icon_16x16.png       # 16x16
├── icon_16x16@2x.png    # 32x32 (Retina)
├── icon_32x32.png       # 32x32
├── icon_32x32@2x.png    # 64x64 (Retina)
├── icon_128x128.png     # 128x128
├── icon_128x128@2x.png  # 256x256 (Retina)
├── icon_256x256.png     # 256x256
├── icon_256x256@2x.png  # 512x512 (Retina)
├── icon_512x512.png     # 512x512
└── icon_512x512@2x.png  # 1024x1024 (Retina)
```

**Automated Icon Generation with ImageMagick:**

```bash
#!/bin/bash
# generate_icons.sh - Generate macOS icon set from a single source image

SOURCE_IMAGE="logo.png"  # Your source image (1024x1024 recommended)
ICONSET="build/macos/YourApp.iconset"

mkdir -p "$ICONSET"

# Generate all required sizes
sips -z 16 16     "$SOURCE_IMAGE" --out "${ICONSET}/icon_16x16.png"
sips -z 32 32     "$SOURCE_IMAGE" --out "${ICONSET}/icon_16x16@2x.png"
sips -z 32 32     "$SOURCE_IMAGE" --out "${ICONSET}/icon_32x32.png"
sips -z 64 64     "$SOURCE_IMAGE" --out "${ICONSET}/icon_32x32@2x.png"
sips -z 128 128   "$SOURCE_IMAGE" --out "${ICONSET}/icon_128x128.png"
sips -z 256 256   "$SOURCE_IMAGE" --out "${ICONSET}/icon_128x128@2x.png"
sips -z 256 256   "$SOURCE_IMAGE" --out "${ICONSET}/icon_256x256.png"
sips -z 512 512   "$SOURCE_IMAGE" --out "${ICONSET}/icon_256x256@2x.png"
sips -z 512 512   "$SOURCE_IMAGE" --out "${ICONSET}/icon_512x512.png"
sips -z 1024 1024 "$SOURCE_IMAGE" --out "${ICONSET}/icon_512x512@2x.png"
```

#### D. Convert iconset to .icns

```bash
iconutil -c icns build/macos/YourApp.iconset -o build/macos/YourApp.icns
```

This creates `YourApp.icns` which PyInstaller will embed in your app bundle.

---

### Step 4: PyInstaller Hooks

Custom hooks help PyInstaller correctly bundle packages with special requirements.

Create `build/macos/pyinstaller_hooks/` directory for your custom hooks.

**Example Hook for a Package with Data Files** (`hook-your_package.py`):

```python
"""
PyInstaller hook for your_package.
Ensures data files are properly bundled in frozen apps.
"""
from PyInstaller.utils.hooks import collect_data_files

# Collect all data files from the package
datas = collect_data_files('your_package')

# Explicitly add a critical file if needed
try:
    import your_package
    from pathlib import Path
    pkg_path = Path(your_package.__file__).parent
    critical_file = pkg_path / 'data' / 'model.bin'
    if critical_file.exists():
        datas.append((str(critical_file), 'your_package/data'))
except Exception:
    pass
```

**Example Hook for Binary Extensions** (`hook-lzma.py`):

```python
"""
PyInstaller hook for lzma module.
Ensures the _lzma C extension is available in frozen apps.
"""

# Import early to ensure it's available
try:
    import lzma
    import _lzma
except ImportError:
    pass
```

**Common Hooks Needed:**

- Packages with C extensions (numpy, scipy, etc.)
- Packages with data files (models, configs, etc.)
- Packages using pkg_resources or importlib.resources
- Web frameworks with templates/static files

---

### Step 5: Build Script

Create an automated build script that handles the complete build process.

**`build_local.sh`**:

```bash
#!/bin/bash
# YourApp - Local Build Script for macOS
set -e

echo "=========================================="
echo "YourApp - macOS Build"
echo "=========================================="

# App root directory
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

# Check Python version
PYTHON_CMD=""
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "ERROR: Python 3 not found"
    exit 1
fi

echo "Using Python: $($PYTHON_CMD --version)"

# Create virtual environment
VENV_DIR="${APP_DIR}/venv_build"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"
PY="${VENV_DIR}/bin/python"

# Install dependencies
echo "Installing dependencies..."
"$PY" -m pip install --upgrade pip --quiet
"$PY" -m pip install -r requirements.txt --quiet
"$PY" -m pip install "pyinstaller>=6.0" --quiet

# Verify icon exists
if [ ! -f "build/macos/YourApp.icns" ]; then
    echo "ERROR: build/macos/YourApp.icns not found"
    echo "Run: iconutil -c icns build/macos/YourApp.iconset"
    exit 1
fi

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist/YourApp.app dist/YourApp build/YourApp

# Build with PyInstaller
echo "Building with PyInstaller..."
"$PY" -m PyInstaller YourApp.spec --clean --noconfirm

# Check if build succeeded
BUNDLED_APP="${APP_DIR}/dist/YourApp.app"
BUNDLED_BIN="${BUNDLED_APP}/Contents/MacOS/YourApp_bin"

if [ ! -f "$BUNDLED_BIN" ]; then
    echo "ERROR: Build failed - binary not found"
    exit 1
fi

# Set up executable
echo "Setting up app bundle executable..."
cp "${BUNDLED_BIN}" "${BUNDLED_APP}/Contents/MacOS/YourApp"
chmod +x "${BUNDLED_APP}/Contents/MacOS/YourApp"

# Code sign the app
echo "Code signing app bundle..."
if [ -f "${APP_DIR}/build/macos/codesign.sh" ]; then
    chmod +x "${APP_DIR}/build/macos/codesign.sh"
    MACOS_SIGNING_IDENTITY="-" "${APP_DIR}/build/macos/codesign.sh" "$BUNDLED_APP"
fi

# Remove quarantine attributes
xattr -cr "$BUNDLED_APP" 2>/dev/null || true

echo ""
echo "=========================================="
echo "✓ Build successful!"
echo "=========================================="
echo "App: $BUNDLED_APP"
echo ""
echo "To run: open \"$BUNDLED_APP\""
```

Make it executable:

```bash
chmod +x build_local.sh
```

#### Optional: UI Build Script

If your application has a web-based UI (React, Vue, etc.), create a separate script to build it.

**`scripts/build_ui.sh`**:

```bash
#!/usr/bin/env bash
# Build the web UI (React/Vite) for your app
# Output: ui/dist/
# Run from repo root. Requires Bun or npm.

set -e

# Get script and repo directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_DIR="$REPO_ROOT/ui"

echo "=========================================="
echo "Building Web UI"
echo "=========================================="

# Verify UI source exists
if [ ! -f "$UI_DIR/package.json" ]; then
  echo "ERROR: ui/package.json not found."
  echo "Ensure UI source is in ui/ directory"
  exit 1
fi

# Check for Bun (fast modern bundler)
if command -v bun &> /dev/null; then
  echo "Using Bun to build UI..."
  cd "$UI_DIR"
  bun install --frozen-lockfile 2>/dev/null || bun install
  bun run build
# Fallback to npm
elif command -v npm &> /dev/null; then
  echo "Using npm to build UI..."
  cd "$UI_DIR"
  npm install
  npm run build
else
  echo "ERROR: Neither Bun nor npm found."
  echo "Install Bun: https://bun.sh"
  echo "Or install Node.js: https://nodejs.org"
  exit 1
fi

# Verify build output
if [ ! -f "$UI_DIR/dist/index.html" ]; then
  echo "ERROR: UI build did not produce ui/dist/index.html"
  exit 1
fi

echo ""
echo "✓ UI build successful: $UI_DIR/dist/"
```

Make it executable:

```bash
chmod +x scripts/build_ui.sh
```

**Usage in build_local.sh:**

```bash
# Add this to build_local.sh before PyInstaller step
if [ -d "ui" ] && [ -f "scripts/build_ui.sh" ]; then
    echo "Building web UI..."
    ./scripts/build_ui.sh
fi
```

#### Complete Local Release Build Script

For testing the full release build process locally (including DMG/ZIP creation), create a script that replicates the GitHub Actions workflow:

**`build_release_local.sh`**:

```bash
#!/bin/bash
# ---------------------------------------------------------------------------
#  Complete Local Release Build Script
#  Replicates the GitHub Actions build-release.yml workflow locally
#  Creates .app bundle, DMG, and ZIP for distribution testing
# ---------------------------------------------------------------------------

set -e  # Exit on error

echo "=========================================="
echo "Local Release Build"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
APP_NAME="YourApp"
VERSION="${VERSION:-$(cat VERSION 2>/dev/null || echo '1.0.0-local')}"
PYTHON_VERSION="3.11"

echo "App: $APP_NAME"
echo "Version: $VERSION"
echo ""

# ---------------------------------------------------------------------------
# 1. Set up Python environment
# ---------------------------------------------------------------------------
echo "=== Step 1: Python Environment ==="

PYTHON_CMD=""
if command -v python${PYTHON_VERSION} &> /dev/null; then
    PYTHON_CMD="python${PYTHON_VERSION}"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "ERROR: Python 3 not found"
    exit 1
fi

echo "Using: $($PYTHON_CMD --version)"

# Create/activate virtual environment
VENV_DIR="${SCRIPT_DIR}/venv_release"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

source "${VENV_DIR}/bin/activate"
PY="${VENV_DIR}/bin/python"

echo "✓ Python environment ready"
echo ""

# ---------------------------------------------------------------------------
# 2. Build UI (if present)
# ---------------------------------------------------------------------------
echo "=== Step 2: Build UI ==="

if [ -f "ui/package.json" ]; then
    if command -v bun &> /dev/null; then
        echo "Building UI with Bun..."
        ./scripts/build_ui.sh
    else
        echo "WARNING: Bun not found, skipping UI build"
        echo "Install from: https://bun.sh"
    fi
else
    echo "No UI to build"
fi

echo "✓ UI build complete"
echo ""

# ---------------------------------------------------------------------------
# 3. Install Dependencies
# ---------------------------------------------------------------------------
echo "=== Step 3: Install Dependencies ==="

"$PY" -m pip install --upgrade pip --quiet
echo "Installing base requirements..."
"$PY" -m pip install -r requirements.txt --quiet

# Install additional dependencies (adjust for your project)
echo "Installing additional dependencies..."
"$PY" -m pip install "pyinstaller>=6.0" --quiet

# Optional: Install app-specific dependencies
# "$PY" -m pip install "audio-separator==0.40.0" --no-deps --quiet
# "$PY" -m pip install "TTS==0.21.2" --quiet

echo "✓ Dependencies installed"
echo ""

# ---------------------------------------------------------------------------
# 4. Verify Build Assets
# ---------------------------------------------------------------------------
echo "=== Step 4: Verify Build Assets ==="

if [ ! -f "build/macos/${APP_NAME}.icns" ]; then
    echo "ERROR: build/macos/${APP_NAME}.icns not found"
    exit 1
fi

if [ ! -f "build/macos/codesign.sh" ]; then
    echo "ERROR: build/macos/codesign.sh not found"
    exit 1
fi

echo "✓ Build assets verified"
echo ""

# ---------------------------------------------------------------------------
# 5. Clean Previous Builds
# ---------------------------------------------------------------------------
echo "=== Step 5: Clean Previous Builds ==="

rm -rf "dist/${APP_NAME}.app" "dist/${APP_NAME}" "build/${APP_NAME}"
rm -f "${APP_NAME}-macOS.dmg" "${APP_NAME}-macOS.zip" checksums.txt

echo "✓ Previous builds cleaned"
echo ""

# ---------------------------------------------------------------------------
# 6. Build with PyInstaller
# ---------------------------------------------------------------------------
echo "=== Step 6: Build with PyInstaller ==="

"$PY" -m PyInstaller "${APP_NAME}.spec" --clean --noconfirm

# Verify build succeeded
BUNDLED_APP="dist/${APP_NAME}.app"
BUNDLED_BIN="${BUNDLED_APP}/Contents/MacOS/${APP_NAME}_bin"

if [ ! -f "$BUNDLED_BIN" ]; then
    echo "ERROR: Build failed - binary not found at: $BUNDLED_BIN"
    exit 1
fi

echo "✓ PyInstaller build complete"
echo ""

# ---------------------------------------------------------------------------
# 7. Set Up App Bundle Executable
# ---------------------------------------------------------------------------
echo "=== Step 7: Set Up App Bundle ==="

# Copy binary to expected location (CFBundleExecutable name)
cp "${BUNDLED_BIN}" "${BUNDLED_APP}/Contents/MacOS/${APP_NAME}"
chmod +x "${BUNDLED_APP}/Contents/MacOS/${APP_NAME}"

echo "✓ App bundle configured"
echo ""

# ---------------------------------------------------------------------------
# 8. Code Sign the App
# ---------------------------------------------------------------------------
echo "=== Step 8: Code Sign App Bundle ==="

chmod +x build/macos/codesign.sh

# Use ad-hoc signing by default (no certificate required)
# Set MACOS_SIGNING_IDENTITY environment variable for Developer ID
export MACOS_SIGNING_IDENTITY="${MACOS_SIGNING_IDENTITY:--}"

./build/macos/codesign.sh "$BUNDLED_APP"

# Remove quarantine attributes
xattr -cr "$BUNDLED_APP" 2>/dev/null || true

echo "✓ Code signing complete"
echo ""

# ---------------------------------------------------------------------------
# 9. Create DMG (Disk Image)
# ---------------------------------------------------------------------------
echo "=== Step 9: Create DMG ==="

DMG_TEMP="dmg_temp"
DMG_NAME="${APP_NAME}-${VERSION}-macOS.dmg"

# Clean and create temp directory
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"

# Copy app to DMG temp
cp -R "$BUNDLED_APP" "$DMG_TEMP/"

# Optional: Copy launcher script if it exists
if [ -f "${APP_NAME}.command" ]; then
    cp "${APP_NAME}.command" "$DMG_TEMP/"
    chmod +x "$DMG_TEMP/${APP_NAME}.command"
fi

# Create Applications symlink
ln -s /Applications "$DMG_TEMP/Applications"

# Create README
cat > "$DMG_TEMP/README.txt" << EOF
${APP_NAME} - macOS Edition
==========================

Installation:
1. Drag ${APP_NAME}.app to your Applications folder
2. Double-click to launch
3. On first launch, you may need to right-click → Open

Version: ${VERSION}

For more information, visit:
https://github.com/yourcompany/yourapp
EOF

# Create DMG
echo "Creating DMG: $DMG_NAME"
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$DMG_TEMP" \
    -ov \
    -format UDZO \
    "$DMG_NAME"

# Clean up temp directory
rm -rf "$DMG_TEMP"

echo "✓ DMG created: $DMG_NAME"
echo ""

# ---------------------------------------------------------------------------
# 10. Create ZIP Archive
# ---------------------------------------------------------------------------
echo "=== Step 10: Create ZIP Archive ==="

ZIP_NAME="${APP_NAME}-${VERSION}-macOS.zip"

cd dist
zip -r "../$ZIP_NAME" "${APP_NAME}.app" --quiet
cd ..

echo "✓ ZIP created: $ZIP_NAME"
echo ""

# ---------------------------------------------------------------------------
# 11. Calculate Checksums
# ---------------------------------------------------------------------------
echo "=== Step 11: Calculate Checksums ==="

shasum -a 256 "$DMG_NAME" > checksums.txt
shasum -a 256 "$ZIP_NAME" >> checksums.txt

echo "Checksums:"
cat checksums.txt

echo ""
echo "✓ Checksums calculated"
echo ""

# ---------------------------------------------------------------------------
# Build Complete
# ---------------------------------------------------------------------------
echo "=========================================="
echo "✓ Release Build Complete!"
echo "=========================================="
echo ""
echo "Artifacts created:"
echo "  • App Bundle: $BUNDLED_APP"
echo "  • DMG:        $DMG_NAME"
echo "  • ZIP:        $ZIP_NAME"
echo "  • Checksums:  checksums.txt"
echo ""
echo "Size information:"
ls -lh "$DMG_NAME" "$ZIP_NAME" | awk '{print "  " $9 ": " $5}'
echo ""
echo "To test the DMG:"
echo "  1. Open: $DMG_NAME"
echo "  2. Drag ${APP_NAME}.app to Applications"
echo "  3. Launch from Applications folder"
echo ""
echo "To test the app directly:"
echo "  open \"$BUNDLED_APP\""
echo ""
```

Make it executable:

```bash
chmod +x build_release_local.sh
```

**Usage:**

```bash
# Basic build
./build_release_local.sh

# With custom version
VERSION="v1.2.3" ./build_release_local.sh

# With Developer ID signing (requires certificate)
MACOS_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAM123)" \
    ./build_release_local.sh
```

**What This Script Does:**

This script replicates the complete GitHub Actions workflow locally:

1. ✅ Sets up Python environment with venv
2. ✅ Builds web UI (if present)
3. ✅ Installs all dependencies
4. ✅ Verifies build assets (icon, codesign script)
5. ✅ Cleans previous builds
6. ✅ Builds app with PyInstaller
7. ✅ Sets up app bundle executable
8. ✅ Code signs the app bundle
9. ✅ Creates DMG disk image with Applications symlink
10. ✅ Creates ZIP archive
11. ✅ Calculates SHA256 checksums

**Output:**

After running, you'll have:
- `dist/YourApp.app` - The application bundle
- `YourApp-1.0.0-macOS.dmg` - DMG for distribution
- `YourApp-1.0.0-macOS.zip` - ZIP for distribution
- `checksums.txt` - SHA256 checksums

This allows you to test the complete release process locally before pushing changes that trigger CI/CD.

---

### Step 6: Code Signing

Code signing prevents macOS from showing "app is damaged" warnings and is required for distribution.

#### A. Create Entitlements File

**`build/macos/entitlements.plist`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Disable App Sandbox for development -->
    <key>com.apple.security.app-sandbox</key>
    <false/>
    
    <!-- Network access (if your app uses network) -->
    <key>com.apple.security.network.server</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
    
    <!-- File system access -->
    <key>com.apple.security.files.user-selected.read-write</key>
    <true/>
    <key>com.apple.security.files.downloads.read-write</key>
    <true/>
    
    <!-- Allow unsigned code execution (Python, PyTorch, etc.) -->
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key>
    <true/>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
    
    <!-- JIT compilation (if using ML frameworks) -->
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
</dict>
</plist>
```

#### B. Create Code Signing Script

**`build/macos/codesign.sh`**:

```bash
#!/bin/bash
# Code signing script for macOS applications
set -euo pipefail

# Configuration
APP_PATH="${1:-dist/YourApp.app}"
SIGNING_IDENTITY="${MACOS_SIGNING_IDENTITY:--}"  # Default to ad-hoc ("-")
ENTITLEMENTS_PATH="build/macos/entitlements.plist"

echo "=================================================="
echo "macOS Code Signing"
echo "=================================================="
echo "App: $APP_PATH"
echo "Identity: $SIGNING_IDENTITY"
echo "Entitlements: $ENTITLEMENTS_PATH"
echo ""

# Verify app exists
if [ ! -d "$APP_PATH" ]; then
    echo "Error: App bundle not found at $APP_PATH"
    exit 1
fi

# Verify entitlements exist
if [ ! -f "$ENTITLEMENTS_PATH" ]; then
    echo "Error: Entitlements file not found at $ENTITLEMENTS_PATH"
    exit 1
fi

# Function to sign a binary
sign_binary() {
    local target="$1"
    echo "Signing: $target"
    
    # Build codesign command
    local cmd=(
        xcrun codesign
        --sign "$SIGNING_IDENTITY"
        --force
        --options runtime
        --entitlements "$ENTITLEMENTS_PATH"
        --deep
    )
    
    # Add timestamp for non-ad-hoc signing
    if [ "$SIGNING_IDENTITY" != "-" ]; then
        cmd+=(--timestamp)
    fi
    
    cmd+=("$target")
    
    # Execute signing
    if "${cmd[@]}"; then
        echo "✓ Successfully signed: $target"
        return 0
    else
        echo "✗ Failed to sign: $target"
        return 1
    fi
}

# Step 1: Sign all libraries and frameworks
echo "Step 1: Signing libraries and frameworks..."
find "$APP_PATH/Contents" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 | \
    while IFS= read -r -d '' lib; do
        sign_binary "$lib" || true
    done

if [ -d "$APP_PATH/Contents/Frameworks" ]; then
    find "$APP_PATH/Contents/Frameworks" -type f -perm -111 -print0 | \
        while IFS= read -r -d '' binary; do
            sign_binary "$binary" || true
        done
fi

echo ""
echo "Step 2: Signing main executables..."
for exe in "$APP_PATH/Contents/MacOS"/*; do
    if [ -f "$exe" ] && [ -x "$exe" ]; then
        sign_binary "$exe"
    fi
done

echo ""
echo "Step 3: Signing app bundle..."
if sign_binary "$APP_PATH"; then
    echo ""
    echo "=================================================="
    echo "✓ Code signing completed successfully!"
    echo "=================================================="
    echo ""
    echo "Verification:"
    xcrun codesign --verify --deep --strict --verbose=2 "$APP_PATH" 2>&1 || true
    echo ""
    echo "Signature info:"
    xcrun codesign -dv --verbose=4 "$APP_PATH" 2>&1 || true
    exit 0
else
    echo ""
    echo "=================================================="
    echo "✗ Code signing failed!"
    echo "=================================================="
    exit 1
fi
```

Make it executable:

```bash
chmod +x build/macos/codesign.sh
```

#### C. Code Signing Modes

**1. Ad-hoc Signing (Development)**

Uses the special identifier "-" which doesn't require certificates:

```bash
MACOS_SIGNING_IDENTITY="-" ./build/macos/codesign.sh dist/YourApp.app
```

- No Apple Developer certificate required
- App runs without quarantine workaround
- Still shows security warning on first launch
- Perfect for local testing and development

**2. Developer ID Signing (Distribution)**

For distributing to users:

```bash
MACOS_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAM123)" \
    ./build/macos/codesign.sh dist/YourApp.app
```

- Requires Apple Developer Program ($99/year)
- Can be notarized by Apple
- No security warnings for users

**3. Finding Your Signing Identity**

```bash
# List all available signing identities
security find-identity -v -p codesigning
```

---

### Step 7: DMG Creation

Create a DMG (disk image) file for distribution with drag-to-Applications installation.

#### A. Create DMG with hdiutil

```bash
#!/bin/bash
# create_dmg.sh - Create DMG disk image

APP_NAME="YourApp"
VERSION="1.0.0"
DMG_NAME="${APP_NAME}-${VERSION}-macOS.dmg"

# Create temporary directory for DMG contents
mkdir -p dmg_temp

# Copy the app
cp -R "dist/${APP_NAME}.app" dmg_temp/

# Create Applications symlink for easy installation
ln -s /Applications dmg_temp/Applications

# Optional: Add README
cat > dmg_temp/README.txt << 'EOF'
YourApp - macOS Edition
=======================

Installation:
1. Drag YourApp.app to your Applications folder
2. Double-click to launch
3. On first launch, you may need to right-click → Open

For more information, visit: https://github.com/yourcompany/yourapp
EOF

# Create DMG
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder dmg_temp \
    -ov \
    -format UDZO \
    "$DMG_NAME"

# Clean up
rm -rf dmg_temp

echo "Created: $DMG_NAME"

# Optional: Calculate checksum
shasum -a 256 "$DMG_NAME" > "${DMG_NAME}.sha256"
```

#### B. Create ZIP Archive (Alternative)

For simpler distribution:

```bash
cd dist
zip -r ../YourApp-macOS.zip YourApp.app
```

---

### Step 8: CI/CD Integration

Automate the entire build process with GitHub Actions.

**`.github/workflows/build-release.yml`**:

```yaml
name: Build macOS Release

on:
  release:
    types: [created]
  workflow_dispatch:
    inputs:
      version:
        description: 'Version tag (e.g., v1.0.0)'
        required: true
        default: 'v1.0.0'

permissions:
  contents: write

jobs:
  build-macos:
    name: Build macOS Application
    runs-on: macos-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Set version
      run: |
        if [ "${{ github.event_name }}" == "release" ]; then
          VERSION="${{ github.event.release.tag_name }}"
        else
          VERSION="${{ github.event.inputs.version }}"
        fi
        echo "VERSION=$VERSION" >> $GITHUB_ENV
        echo "$VERSION" > VERSION
      
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'
        
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install "pyinstaller>=6.0"
        
    - name: Verify icon exists
      run: |
        if [ ! -f "build/macos/YourApp.icns" ]; then
          echo "ERROR: Icon file not found"
          exit 1
        fi

    - name: Clean previous builds
      run: |
        rm -rf dist/YourApp.app dist/YourApp build/YourApp

    - name: Build with PyInstaller
      run: |
        python -m PyInstaller YourApp.spec --clean --noconfirm

    - name: Set up app bundle executable
      run: |
        cp dist/YourApp.app/Contents/MacOS/YourApp_bin \
           dist/YourApp.app/Contents/MacOS/YourApp
        chmod +x dist/YourApp.app/Contents/MacOS/YourApp
        
    - name: Code sign the app bundle
      run: |
        chmod +x build/macos/codesign.sh
        ./build/macos/codesign.sh dist/YourApp.app
      env:
        MACOS_SIGNING_IDENTITY: ${{ secrets.MACOS_SIGNING_IDENTITY || '-' }}
        
    - name: Create DMG
      run: |
        mkdir -p dmg_temp
        cp -R dist/YourApp.app dmg_temp/
        ln -s /Applications dmg_temp/Applications
        
        hdiutil create -volname "YourApp" \
          -srcfolder dmg_temp \
          -ov -format UDZO \
          YourApp-macOS.dmg
          
    - name: Create ZIP archive
      run: |
        cd dist
        zip -r ../YourApp-macOS.zip YourApp.app
        cd ..
        
    - name: Calculate checksums
      run: |
        shasum -a 256 YourApp-macOS.dmg > checksums.txt
        shasum -a 256 YourApp-macOS.zip >> checksums.txt
        
    - name: Upload artifacts
      uses: actions/upload-artifact@v4
      with:
        name: YourApp-macOS
        path: |
          YourApp-macOS.dmg
          YourApp-macOS.zip
          checksums.txt
        
    - name: Upload to release
      if: github.event_name == 'release'
      uses: softprops/action-gh-release@v1
      with:
        files: |
          YourApp-macOS.dmg
          YourApp-macOS.zip
          checksums.txt
```

**Setting Up GitHub Secrets:**

For Developer ID signing in CI/CD:

1. Export your certificate from Keychain Access as `.p12`
2. Encode it: `base64 -i certificate.p12 | pbcopy`
3. Add GitHub secrets:
   - `MACOS_CERTIFICATE`: Base64-encoded certificate
   - `MACOS_CERTIFICATE_PWD`: Certificate password
   - `MACOS_SIGNING_IDENTITY`: "Developer ID Application: Your Name (TEAM123)"

---

## Advanced Topics

### Optimizing Bundle Size

#### Exclude Unnecessary Packages

In your `.spec` file:

```python
excludes=[
    'matplotlib',  # If you don't use plotting
    'tkinter',     # If you don't use Tkinter
    'pytest',      # Testing frameworks
    'IPython',     # Interactive shells
]
```

#### Use UPX Compression

PyInstaller can compress binaries with UPX:

```python
exe = EXE(
    # ...
    upx=True,  # Enable UPX compression
)
```

Install UPX:

```bash
brew install upx
```

### Handling Large Dependencies

For apps with large AI models or datasets:

1. **Don't bundle the models** - Download them on first run
2. **Use external storage** - Store in `~/Library/Application Support/YourApp/`
3. **Provide download script** - Let users download models separately

**Example: Model Download on First Run**

```python
from pathlib import Path
import requests

def get_models_dir():
    """Get the directory for storing models"""
    app_support = Path.home() / 'Library' / 'Application Support' / 'YourApp'
    models_dir = app_support / 'models'
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir

def download_model_if_needed(model_name, url):
    """Download a model if it doesn't exist locally"""
    models_dir = get_models_dir()
    model_path = models_dir / model_name
    
    if model_path.exists():
        return model_path
    
    print(f"Downloading {model_name}...")
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(model_path, 'wb') as f:
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
            downloaded += len(chunk)
            # Show progress
            progress = (downloaded / total_size) * 100
            print(f"Progress: {progress:.1f}%", end='\r')
    
    print(f"\nDownloaded {model_name}")
    return model_path
```

### macOS User Directory Standards

macOS has specific conventions for where applications should store different types of files. Following these standards ensures your app:
- Works correctly in sandboxed environments
- Integrates properly with system backup tools (Time Machine)
- Respects user privacy and security expectations
- Follows Apple's App Store guidelines

#### Standard macOS Directories

**Directory Structure:**

```
~/Library/
├── Application Support/YourApp/    # App data, models, databases
├── Caches/YourApp/                 # Temporary cache files
├── Logs/YourApp/                   # Application logs
└── Preferences/                    # Settings and preferences
    └── com.yourcompany.yourapp.plist
```

#### 1. Application Support Directory

**Purpose**: Persistent app data, user-generated content, downloaded models, databases

**Path**: `~/Library/Application Support/YourApp/`

**Use for**:
- AI/ML models
- User databases
- Plugin data
- Downloaded content
- App-specific data files

**Example Implementation:**

```python
from pathlib import Path
import platform

def get_app_support_dir(app_name: str = "YourApp") -> Path:
    """
    Get the Application Support directory for your app.
    
    Returns:
        Path to ~/Library/Application Support/YourApp/ on macOS
        Falls back to app directory on other platforms
    """
    if platform.system() == "Darwin":  # macOS
        app_support = Path.home() / "Library" / "Application Support" / app_name
        app_support.mkdir(parents=True, exist_ok=True)
        return app_support
    else:
        # Fallback for Windows/Linux
        return Path(__file__).parent

def get_models_dir(app_name: str = "YourApp") -> Path:
    """Get the models directory within App Support"""
    models_dir = get_app_support_dir(app_name) / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir

def get_data_dir(app_name: str = "YourApp") -> Path:
    """Get the data directory within App Support"""
    data_dir = get_app_support_dir(app_name) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

# Usage:
models_path = get_models_dir("YourApp")
model_file = models_path / "my_model.bin"
```

#### 2. Preferences Directory

**Purpose**: User preferences, settings, configuration

**Path**: `~/Library/Preferences/com.yourcompany.yourapp.plist` (traditional)
or `~/Library/Preferences/com.yourcompany.yourapp/` (custom directory)

**Use for**:
- User settings
- UI preferences
- Configuration options
- Feature flags

**Example Implementation:**

```python
import json
from pathlib import Path
import platform

def get_preferences_dir(bundle_id: str = "com.yourcompany.yourapp") -> Path:
    """
    Get the preferences directory for your app.
    
    Args:
        bundle_id: Reverse-DNS style bundle identifier (e.g., "com.yourcompany.yourapp")
    
    Returns:
        Path to ~/Library/Preferences/com.yourcompany.yourapp/ on macOS
    """
    if platform.system() == "Darwin":  # macOS
        prefs_dir = Path.home() / "Library" / "Preferences" / bundle_id
        prefs_dir.mkdir(parents=True, exist_ok=True)
        return prefs_dir
    else:
        # Fallback for Windows/Linux
        return Path(__file__).parent

def load_preferences(bundle_id: str = "com.yourcompany.yourapp") -> dict:
    """Load app preferences from JSON file"""
    prefs_dir = get_preferences_dir(bundle_id)
    prefs_file = prefs_dir / "settings.json"
    
    if prefs_file.exists():
        try:
            with open(prefs_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load preferences: {e}")
    
    # Return defaults
    return {
        "ui_zoom": 100,
        "theme": "light",
        "auto_save": True,
    }

def save_preferences(prefs: dict, bundle_id: str = "com.yourcompany.yourapp") -> None:
    """Save app preferences to JSON file"""
    prefs_dir = get_preferences_dir(bundle_id)
    prefs_file = prefs_dir / "settings.json"
    
    try:
        with open(prefs_file, 'w', encoding='utf-8') as f:
            json.dump(prefs, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save preferences: {e}")

# Usage:
prefs = load_preferences("com.yourcompany.yourapp")
zoom = prefs.get("ui_zoom", 100)

prefs["ui_zoom"] = 120
save_preferences(prefs, "com.yourcompany.yourapp")
```

#### 3. Caches Directory

**Purpose**: Temporary data that can be regenerated or re-downloaded

**Path**: `~/Library/Caches/YourApp/`

**Use for**:
- Downloaded thumbnails
- Temporary processed data
- API response caches
- Compiled assets

**Important**: Cache files may be deleted by the system when disk space is low.

**Example Implementation:**

```python
from pathlib import Path
import platform
import time

def get_caches_dir(app_name: str = "YourApp") -> Path:
    """
    Get the Caches directory for your app.
    Cache files may be deleted by the system when disk space is low.
    """
    if platform.system() == "Darwin":  # macOS
        caches_dir = Path.home() / "Library" / "Caches" / app_name
        caches_dir.mkdir(parents=True, exist_ok=True)
        return caches_dir
    else:
        # Fallback for Windows/Linux
        return Path(__file__).parent / "cache"

def cache_file(key: str, data: bytes, app_name: str = "YourApp") -> Path:
    """Cache data to a file"""
    cache_dir = get_caches_dir(app_name)
    cache_file = cache_dir / f"{key}.cache"
    
    try:
        with open(cache_file, 'wb') as f:
            f.write(data)
        return cache_file
    except Exception as e:
        print(f"Warning: Failed to cache file: {e}")
        return None

def get_cached_file(key: str, max_age_seconds: int = 3600, 
                   app_name: str = "YourApp") -> bytes | None:
    """Get cached data if it exists and is not expired"""
    cache_dir = get_caches_dir(app_name)
    cache_file = cache_dir / f"{key}.cache"
    
    if not cache_file.exists():
        return None
    
    # Check age
    age = time.time() - cache_file.stat().st_mtime
    if age > max_age_seconds:
        # Cache expired
        cache_file.unlink()
        return None
    
    try:
        with open(cache_file, 'rb') as f:
            return f.read()
    except Exception as e:
        print(f"Warning: Failed to read cache: {e}")
        return None

def clear_cache(app_name: str = "YourApp") -> None:
    """Clear all cached files"""
    cache_dir = get_caches_dir(app_name)
    
    try:
        import shutil
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            cache_dir.mkdir(parents=True, exist_ok=True)
            print(f"Cache cleared: {cache_dir}")
    except Exception as e:
        print(f"Warning: Failed to clear cache: {e}")

# Usage:
# Cache an API response
cache_file("api_users", b'{"users": [...]}')

# Get cached data (returns None if expired or missing)
cached_data = get_cached_file("api_users", max_age_seconds=1800)

# Clear all caches
clear_cache()
```

#### 4. Logs Directory

**Purpose**: Application logs, crash reports, debug information

**Path**: `~/Library/Logs/YourApp/`

**Use for**:
- Application logs
- Error reports
- Debug information
- Performance metrics

**Example Implementation:**

```python
import logging
from pathlib import Path
import platform
from datetime import datetime

def get_logs_dir(app_name: str = "YourApp") -> Path:
    """Get the Logs directory for your app"""
    if platform.system() == "Darwin":  # macOS
        logs_dir = Path.home() / "Library" / "Logs" / app_name
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir
    else:
        # Fallback for Windows/Linux
        return Path(__file__).parent / "logs"

def setup_logging(app_name: str = "YourApp", level=logging.INFO) -> None:
    """
    Set up application logging to both console and file.
    Logs are saved to ~/Library/Logs/YourApp/
    """
    logs_dir = get_logs_dir(app_name)
    
    # Create log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"{app_name}_{timestamp}.log"
    
    # Configure logging
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also log to console
        ]
    )
    
    logging.info(f"Logging initialized: {log_file}")

def log_error(error: Exception, app_name: str = "YourApp") -> None:
    """Log an error with full traceback to log file"""
    import traceback
    
    logs_dir = get_logs_dir(app_name)
    error_log = logs_dir / "errors.log"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_text = f"\n{'='*60}\n"
    error_text += f"ERROR at {timestamp}\n"
    error_text += f"{'='*60}\n"
    error_text += traceback.format_exc()
    error_text += f"\n{'='*60}\n"
    
    try:
        with open(error_log, 'a', encoding='utf-8') as f:
            f.write(error_text)
        print(f"Error logged to: {error_log}")
    except Exception as e:
        print(f"Warning: Failed to log error: {e}")

def cleanup_old_logs(max_age_days: int = 30, app_name: str = "YourApp") -> None:
    """Remove log files older than specified days"""
    import time
    
    logs_dir = get_logs_dir(app_name)
    cutoff_time = time.time() - (max_age_days * 86400)
    
    for log_file in logs_dir.glob("*.log"):
        if log_file.stat().st_mtime < cutoff_time:
            try:
                log_file.unlink()
                print(f"Deleted old log: {log_file.name}")
            except Exception as e:
                print(f"Warning: Failed to delete log {log_file.name}: {e}")

# Usage:
setup_logging("YourApp")

try:
    # Your app code
    logging.info("Application started")
    # ...
except Exception as e:
    log_error(e)
    raise

# Periodic cleanup
cleanup_old_logs(max_age_days=7)
```

#### 5. Temporary Files

**Purpose**: Very short-lived temporary files

**Path**: `/tmp/` or use `tempfile.mkdtemp()`

**Use for**:
- Processing temporary files
- Extraction buffers
- Build artifacts

**Example:**

```python
import tempfile
from pathlib import Path

def get_temp_dir(app_name: str = "YourApp") -> Path:
    """Get a temporary directory that's cleaned up on reboot"""
    temp_dir = Path(tempfile.gettempdir()) / app_name
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir

# Or use context manager for automatic cleanup
with tempfile.TemporaryDirectory(prefix="YourApp_") as temp_dir:
    temp_path = Path(temp_dir)
    # Use temp_path...
    # Automatically deleted when context exits
```

#### Complete Directory Management Module

Here's a complete module incorporating all directory types:

```python
"""
app_paths.py - Centralized path management for macOS applications
"""

from pathlib import Path
import platform
import json
from typing import Optional

class AppPaths:
    """Manage all application paths following macOS conventions"""
    
    def __init__(self, app_name: str, bundle_id: str):
        """
        Initialize path manager.
        
        Args:
            app_name: App name for directories (e.g., "YourApp")
            bundle_id: Bundle identifier (e.g., "com.yourcompany.yourapp")
        """
        self.app_name = app_name
        self.bundle_id = bundle_id
        self.is_macos = platform.system() == "Darwin"
        
        # Determine if running as frozen app
        import sys
        if getattr(sys, 'frozen', False):
            self.app_dir = Path(sys.executable).resolve().parent
        else:
            self.app_dir = Path(__file__).parent.resolve()
    
    # Application Support (persistent data)
    
    def get_app_support_dir(self) -> Path:
        """Get ~/Library/Application Support/YourApp/"""
        if self.is_macos:
            path = Path.home() / "Library" / "Application Support" / self.app_name
        else:
            path = self.app_dir / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_models_dir(self) -> Path:
        """Get directory for ML models"""
        path = self.get_app_support_dir() / "models"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_user_data_dir(self) -> Path:
        """Get directory for user-generated content"""
        path = self.get_app_support_dir() / "user_data"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # Preferences (settings)
    
    def get_preferences_dir(self) -> Path:
        """Get ~/Library/Preferences/com.yourcompany.yourapp/"""
        if self.is_macos:
            path = Path.home() / "Library" / "Preferences" / self.bundle_id
        else:
            path = self.app_dir
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def get_config_file(self) -> Path:
        """Get path to main config file"""
        return self.get_preferences_dir() / "config.json"
    
    def load_config(self) -> dict:
        """Load configuration from file"""
        config_file = self.get_config_file()
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load config: {e}")
        return {}
    
    def save_config(self, config: dict) -> None:
        """Save configuration to file"""
        config_file = self.get_config_file()
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save config: {e}")
    
    # Caches (temporary data)
    
    def get_caches_dir(self) -> Path:
        """Get ~/Library/Caches/YourApp/"""
        if self.is_macos:
            path = Path.home() / "Library" / "Caches" / self.app_name
        else:
            path = self.app_dir / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # Logs (application logs)
    
    def get_logs_dir(self) -> Path:
        """Get ~/Library/Logs/YourApp/"""
        if self.is_macos:
            path = Path.home() / "Library" / "Logs" / self.app_name
        else:
            path = self.app_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

# Global instance (initialize once at app startup)
paths = AppPaths(app_name="YourApp", bundle_id="com.yourcompany.yourapp")

# Usage throughout your app:
# from app_paths import paths
#
# model_file = paths.get_models_dir() / "model.bin"
# config = paths.load_config()
# log_file = paths.get_logs_dir() / "app.log"
```

#### Best Practices

**1. Always Create Directories with `mkdir(parents=True, exist_ok=True)`**

```python
path = Path.home() / "Library" / "Application Support" / "YourApp"
path.mkdir(parents=True, exist_ok=True)  # Safe, won't fail if exists
```

**2. Use Platform Detection**

```python
import platform

if platform.system() == "Darwin":  # macOS
    # Use ~/Library/...
else:
    # Fallback for other platforms
```

**3. Handle Errors Gracefully**

```python
try:
    with open(config_file, 'r') as f:
        config = json.load(f)
except Exception as e:
    print(f"Warning: Using default config due to: {e}")
    config = get_default_config()
```

**4. Don't Store Large Files in Preferences**

- ✅ Application Support: Models, databases, user content
- ❌ Preferences: Should only be small config files

**5. Respect Privacy**

Don't access directories outside your app's sandbox without user permission:
- Use file dialogs for user-selected files
- Don't scan or index user's home directory
- Respect privacy entitlements

**6. Clean Up on Uninstall**

Provide a way to remove all app data:

```python
def uninstall_cleanup(app_name: str, bundle_id: str):
    """Remove all app data (call before uninstalling)"""
    import shutil
    
    dirs_to_remove = [
        Path.home() / "Library" / "Application Support" / app_name,
        Path.home() / "Library" / "Caches" / app_name,
        Path.home() / "Library" / "Logs" / app_name,
        Path.home() / "Library" / "Preferences" / bundle_id,
    ]
    
    for directory in dirs_to_remove:
        if directory.exists():
            try:
                shutil.rmtree(directory)
                print(f"Removed: {directory}")
            except Exception as e:
                print(f"Warning: Could not remove {directory}: {e}")
```

#### Summary Table

| Directory | Path | Purpose | Backed Up | Can Be Deleted |
|-----------|------|---------|-----------|----------------|
| Application Support | `~/Library/Application Support/YourApp/` | Models, databases, user data | ✅ Yes | ❌ No |
| Preferences | `~/Library/Preferences/com.yourcompany.yourapp/` | Settings, config | ✅ Yes | ❌ No |
| Caches | `~/Library/Caches/YourApp/` | Temporary cached data | ❌ No | ✅ Yes (by system) |
| Logs | `~/Library/Logs/YourApp/` | Application logs | ❌ No | ✅ Yes (manually) |
| Temp | `/tmp/YourApp_*` | Very short-lived files | ❌ No | ✅ Yes (on reboot) |

### PyWebView Integration

PyWebView creates **native macOS windows** that display your web application without requiring an external browser. This provides a true native app experience with proper window management, dock integration, and system integration.

#### Complete Flask + PyWebView Integration

This section covers the complete implementation including server startup, window lifecycle management, and proper cleanup on window close.

**Production-Ready Implementation:**

```python
#!/usr/bin/env python3
"""
Complete PyWebView + Flask integration with proper lifecycle management
"""

import sys
import os
import threading
import time
import socket
import atexit
from pathlib import Path

import webview
from flask import Flask
from waitress import serve

# Server configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

# Application state
_shutting_down = False

def create_app():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    @app.route('/')
    def index():
        return """
        <!DOCTYPE html>
        <html>
            <head>
                <title>YourApp</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
            </head>
            <body>
                <h1>Hello from PyWebView!</h1>
                <p>This is a native macOS window displaying web content.</p>
                <button onclick="window.pywebview.api.test()">Test API</button>
            </body>
        </html>
        """
    
    return app

def wait_for_server(host, port, max_wait=30):
    """Wait for Flask server to be ready"""
    print(f"Waiting for server at {host}:{port}...", flush=True)
    waited = 0
    while waited < max_wait:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                print(f"Server ready at http://{host}:{port}", flush=True)
                return True
        except Exception:
            pass
        time.sleep(0.5)
        waited += 0.5
    return False

def start_flask_server(app, host, port):
    """Start Flask server using Waitress (production WSGI server)"""
    print(f"Starting Flask server on {host}:{port}...", flush=True)
    try:
        # Use Waitress instead of Flask's development server
        serve(app, host=host, port=port, threads=4, channel_timeout=120)
    except Exception as e:
        print(f"Flask server error: {e}", flush=True)
        raise

def cleanup_resources():
    """Clean up all resources before shutdown"""
    global _shutting_down
    
    if _shutting_down:
        return  # Already cleaning up
    
    _shutting_down = True
    print("Cleaning up resources...", flush=True)
    
    try:
        # Clean up your app-specific resources here
        # Examples:
        # - Release ML models
        # - Close database connections
        # - Clear caches
        # - Save state
        
        # For PyTorch apps:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except ImportError:
            pass
        
        # Force garbage collection
        import gc
        gc.collect()
        
        print("Resource cleanup completed", flush=True)
        
    except Exception as e:
        print(f"Warning: Error during cleanup: {e}", flush=True)

class WindowAPI:
    """
    API exposed to JavaScript for window control.
    Methods can be called from JavaScript using: window.pywebview.api.method_name()
    """
    
    def test(self):
        """Test API method"""
        print("API test method called from JavaScript!", flush=True)
        return {"status": "ok", "message": "API is working!"}
    
    def minimize(self):
        """Minimize the window"""
        try:
            if webview.windows:
                webview.windows[0].minimize()
                return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def maximize(self):
        """Maximize the window"""
        try:
            if webview.windows:
                webview.windows[0].maximize()
                return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

def main():
    """Main entry point with proper lifecycle management"""
    global _shutting_down
    
    # Create Flask app
    app = create_app()
    
    # Start Flask server in background daemon thread
    server_thread = threading.Thread(
        target=start_flask_server,
        args=(app, SERVER_HOST, SERVER_PORT),
        daemon=True,
        name="FlaskServer"
    )
    server_thread.start()
    
    # Wait for server to be ready
    if not wait_for_server(SERVER_HOST, SERVER_PORT):
        print("ERROR: Server failed to start in time", flush=True)
        sys.exit(1)
    
    # Create API instance
    window_api = WindowAPI()
    
    # Define window close handler
    def on_window_closed():
        """
        Called when user closes the window (clicks X button).
        This is where you perform cleanup and shutdown.
        """
        print("Window closed by user", flush=True)
        
        # Clean up all resources
        cleanup_resources()
        
        # Exit the application
        # Use os._exit(0) to bypass any cleanup handlers that might cause issues
        os._exit(0)
    
    # Create native macOS window
    window = webview.create_window(
        title="YourApp",
        url=SERVER_URL,
        width=1200,
        height=800,
        min_size=(800, 600),  # Minimum window size
        resizable=True,
        fullscreen=False,
        frameless=False,  # Set to True for frameless window
        easy_drag=True,  # Allow dragging frameless window
        on_top=False,
        shadow=True,
        js_api=window_api,  # Expose API to JavaScript
    )
    
    # Register window close event handler
    # CRITICAL: This ensures proper cleanup when user closes the window
    try:
        window.events.closed += on_window_closed
        print("Window close handler registered", flush=True)
    except Exception as e:
        print(f"Warning: Could not register close handler: {e}", flush=True)
        # Fallback: register cleanup with atexit
        atexit.register(cleanup_resources)
    
    # Register backup cleanup handler
    atexit.register(cleanup_resources)
    
    # Start the GUI event loop (blocking call)
    # This will run until the window is closed
    print("Starting GUI event loop...", flush=True)
    webview.start(debug=False)
    
    # This line is reached after window closes
    # (if on_window_closed doesn't call os._exit)
    print("GUI event loop ended", flush=True)
    cleanup_resources()
    sys.exit(0)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user", flush=True)
        cleanup_resources()
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"FATAL ERROR:\n{traceback.format_exc()}", flush=True)
        cleanup_resources()
        sys.exit(1)
```

#### Key Components Explained

**1. Window Close Handler (`on_window_closed`)**

The window close handler is **critical** for proper application shutdown. When the user clicks the X button:

```python
def on_window_closed():
    """Handle window close event"""
    print("Window closed by user", flush=True)
    cleanup_resources()  # Clean up before exit
    os._exit(0)  # Immediate exit
```

Register it with:
```python
window.events.closed += on_window_closed
```

**Why `os._exit(0)` instead of `sys.exit(0)`?**
- `os._exit(0)` exits immediately without running cleanup handlers
- Prevents any code from running that might try to re-initialize the window
- Essential for frozen PyInstaller apps where cleanup handlers can cause issues

**2. Resource Cleanup**

The `cleanup_resources()` function should release all app resources:

```python
def cleanup_resources():
    """Clean up before shutdown"""
    global _shutting_down
    
    if _shutting_down:
        return  # Prevent duplicate cleanup
    
    _shutting_down = True
    
    # Release ML models, clear GPU cache, etc.
    try:
        import torch
        if hasattr(torch.backends, "mps"):
            torch.mps.empty_cache()
    except:
        pass
    
    # Force garbage collection
    import gc
    gc.collect()
```

**3. Server Readiness Check**

Never create the window before the server is ready:

```python
def wait_for_server(host, port, max_wait=30):
    """Wait for server to accept connections"""
    waited = 0
    while waited < max_wait:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except:
            pass
        time.sleep(0.5)
        waited += 0.5
    return False
```

**4. Production WSGI Server**

Use Waitress instead of Flask's development server:

```python
from waitress import serve

def start_flask_server(app, host, port):
    """Production-ready server"""
    serve(app, host=host, port=port, threads=4, channel_timeout=120)
```

**5. JavaScript API Bridge**

Expose Python functions to JavaScript:

```python
class WindowAPI:
    def my_function(self, arg1, arg2):
        """Callable from JavaScript"""
        return {"result": "success"}

# JavaScript side:
# window.pywebview.api.my_function(arg1, arg2).then(result => {
#     console.log(result);
# });
```

#### Advanced Window Features

**Window Configuration Options:**

```python
window = webview.create_window(
    title="App Title",
    url="http://127.0.0.1:5000",
    
    # Size and position
    width=1400,
    height=900,
    x=100,  # Position from left edge
    y=100,  # Position from top edge
    min_size=(800, 600),  # Minimum dimensions
    
    # Appearance
    resizable=True,
    fullscreen=False,
    frameless=False,  # Remove title bar and borders
    easy_drag=True,  # Drag frameless window by any area
    on_top=False,  # Always on top of other windows
    shadow=True,  # Drop shadow (for frameless windows)
    
    # Behavior
    confirm_close=False,  # Ask before closing
    background_color='#FFFFFF',  # Window background
    text_select=True,  # Allow text selection
    
    # API
    js_api=window_api,  # Expose Python API to JavaScript
)
```

**Running JavaScript from Python:**

```python
# After window is created and loaded
def run_after_load():
    time.sleep(1)  # Wait for page load
    result = window.evaluate_js('document.title')
    print(f"Page title: {result}")
    
    # Or use run_js() to execute without return value
    window.run_js('document.body.style.background = "blue"')

# Run in separate thread
threading.Thread(target=run_after_load, daemon=True).start()
```

**Frameless Window with Custom Title Bar:**

```python
# Create frameless window
window = webview.create_window(
    title="YourApp",
    url=SERVER_URL,
    frameless=True,
    easy_drag=True,
)

# HTML with custom title bar
html = """
<div id="titlebar" style="
    -webkit-app-region: drag;
    height: 40px;
    background: #333;
    color: white;
    display: flex;
    align-items: center;
    padding: 0 15px;
">
    <span>YourApp</span>
    <div style="margin-left: auto; -webkit-app-region: no-drag;">
        <button onclick="window.pywebview.api.minimize()">−</button>
        <button onclick="window.pywebview.api.maximize()">□</button>
        <button onclick="window.close()">×</button>
    </div>
</div>
"""
```

#### Singleton Protection for PyInstaller

For PyInstaller frozen apps, protect against duplicate window creation:

```python
import threading

_webview_started = False
_webview_lock = threading.Lock()

def safe_webview_start(*args, **kwargs):
    """Prevent duplicate webview.start() calls"""
    global _webview_started
    with _webview_lock:
        if _webview_started:
            return None
        _webview_started = True
        return webview.start(*args, **kwargs)

# Use instead of webview.start()
safe_webview_start()
```

#### Troubleshooting PyWebView

**Window doesn't close properly:**
- Ensure `on_window_closed` handler is registered
- Use `os._exit(0)` instead of `sys.exit(0)`
- Check for background threads preventing exit

**"Server not ready" errors:**
- Increase `max_wait` in `wait_for_server()`
- Check firewall/port availability
- Verify Flask server starts without errors

**JavaScript API not working:**
- Ensure `js_api` parameter is set in `create_window()`
- Wait for page to load before calling API
- Check browser console for JavaScript errors

**Window shows blank page:**
- Verify server is running and accessible
- Check Flask route returns valid HTML
- Test URL in regular browser first

**App doesn't terminate on close:**
- Verify close handler is registered
- Check for non-daemon threads keeping process alive
- Use `os._exit(0)` for immediate termination

### Multi-Architecture Support

For both Intel and Apple Silicon:

#### Universal Binary Approach

PyInstaller on macOS will build for the architecture it's running on. For universal binaries:

1. Build on Intel Mac → Intel binary
2. Build on Apple Silicon → ARM binary
3. Use `lipo` to combine:

```bash
lipo -create \
    -output YourApp_universal \
    YourApp_intel \
    YourApp_arm64
```

#### Separate Builds Approach

Recommended: Build separate versions:

- `YourApp-macOS-Intel.dmg` (x86_64)
- `YourApp-macOS-AppleSilicon.dmg` (arm64)

GitHub Actions can build both using different runners.

---

## Troubleshooting

### "The application is damaged and can't be opened"

**Cause:** App is unsigned or signature is invalid

**Solutions:**

1. Run code signing script:
   ```bash
   ./build/macos/codesign.sh dist/YourApp.app
   ```

2. Remove quarantine attribute:
   ```bash
   xattr -cr dist/YourApp.app
   ```

3. Verify signature:
   ```bash
   codesign --verify --deep --strict --verbose=2 dist/YourApp.app
   ```

### ImportError in Frozen App

**Cause:** PyInstaller didn't detect a required module

**Solutions:**

1. Add to `hiddenimports` in `.spec` file:
   ```python
   hiddenimports=[
       'missing_module',
       'missing_module.submodule',
   ]
   ```

2. Create a custom hook in `build/macos/pyinstaller_hooks/`

3. Use `collect_submodules` for complex packages:
   ```python
   *collect_submodules('complex_package'),
   ```

### Missing Data Files

**Cause:** Package data files not included

**Solutions:**

1. Add to `datas` in `.spec` file:
   ```python
   datas=[
       ('path/to/data', 'destination/in/bundle'),
   ]
   ```

2. Use `collect_data_files`:
   ```python
   from PyInstaller.utils.hooks import collect_data_files
   datas = collect_data_files('package_name')
   ```

### App Icon Not Showing

**Cause:** Icon file missing or corrupted

**Solutions:**

1. Verify icon exists:
   ```bash
   ls -lh build/macos/YourApp.icns
   ```

2. Regenerate from iconset:
   ```bash
   iconutil -c icns build/macos/YourApp.iconset -o build/macos/YourApp.icns
   ```

3. Check Info.plist references correct icon:
   ```bash
   defaults read dist/YourApp.app/Contents/Info.plist CFBundleIconFile
   ```

### Large Bundle Size

**Cause:** Including unnecessary dependencies

**Solutions:**

1. Exclude unused packages in `.spec`:
   ```python
   excludes=['matplotlib', 'tkinter', 'IPython']
   ```

2. Enable UPX compression:
   ```python
   upx=True
   ```

3. Don't bundle large models - download on first run

4. Check what's in your bundle:
   ```bash
   du -h -d 1 dist/YourApp.app/Contents/MacOS/
   ```

### Code Signing Fails

**Cause:** Invalid certificate or entitlements

**Solutions:**

1. Use ad-hoc signing for testing:
   ```bash
   MACOS_SIGNING_IDENTITY="-" ./build/macos/codesign.sh dist/YourApp.app
   ```

2. Verify certificate is valid:
   ```bash
   security find-identity -v -p codesigning
   ```

3. Check entitlements file exists:
   ```bash
   ls -l build/macos/entitlements.plist
   ```

### App Crashes on Launch

**Cause:** Missing dependencies or incompatible architecture

**Solutions:**

1. Run from terminal to see error messages:
   ```bash
   dist/YourApp.app/Contents/MacOS/YourApp
   ```

2. Check Python version matches:
   ```bash
   dist/YourApp.app/Contents/MacOS/YourApp --version
   ```

3. Verify all binaries are signed:
   ```bash
   find dist/YourApp.app -type f -perm -111 | xargs codesign --verify --verbose
   ```

---

## References

### Official Documentation

- **PyInstaller**: https://pyinstaller.org/
- **PyWebView**: https://pywebview.flowrl.com/
- **Apple Code Signing**: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- **Flask**: https://flask.palletsprojects.com/

### Useful Resources

- **Apple Entitlements**: https://developer.apple.com/documentation/bundleresources/entitlements
- **macOS App Bundle**: https://developer.apple.com/library/archive/documentation/CoreFoundation/Conceptual/CFBundles/BundleTypes/BundleTypes.html
- **Icon Guidelines**: https://developer.apple.com/design/human-interface-guidelines/app-icons
- **DMG Best Practices**: https://github.com/create-dmg/create-dmg

### Example Projects

- **AceForge**: https://github.com/audiohacking/AceForge
  - Complete implementation of this packaging method
  - Flask + PyWebView + PyInstaller
  - AI/ML dependencies (PyTorch, transformers, etc.)
  - CI/CD with GitHub Actions

---

## Real-World Implementation: AceForge

This section provides the **actual, complete scripts** from the AceForge project as a concrete example. These are production scripts, not templates.

### AceForge build_local.sh (Complete)

The actual AceForge local build script with all optimizations and caching features:

```bash
#!/bin/bash
# ---------------------------------------------------------------------------
#  AceForge - Local Build Script
#  Builds the PyInstaller app bundle for local testing.
#  Includes the new React UI (ui/) when present; requires Bun (https://bun.sh).
#
#  Optional env vars (safe, non-destructive caching for faster rebuilds):
#    ACEFORGE_QUICK_BUILD=1  - Reuse PyInstaller cache (omit --clean, keep build/AceForge).
#                              Use when only code changed; full clean build if things break.
#    ACEFORGE_SKIP_UI_BUILD=1 - Skip UI build; use existing ui/dist/. Use when only Python changed.
#    ACEFORGE_SKIP_PIP=1     - Skip venv/pip steps. Use when deps unchanged and venv already ready.
# ---------------------------------------------------------------------------

set -e  # Exit on error

echo "=========================================="
echo "AceForge - Local Build"
echo "=========================================="
echo ""

# App root = folder this script lives in
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

# ---------------------------------------------------------------------------
# Build new UI (React/Vite) with Bun when ui/ exists; skip if ACEFORGE_SKIP_UI_BUILD=1.
# ---------------------------------------------------------------------------
UI_DIR="${APP_DIR}/ui"
if [ -f "$UI_DIR/package.json" ]; then
    if [ -n "${ACEFORGE_SKIP_UI_BUILD}" ]; then
        if [ ! -f "$UI_DIR/dist/index.html" ]; then
            echo "ERROR: ACEFORGE_SKIP_UI_BUILD is set but ui/dist/index.html not found. Run without it once."
            exit 1
        fi
        echo "[Build] Skipping UI build (ACEFORGE_SKIP_UI_BUILD)"
    else
        if ! command -v bun &> /dev/null; then
            echo "ERROR: Bun is required to build the new UI. Install from https://bun.sh"
            exit 1
        fi
        echo "[Build] Building new UI (React SPA) with Bun..."
        "${APP_DIR}/scripts/build_ui.sh"
        echo "[Build] New UI build OK"
    fi
else
    echo "ERROR: ui/package.json not found. The new UI source is required for the full app build."
    exit 1
fi
echo ""

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
    if [ -n "${ACEFORGE_SKIP_PIP}" ]; then
        echo "ERROR: ACEFORGE_SKIP_PIP is set but venv_build not found. Run without it once."
        exit 1
    fi
    echo "[Build] Creating virtual environment..."
    $PYTHON_CMD -m venv "$VENV_DIR"
fi

echo "[Build] Activating virtual environment..."
source "${VENV_DIR}/bin/activate"

# Use venv Python for all installs and PyInstaller (ensures TTS and deps are in the bundle)
PY="${VENV_PY}"

if [ -z "${ACEFORGE_SKIP_PIP}" ]; then
# Upgrade pip
echo "[Build] Upgrading pip..."
"$PY" -m pip install --upgrade pip --quiet

# Install dependencies
echo "[Build] Installing dependencies..."
"$PY" -m pip install -r requirements_ace_macos.txt --quiet

# Install additional dependencies
echo "[Build] Installing additional dependencies..."
"$PY" -m pip install "audio-separator==0.40.0" --no-deps --quiet
"$PY" -m pip install "py3langid==0.3.0" --no-deps --quiet
"$PY" -m pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps --quiet
"$PY" -m pip install "rotary_embedding_torch" --quiet

# ---------------------------------------------------------------------------
# Slimming: remove Japanese (Sudachi) dictionary payload
# SudachiDict-core is ~200MB and not needed for AceForge.
# We explicitly uninstall it (and SudachiPy) so PyInstaller cannot bundle it.
# ---------------------------------------------------------------------------
echo "[Build] Removing Japanese Sudachi packages (if present)..."
"$PY" -m pip uninstall -y SudachiDict-core SudachiPy sudachidict-core sudachipy >/dev/null 2>&1 || true

# Install TTS for voice cloning (required for frozen app; build fails if TTS cannot be imported)
# TTS 0.21.2 needs its full dependency tree (phonemizers etc.); --no-deps breaks "from TTS.api import TTS"
echo "[Build] Installing TTS for voice cloning..."
"$PY" -m pip install "coqpit" "trainer>=0.0.32" "pysbd>=0.3.4" "inflect>=5.6.0" "unidecode>=1.3.2" --quiet
"$PY" -m pip install "TTS==0.21.2" --quiet
if ! "$PY" -c "from TTS.api import TTS" 2>/dev/null; then
    echo "[Build] ERROR: TTS installed but 'from TTS.api import TTS' failed. Voice cloning will not work in the app."
    echo "[Build] Run: $PY -c \"from TTS.api import TTS\" to see the error."
    "$PY" -c "from TTS.api import TTS" || true
    exit 1
fi
echo "[Build] TTS verified: from TTS.api import TTS OK"

# Install Demucs for stem splitting (optional component)
echo "[Build] Installing Demucs for stem splitting..."
"$PY" -m pip install "demucs==4.0.1" --quiet
if ! "$PY" -c "import demucs.separate" 2>/dev/null; then
    echo "[Build] WARNING: Demucs installed but 'import demucs.separate' failed. Stem splitting will not work in the app."
    echo "[Build] Run: $PY -c \"import demucs.separate\" to see the error."
    "$PY" -c "import demucs.separate" || true
    # Don't exit - stem splitting is optional
else
    echo "[Build] Demucs verified: import demucs.separate OK"
fi

# Install basic-pitch for MIDI generation (optional component)
echo "[Build] Installing basic-pitch for MIDI generation..."
"$PY" -m pip install "basic-pitch>=0.4.0" --quiet
if ! "$PY" -c "from basic_pitch.inference import predict" 2>/dev/null; then
    echo "[Build] WARNING: basic-pitch installed but 'from basic_pitch.inference import predict' failed. MIDI generation will not work in the app."
    echo "[Build] Run: $PY -c \"from basic_pitch.inference import predict\" to see the error."
    "$PY" -c "from basic_pitch.inference import predict" || true
    # Don't exit - MIDI generation is optional
else
    echo "[Build] basic-pitch verified: from basic_pitch.inference import predict OK"
fi

"$PY" -m pip install "pyinstaller>=6.0" --quiet

# One last pass right before bundling, in case anything reintroduced Sudachi.
echo "[Build] Final check: removing Japanese Sudachi packages (if present)..."
"$PY" -m pip uninstall -y SudachiDict-core SudachiPy sudachidict-core sudachipy >/dev/null 2>&1 || true
else
    echo "[Build] Skipping pip steps (ACEFORGE_SKIP_PIP)"
fi

# Check for PyInstaller (always run)
if ! "$PY" -m PyInstaller --version &> /dev/null; then
    echo "ERROR: PyInstaller not found. Please install it:"
    echo "  $PY -m pip install pyinstaller"
    exit 1
fi

echo "[Build] PyInstaller version: $("$PY" -m PyInstaller --version)"
echo ""

# Clean previous builds (PyInstaller outputs only).
# NEVER delete build/macos/ — it contains AceForge.icns (app icon), codesign.sh, pyinstaller hooks.
# NEVER delete ui/dist/ — may have been produced by the new UI build above.
# ACEFORGE_QUICK_BUILD=1: keep build/AceForge so PyInstaller can reuse cache.
if [ -n "${ACEFORGE_QUICK_BUILD}" ]; then
    echo "[Build] Quick build: reusing PyInstaller cache (keeping build/AceForge)"
    rm -rf dist/AceForge.app dist/CDMF
else
    echo "[Build] Cleaning previous PyInstaller builds..."
    rm -rf dist/AceForge.app dist/CDMF build/AceForge
fi

# Safeguard: build/macos must exist for the app icon and code signing
if [ ! -f "build/macos/AceForge.icns" ]; then
    echo "ERROR: build/macos/AceForge.icns not found. build/macos/ must never be deleted."
    echo "  Restore from main: git checkout main -- build/macos/"
    exit 1
fi

# Build with PyInstaller (omit --clean when ACEFORGE_QUICK_BUILD=1 to reuse cache)
echo "[Build] Building app bundle with PyInstaller..."
echo "This may take several minutes..."
if [ -n "${ACEFORGE_QUICK_BUILD}" ]; then
    "$PY" -m PyInstaller CDMF.spec --noconfirm
else
    "$PY" -m PyInstaller CDMF.spec --clean --noconfirm
fi

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
echo "  ✓ New React UI is bundled; app will serve it at / when launched."
echo ""
```

### AceForge GitHub Actions Workflow (Complete)

The actual `.github/workflows/build-release.yml` from AceForge:

```yaml
name: Build macOS Release

on:
  release:
    types: [created]
  workflow_dispatch:
    inputs:
      version:
        description: 'Version tag (e.g., v0.1.0)'
        required: true
        default: 'v0.1.0-macos'

permissions:
  contents: write
  packages: write

jobs:
  build-macos:
    name: Build macOS Application
    runs-on: macos-latest
    
    steps:
    - name: Checkout repository
      uses: actions/checkout@v4
      
    - name: Set version from release tag
      run: |
        if [ "${{ github.event_name }}" == "release" ]; then
          # Extract version from release tag (e.g., "v1.0.4" from tag "v1.0.4")
          VERSION="${{ github.event.release.tag_name }}"
        else
          # For workflow_dispatch, use the input version
          VERSION="${{ github.event.inputs.version }}"
        fi
        echo "Setting version to: $VERSION"
        echo "$VERSION" > VERSION
        cat VERSION
      
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'
        
    - name: Display Python version
      run: python --version

    - name: Set up Bun
      uses: oven-sh/setup-bun@v2
      with:
        bun-version: latest
    - name: Build new UI (React SPA) with Bun
      run: ./scripts/build_ui.sh

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements_ace_macos.txt
        pip install rotary_embedding_torch
        
    - name: Install audio-separator (no deps)
      run: |
        pip install "audio-separator==0.40.0" --no-deps
        
    - name: Install py3langid (no deps)
      run: |
        pip install "py3langid==0.3.0" --no-deps
        
    - name: Install ACE-Step (no deps)
      run: |
        pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps

    - name: Install TTS for voice cloning
      run: |
        pip install "coqpit" "trainer>=0.0.32" "pysbd>=0.3.4" "inflect>=5.6.0" "unidecode>=1.3.2"
        pip install "TTS==0.21.2"
        python -c "from TTS.api import TTS" || (echo "::error::TTS import failed. Voice cloning will not work." && exit 1)

    - name: Install Demucs for stem splitting
      run: |
        pip install "demucs==4.0.1"
        python -c "import demucs.separate" || (echo "::warning::Demucs import failed. Stem splitting may not work." && true)

    - name: Install basic-pitch for MIDI generation
      run: |
        pip install "basic-pitch>=0.4.0"
        python -c "from basic_pitch.inference import predict" || (echo "::warning::basic-pitch import failed. MIDI generation may not work." && true)

    - name: Slim bundle (remove Sudachi if present)
      run: |
        pip uninstall -y SudachiDict-core SudachiPy sudachidict-core sudachipy 2>/dev/null || true
        
    - name: Install PyInstaller
      run: |
        pip install "pyinstaller>=6.0"

    # build/macos must never be deleted: AceForge.icns (app icon), codesign.sh, pyinstaller hooks
    - name: Check build/macos assets (icon, codesign)
      run: |
        if [ ! -f "build/macos/AceForge.icns" ]; then
          echo "::error::build/macos/AceForge.icns not found. build/macos/ must never be deleted."
          exit 1
        fi

    - name: Clean previous PyInstaller outputs
      run: |
        rm -rf dist/AceForge.app dist/CDMF build/AceForge

    - name: Build with PyInstaller
      run: |
        python -m PyInstaller CDMF.spec --clean --noconfirm

    - name: Set up app bundle executable
      run: |
        # CFBundleExecutable is "AceForge"; PyInstaller produces AceForge_bin. Copy so the app runs the real binary (native pywebview, no terminal).
        cp dist/AceForge.app/Contents/MacOS/AceForge_bin dist/AceForge.app/Contents/MacOS/AceForge
        chmod +x dist/AceForge.app/Contents/MacOS/AceForge
        
    - name: Code sign the app bundle
      run: |
        # Run the code signing script with ad-hoc signing (no certificate required for dev builds)
        # This prevents the "app is damaged" warning that requires sudo xattr -cr
        # For production releases, set MACOS_SIGNING_IDENTITY secret to your Developer ID
        chmod +x build/macos/codesign.sh
        ./build/macos/codesign.sh dist/AceForge.app
      env:
        MACOS_SIGNING_IDENTITY: ${{ secrets.MACOS_SIGNING_IDENTITY || '-' }}
        
    - name: Create DMG (macOS disk image)
      run: |
        # Create a temporary directory for DMG contents
        mkdir -p dmg_temp
        cp -R dist/AceForge.app dmg_temp/
        
        # Copy the .command file for easy launching
        cp AceForge.command dmg_temp/
        chmod +x dmg_temp/AceForge.command
        
        # Create Applications symlink for easy drag-and-drop install
        ln -s /Applications dmg_temp/Applications
        
        # Copy README for users
        cp .github/DMG_README.txt dmg_temp/README.txt
        
        # Create DMG
        hdiutil create -volname "AceForge" \
          -srcfolder dmg_temp \
          -ov -format UDZO \
          AceForge-macOS.dmg
          
    - name: Create ZIP archive (alternative distribution)
      run: |
        cd dist
        zip -r ../AceForge-macOS.zip AceForge.app
        cd ..
        
    - name: Calculate checksums
      run: |
        shasum -a 256 AceForge-macOS.dmg > checksums.txt
        shasum -a 256 AceForge-macOS.zip >> checksums.txt
        cat checksums.txt
        
    - name: Upload DMG artifact
      uses: actions/upload-artifact@v4
      with:
        name: AceForge-macOS-DMG
        path: AceForge-macOS.dmg
        
    - name: Upload to Release (if triggered by release)
      if: github.event_name == 'release'
      uses: softprops/action-gh-release@v1
      with:
        files: |
          AceForge-macOS.dmg
          AceForge-macOS.zip
          checksums.txt
```

### Key Differences from Templates

These are the **actual production scripts** from AceForge, not templates:

1. **App Name**: `AceForge` not `YourApp`
2. **Spec File**: `CDMF.spec` (actual spec file)
3. **Requirements**: `requirements_ace_macos.txt` (actual file)
4. **Dependencies**: Complete list including TTS, Demucs, basic-pitch, ACE-Step
5. **Optimizations**: Japanese dictionary removal, bundle slimming
6. **Caching**: Optional quick build flags for faster development
7. **UI Build**: React SPA built with Bun via `scripts/build_ui.sh`

These scripts are production-ready, battle-tested, and handle all edge cases including:
- Optional components (TTS, Demucs, basic-pitch)
- Build verification at each step
- Proper error handling and messages
- macOS-specific optimizations
- Code signing with multiple modes
- DMG creation with all assets

---

### Tools

- **PyInstaller**: `pip install pyinstaller`
- **PyWebView**: `pip install pywebview`
- **UPX**: `brew install upx`
- **Bun**: https://bun.sh (for modern web UI)

---

## Summary Checklist

When packaging a new Python app, follow these steps:

- [ ] Create entry point script with proper frozen app detection
- [ ] Write PyInstaller `.spec` file with all dependencies
- [ ] Generate app icon in multiple resolutions (.icns file)
- [ ] Create custom PyInstaller hooks for problematic packages
- [ ] Write entitlements.plist for security permissions
- [ ] Create code signing script
- [ ] Write automated build script
- [ ] Test local build
- [ ] Create DMG/ZIP distribution
- [ ] Set up CI/CD workflow for automated builds
- [ ] Test distribution on fresh macOS system

---

## License

This documentation is provided as a reference guide. Adapt it for your project's needs. For the complete working example, see the AceForge repository: https://github.com/audiohacking/AceForge

---

**Last Updated**: February 2026

**Maintained By**: AceForge Project

**Feedback**: For corrections or improvements to this guide, please open an issue or pull request in the AceForge repository.
