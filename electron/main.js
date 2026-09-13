const { app, BrowserWindow, Tray, Menu, shell, powerSaveBlocker } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

const ROOT = path.join(__dirname, "..");
const PORT = 8000;
let win = null;
let tray = null;
let backend = null;
let backendReady = false;

function startBackend() {
  const isWin = process.platform === "win32";
  const py = isWin
    ? path.join(ROOT, ".venv", "Scripts", "python.exe")
    : path.join(ROOT, ".venv", "bin", "python");
  const bin = path.join(ROOT, "dist-backend",
    isWin ? "yt-auto-backend.exe" : "yt-auto-backend");
  const usePython = fs.existsSync(py);
  const cmd = usePython ? py : bin;
  const args = usePython ? ["app.py"] : [];
  console.log(`starting backend: ${cmd} ${args.join(" ")}`);
  backend = spawn(cmd, args, {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env },
    shell: isWin,
  });
  backend.stdout.on("data", (d) => process.stdout.write(`[py] ${d}`));
  backend.stderr.on("data", (d) => process.stderr.write(`[py] ${d}`));
  backend.on("error", (e) => console.error(`backend spawn error: ${e}`));
  backend.on("exit", (code) => {
    console.log(`backend exited (${code})`);
    if (!app.isQuitting && !backendReady) {
      setTimeout(() => { if (!app.isQuitting) startBackend(); }, 1500);
    }
  });
}

function ping() {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${PORT}/health`, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

async function waitBackend() {
  if (await ping()) { backendReady = true; return true; }
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    if (await ping()) { backendReady = true; return true; }
  }
  return false;
}

function setupAppMenu() {
  const template = [
    {
      label: "Edit",
      submenu: [
        { role: "undo" }, { role: "redo" }, { type: "separator" },
        { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "selectAll" }
      ]
    },
    {
      label: "View",
      submenu: [
        { role: "reload", accelerator: "CmdOrCtrl+R" },
        { role: "forceReload", accelerator: "CmdOrCtrl+Shift+R" },
        { role: "toggleDevTools", accelerator: process.platform === "darwin" ? "Alt+Command+I" : "Ctrl+Shift+I" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" }
      ]
    },
    {
      label: "Window",
      submenu: [
        { role: "minimize" },
        { role: "zoom" },
        { role: "close" }
      ]
    }
  ];

  if (process.platform === "darwin") {
    template.unshift({
      label: app.name,
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "services" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { role: "unhide" },
        { type: "separator" },
        { role: "quit" }
      ]
    });
  }

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280, height: 820, minWidth: 400, minHeight: 500,
    title: "YT Auto Studio", backgroundColor: "#090a0f",
    webPreferences: { contextIsolation: true, nodeIntegration: false },
  });
  win.loadURL(`http://localhost:${PORT}/dashboard/`);

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(`http://localhost:${PORT}`) && !url.startsWith("about:")) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  const { session } = require("electron");
  session.defaultSession.webRequest.onBeforeRequest(
    { urls: ["https://accounts.google.com/*", "https://oauth2.googleapis.com/*"] },
    (details, callback) => {
      shell.openExternal(details.url);
      callback({ cancel: true });
    }
  );

  win.on("close", (e) => {
    if (!app.isQuitting && tray) { e.preventDefault(); win.hide(); }
  });
}

function createTray() {
  const iconPath = [path.join(__dirname, "icon.png"), path.join(__dirname, "icon@2x.png")]
    .find((p) => fs.existsSync(p));
  if (!iconPath) return;
  tray = new Tray(iconPath);
  tray.setToolTip("YT Auto Studio");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Studio", click: () => (win ? win.show() : createWindow()) },
    { label: "Simple Upload Page", click: () => { if (!win) createWindow(); win.loadURL(`http://localhost:${PORT}/`); win.show(); } },
    { label: "Reload Page", click: () => { if (win) win.webContents.reloadIgnoringCache(); } },
    { label: "Quit", click: () => { app.isQuitting = true; app.quit(); } },
  ]));
  tray.on("click", () => (win && !win.isVisible() ? win.show() : win.focus()));
}

function setupDistWatcher() {
  const distPath = path.join(ROOT, "web", "dist");
  if (fs.existsSync(distPath)) {
    let reloadTimeout = null;
    fs.watch(distPath, { recursive: true }, () => {
      clearTimeout(reloadTimeout);
      reloadTimeout = setTimeout(() => {
        if (win && !win.isDestroyed()) {
          console.log("⚡ [Electron] web/dist changed -> reloading window");
          win.webContents.reloadIgnoringCache();
        }
      }, 300);
    });
  }
}

function watchBatchForSleep() {
  let blockerId = null;
  setInterval(async () => {
    try {
      const res = await fetch(`http://localhost:${PORT}/api/batch/status`);
      const st = await res.json();
      if (st.running && blockerId === null) {
        blockerId = powerSaveBlocker.start("prevent-app-suspension");
        console.log("🛡 powerSaveBlocker ON (batch running — no sleep mid-upload)");
      } else if (!st.running && blockerId !== null && powerSaveBlocker.isStarted(blockerId)) {
        powerSaveBlocker.stop(blockerId);
        blockerId = null;
        console.log("powerSaveBlocker off (batch done — sleep allowed)");
      }
    } catch { /* backend not up yet */ }
  }, 15000);
}

app.whenReady().then(async () => {
  try {
    setupAppMenu();
    app.setLoginItemSettings({ openAtLogin: true });   // auto-start after reboot
    const isUp = await ping();
    if (!isUp) {
      startBackend();
    } else {
      backendReady = true;
    }
    const ok = await waitBackend();
    createWindow();
    if (!ok) {
      win.loadURL("data:text/html,<h2 style='font-family:sans-serif;padding:40px'>Backend failed to start — check the terminal log</h2>");
      return;
    }
    createTray();
    setupDistWatcher();
    watchBatchForSleep();
  } catch (e) {
    console.error("startup error:", e);
  }
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (backend && !backend.killed) backend.kill();
});

app.on("window-all-closed", (e) => e.preventDefault());
