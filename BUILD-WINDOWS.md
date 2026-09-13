# 📦 Building YT Auto Studio for Windows

## Quick Start (on a Windows PC)

1. Copy the entire `yt-auto` folder to a Windows PC
2. Install [Python](https://python.org) (check "Add to PATH")
3. Install [Node.js](https://nodejs.org) (LTS)
4. Double-click `build-windows.bat`
5. Wait ~5 minutes → `release\YT-Auto-Setup-1.0.0.exe` is ready

## What the script does

```
build-windows.bat
├── [1/5] Checks Python + Node.js are installed
├── [2/5] Creates .venv + installs all Python dependencies
├── [3/5] Builds React dashboard (pnpm → web/dist/)
├── [4/5] PyInstaller → dist-backend/yt-auto-backend.exe (standalone Python)
└── [5/5] electron-builder → release/YT-Auto-Setup-1.0.0.exe
```

## Output files

| File | Size (approx) | Description |
|---|---|---|
| `YT-Auto-Setup-1.0.0.exe` | ~120 MB | Full installer — desktop shortcut, start menu |
| `YT-Auto-Portable.exe` | ~120 MB | Single file, no install needed — just double-click |

## What's bundled inside

```
YT-Auto-Setup.exe
├── Electron runtime (Chromium + Node.js)  ~80 MB
├── yt-auto-backend.exe (Python backend)   ~40 MB
│   ├── FastAPI + uvicorn
│   ├── Google API libraries
│   └── All research/analytics modules
├── web/dist/ (React dashboard)             ~2 MB
└── .env (OpenRouter API key)
```

## After installing on a Windows PC

1. Double-click the desktop shortcut "YT Auto Studio"
2. The app starts the backend automatically (no console window visible)
3. Dashboard loads → done
4. Close window = minimize to tray (schedules keep running)
5. Quit from tray = clean shutdown

## First-time setup on Windows

Same as Mac — put your `client_secret.json` next to the installed `app.py` (or in the install directory), or re-authenticate channels via the `+` button.

## Cross-compiling from Mac (advanced)

Electron can cross-compile Windows installers from Mac, but **PyInstaller cannot** build Windows .exe from macOS. If you need to automate this:

1. Use GitHub Actions / CI with a Windows runner
2. Or use a Windows VM (Parallels, Boot Camp, VirtualBox)
3. Or use Docker with Wine (fragile, not recommended)

The `build-windows.bat` script works on any Windows PC — that's the reliable path.
