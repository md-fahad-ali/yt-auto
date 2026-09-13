"""Cross-platform OS wake registration + sleep prevention.

Supports macOS (pmset), Windows (schtasks), Linux (systemd timer).
Falls back gracefully to the catch-up scheduler when wake can't be set.
"""
import logging
import platform
import shutil
import subprocess
from datetime import datetime, timedelta

logger = logging.getLogger("yt-auto.wake")

TASK_NAME = "YTAutoStudioWake"


def get_platform() -> str:
    s = platform.system()
    if s == "Darwin":
        return "macos"
    elif s == "Windows":
        return "windows"
    elif s == "Linux":
        return "linux"
    return "unknown"


def _wake_time(hhmm: str, lead_minutes: int = 5) -> str:
    hh, mm = int(hhmm[:2]), int(hhmm[3:])
    total = hh * 60 + mm - lead_minutes
    if total < 0:
        total += 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def register_wake(hhmm: str) -> dict:
    """Register an OS-level daily wake at `lead_minutes` before hhmm.
    Returns {"ok": bool, "method": str, "detail": str, "platform": str}."""
    p = get_platform()
    wake = _wake_time(hhmm)
    result = {"platform": p, "wake_time": wake, "method": "", "detail": "", "ok": False}

    try:
        if p == "macos":
            r = _macos(wake)
        elif p == "windows":
            r = _windows(wake)
        elif p == "linux":
            r = _linux(wake)
        else:
            r = {"ok": False, "detail": f"unsupported platform: {p}"}
        result.update(r)
    except Exception as e:
        result.update({"ok": False, "detail": f"error: {e}"})

    if not result["ok"]:
        result["detail"] += " — catch-up scheduler still guarantees the run"
    logger.info(f"wake registration: {result}")
    return result


def unregister_wake() -> dict:
    p = get_platform()
    try:
        if p == "macos":
            subprocess.run(["pmset", "repeat", "cancel"], timeout=15, capture_output=True)
            return {"ok": True, "detail": "cleared"}
        elif p == "windows":
            subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"],
                           timeout=15, capture_output=True)
            return {"ok": True, "detail": "cleared"}
        elif p == "linux":
            subprocess.run(["systemctl", "--user", "disable", "--now", f"{TASK_NAME}.timer"],
                           timeout=15, capture_output=True)
            return {"ok": True, "detail": "cleared"}
    except Exception as e:
        return {"ok": False, "detail": str(e)}
    return {"ok": False, "detail": "unsupported"}


# ── Platform implementations ──────────────────────────────────────────

def _macos(wake: str) -> dict:
    if not shutil.which("pmset"):
        return {"ok": False, "method": "pmset", "detail": "pmset not found"}
    script = (f'do shell script "pmset repeat wakeorpoweron MTWRFSU {wake}" '
              f'with administrator privileges')
    r = subprocess.run(["osascript", "-e", script], timeout=90, capture_output=True, text=True)
    if r.returncode == 0:
        return {"ok": True, "method": "pmset", "detail": f"Mac wakes daily at {wake}"}
    return {"ok": False, "method": "pmset", "detail": f"admin declined or error: {r.stderr.strip()[:80]}"}


def _windows(wake: str) -> dict:
    if not shutil.which("schtasks"):
        return {"ok": False, "method": "schtasks", "detail": "schtasks not found"}

    _enable_wake_timers()

    cmd = ["schtasks", "/create", "/tn", TASK_NAME, "/tr", "cmd /c exit",
           "/sc", "daily", "/st", wake, "/rl", "highest", "/f",
           "/wkst", ""]  # /wkst for all workstations
    r = subprocess.run(cmd, timeout=30, capture_output=True, text=True)
    if r.returncode == 0:
        _set_wake_flag()
        return {"ok": True, "method": "schtasks",
                "detail": f"Windows wakes daily at {wake} (Task Scheduler)"}
    return {"ok": False, "method": "schtasks", "detail": f"schtasks error: {r.stderr.strip()[:80]}"}


