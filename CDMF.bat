::[Bat To Exe Converter]
::
::YAwzoRdxOk+EWAjk
::fBw5plQjdCyDJHqF+kYpDA5aSwGNMkavFbwfzufp6O+7sVkcQOs8RIza1LCXJu8B7UDbe5M6mHNZl6s=
::YAwzuBVtJxjWCl3EqQJgSA==
::ZR4luwNxJguZRRnk
::Yhs/ulQjdF+5
::cxAkpRVqdFKZSjk=
::cBs/ulQjdF+5
::ZR41oxFsdFKZSDk=
::eBoioBt6dFKZSDk=
::cRo6pxp7LAbNWATEpCI=
::egkzugNsPRvcWATEpCI=
::dAsiuh18IRvcCxnZtBJQ
::cRYluBh/LU+EWAnk
::YxY4rhs+aU+JeA==
::cxY6rQJ7JhzQF1fEqQJQ
::ZQ05rAF9IBncCkqN+0xwdVs0
::ZQ05rAF9IAHYFVzEqQJQ
::eg0/rx1wNQPfEVWB+kM9LVsJDGQ=
::fBEirQZwNQPfEVWB+kM9LVsJDGQ=
::cRolqwZ3JBvQF1fEqQJQ
::dhA7uBVwLU+EWDk=
::YQ03rBFzNR3SWATElA==
::dhAmsQZ3MwfNWATElA==
::ZQ0/vhVqMQ3MEVWAtB9wSA==
::Zg8zqx1/OA3MEVWAtB9wSA==
::dhA7pRFwIByZRRnk
::Zh4grVQjdCyDJHqF+kYpDA5aSwGNMkavFbwfzufp6O+7gWkwcqw6YIq7
::YB416Ek+ZG8=
::
::
::978f952a14a936cc963da21a135fa983
@echo off
setlocal
title Candy Dungeon Music Forge
color 0b

REM ---------------------------------------------------------------------------
REM  Candy Dungeon Music Forge - Bootstrap / Launcher (no block () usage)
REM ---------------------------------------------------------------------------

echo ---------------------------------------------
echo  Candy Dungeon Music Forge - Server Console
echo  This window must stay open while CDMF runs.
echo  Press Ctrl+C to stop the server.
echo ---------------------------------------------

REM App root = folder this BAT/EXE lives in (keep trailing backslash)
set "APP_DIR=%~dp0"

set "VENV_DIR=%APP_DIR%venv_ace"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "EMBED_PY=%APP_DIR%python_embed\python.exe"
set "REQ_FILE=%APP_DIR%requirements_ace.txt"
set "APP_SCRIPT=%APP_DIR%music_forge_ui.py"
set "LOADING_HTML=%APP_DIR%static\loading.html"
set "APP_URL=http://127.0.0.1:5056/"
set "CDMF_LYRICS_USE_GPU=1"

echo [CDMF] App dir : %APP_DIR%
echo [CDMF] VENV_PY : %VENV_PY%
echo [CDMF] EMBED_PY: %EMBED_PY%

REM ---------------------------------------------------------------------------
REM  Open loading page right away so user sees something nice
REM ---------------------------------------------------------------------------
if exist "%LOADING_HTML%" (
    echo [CDMF] Opening loading page in your default browser...
    start "" "%LOADING_HTML%"
) else (
    echo [CDMF] loading.html not found; open this URL in your browser:
    echo        %APP_URL%
)

REM ---------------------------------------------------------------------------
REM  Check for existing venv
REM ---------------------------------------------------------------------------
if exist "%VENV_PY%" goto launch_app

echo [CDMF] No venv_ace found, running one-time setup...

REM ---------------------------------------------------------------------------
REM  Sanity checks
REM ---------------------------------------------------------------------------
if not exist "%EMBED_PY%" goto no_embed_python
if not exist "%REQ_FILE%" goto no_requirements

REM ---------------------------------------------------------------------------
REM  Create venv_ace using bundled Python
REM ---------------------------------------------------------------------------
echo [CDMF] Creating virtual environment at:
echo         %VENV_DIR%
"%EMBED_PY%" -m venv "%VENV_DIR%"
if errorlevel 1 goto venv_create_failed

if not exist "%VENV_PY%" goto venv_python_missing

