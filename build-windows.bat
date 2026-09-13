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
echo Missing Python / Node.js / pnpm? It installs them automatically.
echo.
echo ============================================
pause

echo.
echo [1/5] Checking prerequisites...

python --version >nul 2>&1
if %errorlevel% neq 0 call :install_python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python could not be installed automatically.
    echo Install from https://python.org and CHECK "Add Python to PATH".
    pause & exit /b 1
)

node --version >nul 2>&1
if %errorlevel% neq 0 call :install_node
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js could not be installed automatically.
    echo Install from https://nodejs.org and re-run this script.
    pause & exit /b 1
)

where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo pnpm not found - installing it now...
    call npm install -g pnpm
)
where pnpm >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: pnpm could not be installed automatically. Run: npm install -g pnpm
    pause & exit /b 1
)
echo OK: Python, Node.js, and pnpm ready.

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
goto :eof

:install_python
echo Python not found - installing Python 3.12 (a UAC prompt may appear - click Yes)...
where winget >nul 2>&1
if %errorlevel% equ 0 (
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
) else (
    echo winget not available - downloading the official installer...
    curl -L -o "%TEMP%\python-installer.exe" https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe
    "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
)
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%"
goto :eof

:install_node
echo Node.js not found - installing Node.js LTS (a UAC prompt may appear - click Yes)...
where winget >nul 2>&1
if %errorlevel% equ 0 (
    winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
) else (
    echo winget not available - downloading the official installer...
    curl -L -o "%TEMP%\node-installer.msi" https://nodejs.org/dist/v20.18.1/node-v20.18.1-x64.msi
    msiexec /i "%TEMP%\node-installer.msi" /qn
)
set "PATH=%PATH%;C:\Program Files\nodejs;%LOCALAPPDATA%\Programs\nodejs"
goto :eof
