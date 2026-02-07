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

### PyWebView Integration

For native window UI with web technologies:

**Flask + PyWebView Setup:**

```python
import webview
from flask import Flask
import threading
import time

def create_app():
    app = Flask(__name__)
    
    @app.route('/')
    def index():
        return """
        <html>
            <head><title>YourApp</title></head>
            <body>
                <h1>Hello from PyWebView!</h1>
            </body>
        </html>
        """
    
    return app

def start_server(app, port=5000):
    """Start Flask server in background thread"""
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)

def main():
    app = create_app()
    
    # Start Flask in daemon thread
    server_thread = threading.Thread(
        target=lambda: start_server(app, 5000),
        daemon=True
    )
    server_thread.start()
    
    # Wait for server to start
    time.sleep(1)
    
    # Create native window
    window = webview.create_window(
        'YourApp',
        'http://127.0.0.1:5000',
        width=1200,
        height=800,
        resizable=True,
        frameless=False,
        easy_drag=True,
    )
    
    # Start webview (blocks until window closes)
    webview.start()

if __name__ == '__main__':
    main()
```

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