REM ---------------------------------------------------------------------------
REM  Install pip (if needed) and upgrade it
REM ---------------------------------------------------------------------------
echo [CDMF] Ensuring pip is available / up to date...
"%VENV_PY%" -m ensurepip --upgrade >nul 2>&1
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto pip_upgrade_failed

REM ---------------------------------------------------------------------------
REM  Install app requirements into venv_ace (excluding ace_step / torch)
REM ---------------------------------------------------------------------------
echo [CDMF] Installing dependencies from requirements_ace.txt...
"%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 goto requirements_install_failed

echo [CDMF] Installing audio-separator (ignoring beartype's version constraint)...
"%VENV_PY%" -m pip install "audio-separator==0.40.0" --no-deps
if errorlevel 1 goto requirements_install_failed

echo [CDMF] Installing py3langid (ignoring its numpy>=2.0.0 requirement)...
"%VENV_PY%" -m pip install "py3langid==0.3.0" --no-deps
if errorlevel 1 goto requirements_install_failed

REM ---------------------------------------------------------------------------
REM  Install ACE-Step from GitHub (WITHOUT touching deps like numpy/torch)
REM ---------------------------------------------------------------------------
echo [CDMF] Installing ACE-Step from GitHub (no deps; using our pinned stack)...
"%VENV_PY%" -m pip install "git+https://github.com/ace-step/ACE-Step.git" --no-deps
if errorlevel 1 goto ace_step_install_failed

REM ---------------------------------------------------------------------------
REM  Install PyTorch CUDA stack from official index
REM ---------------------------------------------------------------------------
echo [CDMF] Installing PyTorch (CUDA 12.6)...
"%VENV_PY%" -m pip install ^
  "torch==2.9.1+cu126" ^
  "torchvision==0.24.1+cu126" ^
  "torchaudio==2.9.1+cu126" ^
  --index-url https://download.pytorch.org/whl/cu126

if errorlevel 1 goto torch_install_failed

echo [CDMF] venv_ace setup complete.

REM ---------------------------------------------------------------------------
REM  Launch the app
REM ---------------------------------------------------------------------------
:launch_app
if not exist "%APP_SCRIPT%" goto app_script_missing

echo  
echo ---------------------------------------------
echo [CDMF] Starting Candy Music Forge UI...
echo [CDMF] THIS MAY TAKE A FEW MOMENTS IF YOU'VE NEVER BOOTED UP BEFORE. PLEASE WAIT.
echo [CDMF] (Close this window to stop the server.)
"%VENV_PY%" "%APP_SCRIPT%"
goto :eof

REM ---------------------------------------------------------------------------
REM  Error handlers
REM ---------------------------------------------------------------------------
:no_embed_python
echo [ERROR] Bundled Python not found at:
echo         %EMBED_PY%
echo Make sure python_embed\python.exe is present next to CDMF.bat/CDMF.exe.
goto fail

:no_requirements
echo [ERROR] requirements_ace.txt not found at:
echo         %REQ_FILE%
echo Cannot install dependencies without this file.
goto fail

:venv_create_failed
echo [ERROR] Failed to create virtual environment with:
echo         "%EMBED_PY%" -m venv "%VENV_DIR%"
goto fail

:venv_python_missing
echo [ERROR] venv Python not found at:
echo         %VENV_PY%
goto fail

:pip_upgrade_failed
echo [ERROR] Failed to upgrade pip in venv.
goto fail

:requirements_install_failed
echo [ERROR] pip install -r requirements_ace.txt failed.
goto fail

:ace_step_install_failed
echo [ERROR] Failed to install ACE-Step from GitHub:
echo         git+https://github.com/ace-step/ACE-Step.git
echo You can try installing it manually inside the venv:
echo         "%VENV_PY%" -m pip install "git+https://github.com/ace-step/ACE-Step.git"
goto fail

:torch_install_failed
echo [ERROR] Failed to install PyTorch CUDA wheels from:
echo         https://download.pytorch.org/whl/cu126
echo You can try installing them manually inside the venv, for example:
echo         "%VENV_PY%" -m pip install torch torchvision torchaudio ^
  --index-url https://download.pytorch.org/whl/cu126
goto fail

:app_script_missing
echo [ERROR] Cannot find app script:
echo         %APP_SCRIPT%
goto fail

:fail
echo.
echo [CDMF] Launch failed. See error messages above.
echo Press any key to close this window . . .
pause >nul
exit /b 1
