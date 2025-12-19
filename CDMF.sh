#!/bin/bash
# ---------------------------------------------------------------------------
#  AceForge - Bootstrap / Launcher for macOS
# ---------------------------------------------------------------------------

set -e  # Exit on error

echo "---------------------------------------------"
echo " AceForge - Server Console"
echo " This window must stay open while AceForge runs."
echo " Press Ctrl+C to stop the server."
echo "---------------------------------------------"

# App root = folder this script lives in
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

VENV_DIR="${APP_DIR}/venv_ace"
VENV_PY="${VENV_DIR}/bin/python"
REQ_FILE="${APP_DIR}/requirements_ace_macos.txt"
APP_SCRIPT="${APP_DIR}/music_forge_ui.py"
LOADING_HTML="${APP_DIR}/static/loading.html"
APP_URL="http://127.0.0.1:5056/"

# Check if we want to use GPU for lyrics processing
export CDMF_LYRICS_USE_GPU=1

echo "[AceForge] App dir : ${APP_DIR}"
echo "[AceForge] VENV_PY : ${VENV_PY}"

# ---------------------------------------------------------------------------
#  Open loading page right away so user sees something nice
# ---------------------------------------------------------------------------
if [ -f "${LOADING_HTML}" ]; then
    echo "[AceForge] Opening loading page in your default browser..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open "${LOADING_HTML}" 2>/dev/null || echo "[AceForge] Could not open browser automatically"
    else
        xdg-open "${LOADING_HTML}" 2>/dev/null || echo "[AceForge] Could not open browser automatically"
    fi
else
    echo "[AceForge] loading.html not found; open this URL in your browser:"
    echo "       ${APP_URL}"
fi

# ---------------------------------------------------------------------------
#  Check for existing venv
# ---------------------------------------------------------------------------
if [ -f "${VENV_PY}" ]; then
    echo "[AceForge] Found existing venv_ace, launching app..."
    exec "${VENV_PY}" "${APP_SCRIPT}"
fi

echo "[AceForge] No venv_ace found, running one-time setup..."

# ---------------------------------------------------------------------------
#  Sanity checks
# ---------------------------------------------------------------------------
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 not found in PATH"
    echo "Please install Python 3.10 or later:"
    echo "  - Using Homebrew: brew install python@3.10"
    echo "  - Or download from: https://www.python.org/downloads/"
    exit 1
fi

PYTHON_CMD=$(command -v python3)
PYTHON_VERSION=$("${PYTHON_CMD}" --version 2>&1 | awk '{print $2}')
echo "[AceForge] Found Python ${PYTHON_VERSION} at ${PYTHON_CMD}"

if [ ! -f "${REQ_FILE}" ]; then
    echo "[ERROR] requirements_ace_macos.txt not found at:"
    echo "        ${REQ_FILE}"
    echo "Cannot install dependencies without this file."
    exit 1
fi

# ---------------------------------------------------------------------------
#  Create venv_ace using system Python
# ---------------------------------------------------------------------------
echo "[AceForge] Creating virtual environment at:"
echo "        ${VENV_DIR}"
"${PYTHON_CMD}" -m venv "${VENV_DIR}"

if [ ! -f "${VENV_PY}" ]; then
    echo "[ERROR] venv Python not found at:"
    echo "        ${VENV_PY}"
    exit 1
fi

# ---------------------------------------------------------------------------
#  Install pip (if needed) and upgrade it
# ---------------------------------------------------------------------------
echo "[AceForge] Ensuring pip is available / up to date..."
"${VENV_PY}" -m ensurepip --upgrade > /dev/null 2>&1 || true
"${VENV_PY}" -m pip install --upgrade pip

# ---------------------------------------------------------------------------
#  Install app requirements into venv_ace
# ---------------------------------------------------------------------------
echo "[AceForge] Installing dependencies from requirements_ace_macos.txt..."
"${VENV_PY}" -m pip install -r "${REQ_FILE}"

# Note: These packages have specific version conflicts with other dependencies
# and need to be installed with --no-deps to avoid breaking the environment
echo "[AceForge] Installing audio-separator (--no-deps due to beartype version conflict)..."
"${VENV_PY}" -m pip install "audio-separator==0.40.0" --no-deps

echo "[AceForge] Installing py3langid (--no-deps due to numpy>=2.0.0 requirement conflict)..."
"${VENV_PY}" -m pip install "py3langid==0.3.0" --no-deps

# ---------------------------------------------------------------------------
#  Install ACE-Step from GitHub (WITHOUT touching deps like numpy/torch)
# ---------------------------------------------------------------------------
echo "[AceForge] Installing ACE-Step from GitHub (no deps; using our pinned stack)..."
"${VENV_PY}" -m pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps

echo "[AceForge] venv_ace setup complete."

# ---------------------------------------------------------------------------
#  Launch the app
# ---------------------------------------------------------------------------
if [ ! -f "${APP_SCRIPT}" ]; then
    echo "[ERROR] Cannot find app script:"
    echo "        ${APP_SCRIPT}"
    exit 1
fi

echo ""
echo "---------------------------------------------"
echo "[AceForge] Starting AceForge UI..."
echo "[AceForge] THIS MAY TAKE A FEW MOMENTS IF YOU'VE NEVER BOOTED UP BEFORE. PLEASE WAIT."
echo "[AceForge] (Close this window to stop the server.)"
exec "${VENV_PY}" "${APP_SCRIPT}"