def _enable_wake_timers():
    try:
        subprocess.run(["powercfg", "/setacvalueindex", "SCHEME_CURRENT",
                        "SUB_SLEEP", "RTCWAKE", "1"],
                       timeout=15, capture_output=True)
        subprocess.run(["powercfg", "/setdcvalueindex", "SCHEME_CURRENT",
                        "SUB_SLEEP", "RTCWAKE", "1"],
                       timeout=15, capture_output=True)
        subprocess.run(["powercfg", "/setactive", "SCHEME_CURRENT"],
                       timeout=15, capture_output=True)
    except Exception:
        pass


def _set_wake_flag():
    try:
        import xml.etree.ElementTree as ET
        query = subprocess.run(["schtasks", "/query", "/tn", TASK_NAME, "/xml"],
                               timeout=15, capture_output=True, text=True)
        if query.returncode == 0:
            xml = query.stdout.replace("b'<?xml", "<?xml").replace("'", "")
            root = ET.fromstring(xml.strip())
            ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
            for settings in root.findall(".//t:Settings", ns):
                wake = ET.SubElement(settings, f"{{{ns['t']}}}WakeToRun")
                wake.text = "true"
            modified = ET.tostring(root, encoding="unicode")
            subprocess.run(["schtasks", "/create", "/tn", TASK_NAME, "/xml",
                            modified.replace("\n", "")],
                           timeout=15, capture_output=True, text=True)
    except Exception:
        pass


def _linux(wake: str) -> dict:
    if shutil.which("systemctl"):
        unit = f"""[Unit]
Description=YT Auto Studio daily wake trigger

[Timer]
OnCalendar=*-*-* {wake}:00
WakeSystem=true
Persistent=true

[Install]
WantedBy=timers.target"""
        try:
            import pathlib
            d = pathlib.Path.home() / ".config" / "systemd" / "user"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{TASK_NAME}.timer").write_text(unit)
            (d / f"{TASK_NAME}.service").write_text(
                "[Unit]\nDescription=YT Auto Studio wake\n"
                "[Service]\nType=oneshot\nExecStart=/bin/true\n")
            subprocess.run(["systemctl", "--user", "daemon-reload"],
                           timeout=15, capture_output=True)
            subprocess.run(["systemctl", "--user", "enable", "--now", f"{TASK_NAME}.timer"],
                           timeout=15, capture_output=True)
            return {"ok": True, "method": "systemd-timer",
                    "detail": f"Linux wakes daily at {wake} (systemd WakeSystem)"}
        except Exception as e:
            return {"ok": False, "method": "systemd-timer", "detail": str(e)[:80]}

    if shutil.which("rtcwake"):
        return {"ok": False, "method": "rtcwake",
                "detail": "rtcwake is one-shot (not repeating) — catch-up will handle it"}

    return {"ok": False, "method": "none", "detail": "no systemd or rtcwake found"}


# ── Sleep prevention (used by the batch worker) ──────────────────────

def prevent_sleep() -> str | None:
    """Best-effort sleep prevention. Returns a handle to release, or None."""
    p = get_platform()
    try:
        if p == "macos":
            r = subprocess.Popen(["caffeinate", "-i", "-w", str(_get_pid())],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"caffeinate:{r.pid}"
        elif p == "windows":
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            return "winapi:SetThreadExecutionState"
        elif p == "linux":
            systemd_inhibit = shutil.which("systemd-inhibit")
            if systemd_inhibit:
                r = subprocess.Popen([systemd_inhibit, "--what=sleep",
                                      "--who=YT Auto Studio",
                                      "--why=batch upload in progress",
                                      "sleep", "infinity"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"systemd-inhibit:{r.pid}"
    except Exception as e:
        logger.warning(f"prevent_sleep failed: {e}")
    return None


def allow_sleep(handle: str | None):
    if not handle:
        return
    try:
        if handle.startswith(("caffeinate:", "systemd-inhibit:")):
            pid = int(handle.split(":")[1])
            import os, signal
            os.kill(pid, signal.SIGTERM)
        elif handle == "winapi:SetThreadExecutionState":
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:
        pass


def _get_pid() -> int:
    import os
    return os.getpid()
