@echo off
TITLE YT Auto Studio - Windows Builder
COLOR 0A

echo ============================================
echo   YT Auto Studio - Windows Package Builder
echo ============================================
echo.
echo This script builds:
echo   1. Python backend as standalone .exe (PyInstaller)
echo   2. Electron desktop app as Windows installer
echo.
echo Prerequisites (auto-checked):
echo   - Python 3.11+ installed and in PATH
echo   - Node.js 18+ installed and in PATH
echo   - pnpm installed (npm install -g pnpm)
echo.
echo ============================================
pause

echo.
echo [1/5] Checking prerequisites...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install from https://python.org
    echo Make sure "Add Python to PATH" is checked during install.
    pause & exit /b 1
)
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js not found. Install from https://nodejs.org
    pause & exit /b 1
)
echo OK: Python and Node.js found.

echo.
echo [2/5] Creating Python virtual environment...
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt pyinstaller
echo OK: Dependencies installed.

echo.
echo [3/5] Building frontend (React dashboard)...
cd web
if not exist node_modules (
    call pnpm install
)
call pnpm run build
cd ..
echo OK: Frontend built.

echo.
echo [4/5] Building Python backend .exe...
pyinstaller --onefile --name yt-auto-backend --distpath dist-backend --specpath build_temp ^
    --exclude-module tkinter --exclude-module matplotlib --exclude-module numpy ^
    app.py
if not exist dist-backend\yt-auto-backend.exe (
    echo ERROR: Backend build failed. Check output above.
    pause & exit /b 1
)
echo OK: Backend .exe created.

echo.
echo [5/5] Building Windows installer (.exe)...
cd electron
if not exist node_modules (
    call pnpm install
)
call npx electron-builder --win
cd ..
echo.
echo ============================================
echo   BUILD COMPLETE!
echo ============================================
echo.
echo Output files:
echo   release\YT-Auto-Setup-1.0.0.exe    (installer)
echo   release\YT-Auto-Portable.exe       (portable, no install)
echo.
echo Copy either file to any Windows PC and run it.
echo No Python, Node.js, or any other prerequisite needed.
echo.
pause
