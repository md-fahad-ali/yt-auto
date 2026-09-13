"""Grandma Uploads — one-page YouTube uploader. Localhost MVP.

Run:  python app.py   →  http://localhost:8000
"""
import json
import os
import sqlite3
import sys
import tempfile
import threading
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

if getattr(sys, "frozen", False):
    EXE_DIR = Path(sys.executable).parent
    # ponytail: frozen apps must never write into the install dir (Program Files is read-only)
    BASE = Path(os.environ.get("APPDATA") or Path.home()) / "YTAutoStudio"
    BASE.mkdir(parents=True, exist_ok=True)
    os.environ["YT_AUTO_DATA"] = str(BASE)
else:
    BASE = Path(__file__).parent
    EXE_DIR = BASE


def _find(name: str) -> Path:
    """Search writable data dir first, then next to the frozen exe."""
    for p in (BASE / name, EXE_DIR / name, EXE_DIR.parent / name):
        if p.exists():
            return p
    return BASE / name


for _line in (_find(".env").read_text().splitlines() if _find(".env").exists() else []):
    if "=" in _line and not _line.startswith("#"):
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())
TOKENS_DIR = BASE / "tokens"
LOG_FILE = BASE / "uploads_log.json"
CLIENT_SECRET = _find("client_secret.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
DAILY_CAP = 5  # ponytail: hard cap per channel/day — far under API limit, no burst patterns

TOKENS_DIR.mkdir(exist_ok=True)

app = FastAPI()
app.secret_key = os.environ.get("SESSION_SECRET", "dev-only-localhost-secret-key-12345")
# ponytail: plain cookie session for localhost MVP — sign cookies before any real deploy

from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(
    SessionMiddleware,
    secret_key=app.secret_key,
    max_age=3600 * 24 * 30,  # 30 days session
    same_site="lax",
    https_only=False,
)


# ---------- helpers ----------

def load_log() -> dict:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return {}


def save_log(log: dict):
    LOG_FILE.write_text(json.dumps(log, indent=2))


def today_count(channel_id: str) -> int:
    log = load_log()
    return len([e for e in log.get("uploads", []) if e["channel"] == channel_id and e["date"] == date.today().isoformat()])


def token_path(channel_id: str) -> Path:
    safe = "".join(c for c in channel_id if c.isalnum() or c in "-_")
    return TOKENS_DIR / f"{safe}.json"


def get_active_channel(request: Request):
    """Retrieve active channel ID & Title from session, or auto-load from authstore."""
    channel_id = request.session.get("channel_id")
    channel_title = request.session.get("channel_title")
    if channel_id and channel_title:
        return channel_id, channel_title

    import authstore
    for cid, info in sorted(authstore.load_all().items(),
                            key=lambda kv: kv[1].get("updated_at", ""), reverse=True):
        try:
            creds = Credentials.from_authorized_user_info(info)
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
                authstore.save(cid, creds)
            yt = build("youtube", "v3", credentials=creds)
            me = yt.channels().list(part="snippet", mine=True).execute()
            items = me.get("items", [])
            title = items[0]["snippet"]["title"] if items else cid
            request.session["channel_id"] = cid
            request.session["channel_title"] = title
            return cid, title
        except Exception:
            continue
    return None, None


def get_youtube(channel_id: str):
    import authstore
    info = authstore.load(channel_id)
    if not info:
        raise HTTPException(401, "Not signed in")
    creds = Credentials.from_authorized_user_info(info)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
        authstore.save(channel_id, creds)
    return build("youtube", "v3", credentials=creds)


# ---------- auth ----------

_oauth_store = {"state": None, "verifier": None}


@app.get("/login")
def login(request: Request, next: str = "/"):
    if not CLIENT_SECRET.exists():
        return HTMLResponse("<h2>⚠️ Missing client_secret.json — see SETUP.md (developer does this once)</h2>", 503)
    if not next.startswith("/"):
        next = "/"
    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET), scopes=SCOPES)
    flow.redirect_uri = "http://localhost:8000/callback"
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
    _oauth_store["state"] = state
    _oauth_store["verifier"] = flow.code_verifier
    return RedirectResponse(auth_url)


@app.get("/callback")
def callback(request: Request):
    flow = Flow.from_client_secrets_file(str(CLIENT_SECRET), scopes=SCOPES)
    flow.redirect_uri = "http://localhost:8000/callback"
    if _oauth_store["verifier"]:
        flow.code_verifier = _oauth_store["verifier"]
    flow.fetch_token(code=request.query_params.get("code"))
    creds = flow.credentials

    yt = build("youtube", "v3", credentials=creds)
    me = yt.channels().list(part="snippet", mine=True).execute()
    items = me.get("items", [])
    if not items:
        return HTMLResponse("<h2>No YouTube channel on this Google account. Pick the account that owns the channel.</h2>", 400)
    channel_id, title = items[0]["id"], items[0]["snippet"]["title"]

    import authstore as _asa
    _asa.save(channel_id, creds, name=title)
    request.session["channel_id"] = channel_id
    request.session["channel_title"] = title

    safe_title = title.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Login Successful</title></head>
<body style="font-family:sans-serif;background:#f0fdf4;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">
<div style="text-align:center;padding:40px;background:#fff;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.1);max-width:420px">
<div style="font-size:56px;margin-bottom:12px">&#10004;&#65039;</div>
<h1 style="color:#16a34a;margin:0 0 8px;font-size:24px">Channel Connected!</h1>
<p style="color:#333;font-size:18px;margin:12px 0"><b>{safe_title}</b></p>
<p style="color:#666;font-size:14px;margin:16px 0">Return to <b>YT Auto Studio</b> — your channel is now connected.</p>
<p style="color:#999;font-size:13px">You can close this browser tab now.</p>
</div>
<script>setTimeout(function(){{try{{window.close()}}catch(e){{}}}},3000)</script>
</body></html>""")


@app.get("/logout")
def logout(request: Request):
    channel_id = request.session.get("channel_id")
    if channel_id:
        tp = token_path(channel_id)
        if tp.exists():
            tp.unlink(missing_ok=True)
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


# ---------- upload ----------

@app.get("/api/ideas")
def ideas(topic: str):
    topic = (topic or "").strip()
    if not topic or len(topic) > 80:
        raise HTTPException(400, "Give a topic (1-80 characters)")
    try:
        from research import viral_brief_data, canonical_topic
        topic = canonical_topic(topic)
        d = viral_brief_data(topic, days=30)
        d["source"] = "live"
        return d
    except Exception as e:
        raise HTTPException(502, f"Idea lookup failed: {e}")


@app.get("/api/compare")
def api_compare(topic: str):
    topic = (topic or "").strip()
    if not topic or len(topic) > 80:
        raise HTTPException(400, "Give a topic (1-80 characters)")
    from index import index_videos, aggregate, con
    from research import viral_brief_data, canonical_topic
    t = canonical_topic(topic)
    live = viral_brief_data(t, days=30)
    vids = index_videos(con(), t)
    idx = aggregate(vids[:15]) if vids else {"tags": live.get("tags", [])[:8]}
    lt, it = live["tags"][:10], idx["tags"][:10]
    overlap = len(set(lt) & set(it))
    pct = int(overlap / max(len(set(lt) | set(it)), 1) * 100) if (lt or it) else 100
    return {"topic": t, "live_tags": lt, "index_tags": it,
            "overlap_count": overlap, "agreement_pct": pct,
            "index_videos_count": len(vids)}


@app.get("/api/channels")
def api_channels():
    out = []
    from uploader import con as bcon
    c = bcon()
    import authstore
    names = authstore.names()
    for cid in authstore.load_all():
        row = c.execute("SELECT folder, cap, schedule_slots, auto_schedule FROM channels WHERE channel_id=?", (cid,)).fetchone()
        av_file = BASE / "avatars" / f"{cid}.jpg"
        slots = []
        auto_sched = False
        if row:
            try:
                slots = json.loads(row[2]) if row[2] else []
            except Exception:
                slots = []
            auto_sched = bool(row[3]) if row[3] is not None else False
        out.append({
            "id": cid,
            "name": names.get(cid) or cid,
            "avatar": f"/avatars/{cid}.jpg" if av_file.exists() else None,
            "folder": row[0] if row else None,
            "cap": row[1] if row and row[1] is not None else 5,
            "schedule_slots": slots,
            "auto_schedule": auto_sched
        })
    c.close()
    return out


log_lines = []

def _refresh_avatars():
    """Fetch real names + thumbnails for ALL channels using the first token
    that has readonly scope (id-based lookups work for any channel)."""
    import urllib.request
    av = BASE / "avatars"
    av.mkdir(exist_ok=True)
    import authstore
    service = None
    allauth = authstore.load_all()
    for cid, info in allauth.items():
        try:
            creds = Credentials.from_authorized_user_info(info)
            if creds.expired:
                creds.refresh(GoogleRequest())
                authstore.save(cid, creds)
            cand = build("youtube", "v3", credentials=creds)
            cand.channels().list(part="snippet", mine=True).execute()
            service = cand
            break
        except Exception:
            continue
    if service is None:
        return
    ids = list(allauth.keys())
    for i in range(0, len(ids), 50):
        res = service.channels().list(part="snippet", id=",".join(ids[i:i + 50])).execute()
        for it in res.get("items", []):
            try:
                authstore.set_name(it["id"], it["snippet"]["title"])
                url = it["snippet"]["thumbnails"].get("default", {}).get("url")
                if url:
                    urllib.request.urlretrieve(url, str(av / f"{it['id']}.jpg"))
            except Exception as e:
                log_lines.append(f"avatar {it['id'][:10]}: {e}")


@app.post("/api/avatars/refresh")
def api_avatars_refresh():
    _refresh_avatars()
    return {"ok": True, "count": len(list((BASE / "avatars").glob("*.json")))}


@app.post("/api/batch/start")
def api_batch_start(request: Request, test_mode: bool = False, schedule: bool = True):
    from uploader import run_batch, _state
    if _state.get("running"):
        raise HTTPException(409, "A batch is already running")
    _refresh_avatars()
    threading.Thread(target=run_batch, args=(test_mode, schedule), daemon=True).start()
    return {"started": True, "test_mode": test_mode, "schedule": schedule}


@app.get("/api/daily")
def api_daily_get():
    c = sqlite3.connect(BASE / "batch.db")
    c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    g = lambda k, d=None: (c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone() or [d])[0]
    out = {"enabled": g("daily_enabled", "0") == "1",
           "time": g("daily_time", ""),
           "last_run": g("daily_last_run", None)}
    c.close()
    return out


@app.post("/api/daily")
def api_daily_set(body: dict):
    c = sqlite3.connect(BASE / "batch.db")
    c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    if "enabled" in body:
        c.execute("INSERT OR REPLACE INTO settings VALUES ('daily_enabled', ?)",
                  ("1" if body["enabled"] else "0",))
    t = str(body.get("time", "")).strip()
    wake_note = None
    if len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit() \
            and 0 <= int(t[:2]) < 24 and 0 <= int(t[3:]) < 60:
        c.execute("INSERT OR REPLACE INTO settings VALUES ('daily_time', ?)", (t,))
        if body.get("enabled"):
            from wake import register_wake
            w = register_wake(t)
            wake_note = w.get("detail", "")
    elif t:
        raise HTTPException(400, "Time must be HH:MM (24h)")
    c.commit(); c.close()
    out = api_daily_get()
    if wake_note:
        out["wake"] = wake_note
    return out


def _daily_scheduler_loop():
    import time as _t
    while True:
        try:
            c = sqlite3.connect(BASE / "batch.db")
            c.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
            g = lambda k: (c.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone() or [None])[0]
            enabled = g("daily_enabled") == "1"
            hhmm = g("daily_time")
            last = g("daily_last_run")
            c.close()
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            if enabled and hhmm and last != today and now.strftime("%H:%M") >= hhmm:
                from uploader import run_batch, _state
                if not _state.get("running"):
                    late = "" if now.strftime("%H:%M") == hhmm else " (catch-up — Mac was asleep/off at scheduled time)"
                    c = sqlite3.connect(BASE / "batch.db")
                    c.execute("INSERT OR REPLACE INTO settings VALUES ('daily_last_run', ?)", (today,))
                    c.commit(); c.close()
                    log_lines.append(f"⏰ daily auto-run triggered for {hhmm}{late}")
                    threading.Thread(target=run_batch, args=(False, True), daemon=True).start()
        except Exception:
            pass
        _t.sleep(20)


@app.on_event("startup")
def _start_daily_scheduler():
    threading.Thread(target=_daily_scheduler_loop, daemon=True).start()


@app.post("/api/batch/stop")
def api_batch_stop():
    from uploader import stop_batch
    stop_batch()
    return {"stopping": True}


@app.post("/api/batch/skip-rest")
def api_batch_skip_rest():
    from uploader import skip_rest
    skip_rest()
    return {"ok": True}


@app.get("/api/batch/status")
def api_batch_status():
    from uploader import _state, con as bcon, VIDEO_EXT
    c = bcon()
    chans = []
    completed_in_batch = set(_state.get("completed_channels", []))
    is_running = _state.get("running", False)
    current_cid = _state.get("channel")
    av = BASE / "avatars"

    import authstore as _as
    _names = _as.names()
    for cid in _as.load_all():
        row = c.execute("SELECT folder, cap FROM channels WHERE channel_id=?", (cid,)).fetchone()
        folder_path = row[0] if row and row[0] else None
        cap_val = row[1] if row and row[1] is not None else 5

        total_files = 0
        pending_files = 0
        posted_count = c.execute("SELECT COUNT(*) FROM uploads WHERE channel_id=? AND state='POSTED'", (cid,)).fetchone()[0]

        if folder_path and Path(folder_path).is_dir():
            files = [p.name for p in Path(folder_path).iterdir() if p.suffix.lower() in VIDEO_EXT and p.is_file()]
            total_files = len(files)
            done_files = {r[0] for r in c.execute("SELECT filename FROM uploads WHERE channel_id=? AND state='POSTED'", (cid,))}
            pending_files = len([f for f in files if f not in done_files])

        av_file = av / f"{cid}.jpg"
        name = _names.get(cid) or cid

        if is_running:
            if current_cid == cid:
                state = "active"
            elif cid in completed_in_batch:
                state = "done"
            elif folder_path and pending_files > 0:
                state = "waiting"
            else:
                state = "idle"
        else:
            if folder_path and total_files > 0 and pending_files == 0:
                state = "done"
            elif folder_path and pending_files > 0:
                state = "ready"
            else:
                state = "idle"

        chans.append({"id": cid, "name": name,
                      "avatar": f"/avatars/{cid}.jpg" if av_file.exists() else None,
                      "folder": folder_path,
                      "cap": cap_val,
                      "done": posted_count,
                      "total": total_files if total_files > 0 else posted_count,
                      "pending": pending_files,
                      "state": state})
    return {"running": is_running,
            "phase": _state.get("phase", "idle"),
            "rest_until": _state.get("rest_until"),
            "current_channel": current_cid,
            "current_video": _state.get("video"),
            "log": _state.get("log", [])[-12:], "channels": chans}


@app.get("/api/batch/preview/{channel_id}")
def api_batch_preview(channel_id: str):
    c = sqlite3.connect(BASE / "batch.db")
    row = c.execute("SELECT folder, cap FROM channels WHERE channel_id=?", (channel_id,)).fetchone()
    if not row or not row[0]:
        raise HTTPException(400, "No folder set for this channel")
    folder = Path(row[0])
    cap_val = row[1] if row and row[1] is not None else 5
    if not folder.is_dir():
        raise HTTPException(400, f"Folder not found: {folder}")
    from uploader import title_from_filename, VIDEO_EXT
    out = []
    unposted_count = 0
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() in VIDEO_EXT and p.is_file():
            up = c.execute("SELECT state, video_id, updated_at FROM uploads WHERE channel_id=? AND filename=?",
                           (channel_id, p.name)).fetchone()
            state = up[0] if up else "NEW"
            video_id = up[1] if up else None
            url = f"https://youtu.be/{video_id}" if video_id else None
            is_posted = state == "POSTED"
            in_next_batch = False
            batch_order = None
            if not is_posted:
                unposted_count += 1
                if unposted_count <= cap_val:
                    in_next_batch = True
                    batch_order = unposted_count
            out.append({
                "file": p.name,
                "title": title_from_filename(p),
                "state": state,
                "video_id": video_id,
                "url": url,
                "is_posted": is_posted,
                "in_next_batch": in_next_batch,
                "batch_order": batch_order,
                "cap": cap_val
            })
    c.close()
    return out


@app.post("/api/channels/{channel_id}/reset-uploads")
def api_reset_channel_uploads(channel_id: str, filename: str = None):
    c = sqlite3.connect(BASE / "batch.db")
    if filename:
        c.execute("DELETE FROM uploads WHERE channel_id=? AND filename=?", (channel_id, filename))
    else:
        c.execute("DELETE FROM uploads WHERE channel_id=?", (channel_id,))
    c.commit()
    c.close()
    return {"ok": True, "channel_id": channel_id, "filename": filename}


@app.post("/api/channels/{channel_id}/folder")
def api_set_folder(channel_id: str, body: dict):
    folder = (body or {}).get("folder", "").strip()
    cap = (body or {}).get("cap")
    if not folder or not Path(folder).is_dir():
        raise HTTPException(400, f"Folder does not exist: {folder}")
    c = sqlite3.connect(BASE / "batch.db")
    c.execute("CREATE TABLE IF NOT EXISTS channels(channel_id TEXT PRIMARY KEY, folder TEXT, cap INT DEFAULT 5)")
    if cap is not None:
        try:
            cap_val = max(1, int(cap))
            c.execute("INSERT INTO channels(channel_id, folder, cap) VALUES (?,?,?) "
                      "ON CONFLICT(channel_id) DO UPDATE SET folder=excluded.folder, cap=excluded.cap", (channel_id, folder, cap_val))
        except (ValueError, TypeError):
            c.execute("INSERT INTO channels(channel_id, folder) VALUES (?,?) "
                      "ON CONFLICT(channel_id) DO UPDATE SET folder=excluded.folder", (channel_id, folder))
            cap_val = 5
    else:
        c.execute("INSERT INTO channels(channel_id, folder) VALUES (?,?) "
                  "ON CONFLICT(channel_id) DO UPDATE SET folder=excluded.folder", (channel_id, folder))
        row = c.execute("SELECT cap FROM channels WHERE channel_id=?", (channel_id,)).fetchone()
        cap_val = row[0] if row and row[0] is not None else 5
    c.commit()
    c.close()
    return {"ok": True, "channel_id": channel_id, "folder": folder, "cap": cap_val}


@app.post("/api/channels/{channel_id}/cap")
def api_set_cap(channel_id: str, body: dict):
    cap = (body or {}).get("cap", 5)
    try:
        cap_val = max(1, int(cap))
    except (ValueError, TypeError):
        raise HTTPException(400, "Upload cap must be a positive number (minimum 1)")
    c = sqlite3.connect(BASE / "batch.db")
    c.execute("CREATE TABLE IF NOT EXISTS channels(channel_id TEXT PRIMARY KEY, folder TEXT, cap INT DEFAULT 5)")
    c.execute("INSERT INTO channels(channel_id, cap) VALUES (?,?) "
              "ON CONFLICT(channel_id) DO UPDATE SET cap=excluded.cap", (channel_id, cap_val))
    c.commit()
    c.close()
    return {"ok": True, "channel_id": channel_id, "cap": cap_val}


@app.post("/api/channels/{channel_id}/schedule")
def api_set_channel_schedule(channel_id: str, body: dict):
    slots = (body or {}).get("slots", [])
    auto_schedule = 1 if (body or {}).get("auto_schedule", False) else 0
    cleaned_slots = []
    for s in slots:
        t = str(s.get("time", "")).strip()
        if not t:
            continue
        parts = t.split(":")
        if len(parts) == 2:
            try:
                h, m = int(parts[0]), int(parts[1])
                if 0 <= h <= 23 and 0 <= m <= 59:
                    norm_time = f"{h:02d}:{m:02d}"
                    cnt = max(1, int(s.get("count", 1)))
                    enabled = bool(s.get("enabled", True))
                    cleaned_slots.append({"time": norm_time, "count": cnt, "enabled": enabled})
            except Exception:
                continue

    from uploader import con as bcon
    c = bcon()
    c.execute("INSERT INTO channels(channel_id, schedule_slots, auto_schedule) VALUES (?,?,?) "
              "ON CONFLICT(channel_id) DO UPDATE SET schedule_slots=excluded.schedule_slots, auto_schedule=excluded.auto_schedule",
              (channel_id, json.dumps(cleaned_slots), auto_schedule))
    c.commit()
    c.close()
    return {"ok": True, "channel_id": channel_id, "schedule_slots": cleaned_slots, "auto_schedule": bool(auto_schedule)}


@app.get("/api/schedule")
def api_get_global_schedule():
    from uploader import con as bcon
    c = bcon()
    row = c.execute("SELECT auto_schedule, slots FROM global_schedule WHERE id=1").fetchone()
    c.close()
    auto_sched = bool(row[0]) if row and row[0] is not None else False
    try:
        slots = json.loads(row[1]) if row and row[1] else []
    except Exception:
        slots = []
    return {"auto_schedule": auto_sched, "slots": slots}


@app.post("/api/schedule")
def api_set_global_schedule(body: dict):
    slots = (body or {}).get("slots", [])
    auto_schedule = 1 if (body or {}).get("auto_schedule", False) else 0
    cleaned_slots = []
    for s in slots:
        t = str(s.get("time", "")).strip()
        if not t:
            continue
        parts = t.split(":")
        if len(parts) == 2:
            try:
                h, m = int(parts[0]), int(parts[1])
                if 0 <= h <= 23 and 0 <= m <= 59:
                    norm_time = f"{h:02d}:{m:02d}"
                    cnt = max(1, int(s.get("count", 1)))
                    enabled = bool(s.get("enabled", True))
                    cleaned_slots.append({"time": norm_time, "count": cnt, "enabled": enabled})
            except Exception:
                continue

    from uploader import con as bcon
    c = bcon()
    c.execute("INSERT INTO global_schedule(id, auto_schedule, slots) VALUES (1,?,?) "
              "ON CONFLICT(id) DO UPDATE SET auto_schedule=excluded.auto_schedule, slots=excluded.slots",
              (auto_schedule, json.dumps(cleaned_slots)))
    c.commit()
    c.close()
    return {"ok": True, "auto_schedule": bool(auto_schedule), "slots": cleaned_slots}


@app.delete("/api/channels/{channel_id}")
def api_delete_channel(channel_id: str):
    safe = "".join(c for c in channel_id if c.isalnum() or c in "-_")
    removed = []
    import authstore as _asd
    if _asd.delete(channel_id):
        removed.append("auth")
    for f in (BASE / "avatars").glob(f"{safe}.jpg"):
        f.unlink(); removed.append("avatar")
    c = sqlite3.connect(BASE / "batch.db")
    c.execute("DELETE FROM channels WHERE channel_id=?", (channel_id,))
    c.execute("DELETE FROM uploads WHERE channel_id=?", (channel_id,))
    c.commit(); c.close()
    return {"ok": True, "channel_id": channel_id, "removed": removed}


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...), title: str = Form(...),
                 description: str = Form(""), tags: str = Form("")):
    channel_id, _ = get_active_channel(request)
    if not channel_id:
        raise HTTPException(401, "Sign in first")
    title = title.strip()
    if not title or len(title) > 100:
        raise HTTPException(400, "Title must be 1-100 characters")
    tag_list = [t.strip() for t in tags.split(",") if t.strip()][:30]
    if not (file.filename or "").lower().endswith((".mp4", ".mov", ".webm", ".avi", ".mkv")):
        raise HTTPException(400, "Only video files (mp4, mov, webm, avi, mkv)")

    if today_count(channel_id) >= DAILY_CAP:
        raise HTTPException(429, f"Daily limit of {DAILY_CAP} uploads reached for your own safety. Try tomorrow.")

    with tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        yt = get_youtube(channel_id)
        resp = yt.videos().insert(
            part="snippet,status",
            body={
                "snippet": {"title": title, "description": description,
                            "tags": tag_list, "categoryId": "22"},
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
            },
            media_body=MediaFileUpload(tmp_path, resumable=True, chunksize=8 * 1024 * 1024),
        )
        # resumable loop with progress
        progress = 0
        while True:
            status, response = resp.next_chunk()
            if status:
                progress = int(status.progress() * 100)
            if response is not None:
                break
        vid = response["id"]

        log = load_log()
        log.setdefault("uploads", []).append(
            {"channel": channel_id, "date": date.today().isoformat(), "title": title, "video_id": vid}
        )
        save_log(log)
        return {"ok": True, "video_id": vid, "url": f"https://youtu.be/{vid}"}
    except Exception as e:
        detail = getattr(e, "content", b"")
        raise HTTPException(500, f"YouTube rejected the upload: {e}. {detail.decode()[:300] if detail else ''}")
    finally:
        os.unlink(tmp_path)


@app.get("/health")
def health():
    log = load_log().get("uploads", [])
    today = date.today().isoformat()
    import authstore as _ash
    return {"tokens_saved": len(_ash.load_all()),
            "uploads_total": len(log),
            "uploads_today_all_channels": len([e for e in log if e["date"] == today]),
            "daily_cap_per_channel": DAILY_CAP}


# ---------- the one page ----------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    channel_id, channel_title = get_active_channel(request)
    signed_in = bool(channel_id)
    return HTML_CONTENT.replace("{{SIGNED_IN}}", "1" if signed_in else "0").replace("{{CHANNEL}}", channel_title or channel_id or "")


HTML_CONTENT = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Upload to My YouTube</title>
<style>
 body{font-family:-apple-system,sans-serif;max-width:560px;margin:40px auto;padding:0 20px;background:#fafafa}
 @media(max-width:600px){body{margin:16px auto}}
 h1{font-size:32px} .step{background:#fff;border:2px solid #ddd;border-radius:16px;padding:24px;margin:20px 0}
 @media(max-width:600px){h1{font-size:26px}.step{padding:18px 16px}}
 button,a.btn{background:#ea4335;color:#fff;border:none;border-radius:12px;padding:18px 36px;font-size:22px;cursor:pointer;text-decoration:none;display:inline-block}
 @media(max-width:600px){button,a.btn{width:100%;padding:16px;font-size:20px}}
 button:disabled{background:#ccc} input[type=text]{width:100%;font-size:20px;padding:14px;border:2px solid #ddd;border-radius:10px;box-sizing:border-box}
 input[type=file]{font-size:18px;max-width:100%} .ok{color:#188038;font-size:22px;font-weight:bold} .err{color:#d93025;font-size:18px}
 #progress{display:none;margin-top:12px;height:26px;background:#eee;border-radius:13px;overflow:hidden}
 #bar{height:100%;width:0;background:#188038;transition:width .3s} .small{color:#475569;font-size:15px;line-height:1.5}
 .chip{border:1px solid #cbd5e1;border-radius:20px;padding:8px 14px;margin:4px 3px;font-size:14px;font-weight:600;background:#ffffff;color:#1e293b;cursor:pointer;box-shadow:0 1px 3px rgba(0,0,0,0.06);transition:all 0.15s ease;display:inline-block}
 .chip:hover{background:#f1f5f9;border-color:#94a3b8;color:#0f172a;transform:translateY(-1px);box-shadow:0 2px 5px rgba(0,0,0,0.1)}
</style></head><body>
<h1>📺 Upload to My YouTube</h1>

<div class="step" id="signin-step">
 <b>Step 1 — Sign in (only once)</b><br><br>
 <div id="signedout"><a class="btn" href="/login">Sign in with Google</a></div>
 <div id="signedin" style="display:none">✅ Signed in as <b>{{CHANNEL}}</b> &nbsp; <a class="small" href="/logout">(switch account)</a></div>
</div>

<div class="step">
 <b>Step 2 — Choose your video</b><br><br>
 <input type="file" id="file" accept="video/*" style="font-size:20px">
 <br><br><b>Title</b><br><input type="text" id="title" maxlength="100" placeholder="Name of your video">
 <br><br><b>Description (optional)</b><br><input type="text" id="desc" placeholder="A few words about it">
</div>

<div class="step" style="background:#fffbe8;border-color:#e3d27a">
 <b>💡 Need ideas? What is your video about?</b><br><br>
 <input type="text" id="topic" placeholder="e.g. ai video, cooking, cricket" style="width:70%;display:inline-block">
 <button id="ideabtn" onclick="getIdeas()" style="padding:14px 22px;font-size:17px;background:#f9ab00">Find</button>
 <button id="cmpbtn" onclick="getCompare()" style="padding:14px 22px;font-size:17px;background:#1a73e8">📊 Free vs API</button>
 <div id="ideas" style="display:none;margin-top:16px"></div>
</div>

<div class="step">
 <b>Step 3 — Upload</b><br><br>
 <button id="upbtn" onclick="doUpload()">⬆️ Upload</button>
 <div id="progress"><div id="bar"></div></div>
 <p id="tagmsg" class="small"></p>
 <p id="msg" class="ok"></p><p id="err" class="err"></p>
</div>

<script>
const signed = "{{SIGNED_IN}}" === "1";
if (signed) { document.getElementById("signedout").style.display="none";
               document.getElementById("signedin").style.display="block"; }

let chosenTags = [];
function getIdeas() {
 const t = document.getElementById("topic").value.trim();
 const box = document.getElementById("ideas");
 if (!t) { box.style.display="block"; box.innerHTML="<span class='err'>Type a topic first</span>"; return; }
 box.style.display = "block";
 box.innerHTML = "⏳ Looking at what's winning right now...";
 fetch("/api/ideas?topic=" + encodeURIComponent(t))
  .then(r => r.json()).then(d => {
    if (d.detail) { box.innerHTML = "<span class='err'>" + d.detail + "</span>"; return; }
    let h = "";
    const clean = s => s.replace(/['"]/g, "");
    if (d.keywords && d.keywords.length) {
      h += "<b>🔑 Words people search (click to add to title):</b><br>";
      d.keywords.forEach(k => h += '<button class="chip" data-add-title="' + clean(k) + '">' + clean(k) + '</button> ');
      h += "<br><br>";
    }
    if (d.hashtags && d.hashtags.length) {
      h += "<b>#️⃣ Winning hashtags (click to add to description):</b><br>";
      d.hashtags.forEach(k => h += '<button class="chip" data-add-desc="' + clean(k) + '">' + clean(k) + '</button> ');
      h += "<br><br>";
    }
    if (d.tags && d.tags.length) {
      h += "<b>🏷️ Viral tags:</b> ";
      h += "<button class='chip' style='background:#188038;color:#fff' id='usetags'>✅ Use these tags on my video</button><br>";
      h += "<span class='small'>" + d.tags.map(clean).join(", ") + "</span><br><br>";
      chosenTags = d.tags;
    }
    if (d.duration) h += "<span class='small'>⏱️ Winners are ~" + Math.round(d.duration/60) + " min " + (d.duration%60) + "s long. ";
    if (d.hours && d.hours.length) h += "Best upload time: " + d.hours.join(", ") + " UTC.</span>";
    if (!h) h = "<span class='err'>😕 Nothing found for that exact phrase.<br>Try 1-3 words — e.g. <b>sajek tour</b> or <b>bangladesh travel</b></span>";
    else h += "<br><span class='small'>" + (d.source === "index" || d.source === "corpus"
              ? "⚡ Served from your index — 0 API cost"
              : "🔎 Live research — saved to index for next time") + "</span>";
    box.innerHTML = h;
  }).catch(() => box.innerHTML = "<span class='err'>Could not fetch ideas — check internet.</span>");
}
function getCompare() {
 const t = document.getElementById("topic").value.trim();
 const box = document.getElementById("ideas");
 if (!t) { box.style.display="block"; box.innerHTML="<span class='err'>Type a topic first</span>"; return; }
 box.style.display = "block";
 box.innerHTML = "⏳ Comparing free index vs live API (spends 1 search)...";
 fetch("/api/compare?topic=" + encodeURIComponent(t))
  .then(r => r.json()).then(d => {
    if (d.detail) { box.innerHTML = "<span class='err'>" + d.detail + "</span>"; return; }
    const L = d.live_tags, I = d.index_tags;
    const setL = new Set(L.map(x=>x.toLowerCase())), setI = new Set(I.map(x=>x.toLowerCase()));
    const common = L.filter(x=>setI.has(x.toLowerCase())).length;
    const pct = Math.round(common / Math.max(new Set([...setL,...setI]).size,1) * 100);
    let h = "<b>📊 '" + d.topic + "' — Free (index, " + d.index_videos + " videos) vs API (live)</b><br><br>";
    h += "<table style='width:100%;border-collapse:collapse;font-size:15px'>";
    h += "<tr style='background:#eee'><th style='padding:8px;text-align:left'>⚡ FREE (0 quota)</th><th style='padding:8px;text-align:left'>🔎 API (1 search)</th></tr>";
    const n = Math.max(L.length, I.length);
    for (let i=0;i<n;i++){
      const l = L[i]||"", r = I[i]||"";
      const same = l && r && l.toLowerCase()===r.toLowerCase();
      h += "<tr style='border-top:1px solid #ddd'><td style='padding:6px'>" + (same?"✅ ":"") + l + "</td><td style='padding:6px'>" + (same?"✅ ":"") + r + "</td></tr>";
    }
    h += "</table><br><b>" + common + " tags match — " + pct + "% agreement" + (pct>=60 ? " ✅ trustworthy" : " ⚠️ refresh index") + "</b>";
    box.innerHTML = h;
  }).catch(() => box.innerHTML = "<span class='err'>Compare failed — check internet.</span>");
}

document.addEventListener("click", e => {
  const t = e.target.closest("button[data-add-title]");
  const d = e.target.closest("button[data-add-desc]");
  if (t) {
    const el = document.getElementById("title");
    el.value = el.value ? el.value + " " + t.dataset.addTitle : t.dataset.addTitle;
  }
  if (d) {
    const el = document.getElementById("desc");
    el.value = (el.value + " " + d.dataset.addDesc).trim();
  }
  if (e.target.id === "usetags") {
    document.getElementById("tagmsg").innerHTML = "✅ Tags will be added automatically";
  }
});

function doUpload() {
 const f = document.getElementById("file").files[0];
 const t = document.getElementById("title").value.trim();
 document.getElementById("err").textContent = "";
 document.getElementById("msg").textContent = "";
 if (!signed) { document.getElementById("err").textContent = "Please sign in first (Step 1)."; return; }
 if (!f) { document.getElementById("err").textContent = "Please choose a video file (Step 2)."; return; }
 if (!t) { document.getElementById("err").textContent = "Please give your video a title."; return; }

 const fd = new FormData();
 fd.append("file", f); fd.append("title", t); fd.append("description", document.getElementById("desc").value);
 if (chosenTags.length) fd.append("tags", chosenTags.join(","));
 const xhr = new XMLHttpRequest();
 xhr.open("POST", "/api/upload");
 xhr.upload.onprogress = e => { if (e.lengthComputable) {
   document.getElementById("progress").style.display = "block";
   document.getElementById("bar").style.width = Math.round(e.loaded/e.total*100) + "%"; }};
 xhr.onload = () => {
   const r = JSON.parse(xhr.responseText);
   if (xhr.status === 200) {
     document.getElementById("msg").innerHTML = "✅ Done! <a href='" + r.url + "' target='_blank'>Watch it on YouTube</a>";
   } else {
     document.getElementById("err").textContent = r.detail || "Upload failed. Please try again.";
     document.getElementById("progress").style.display = "none";
   }};
 xhr.onerror = () => document.getElementById("err").textContent = "Connection lost — check internet and retry.";
 xhr.send(fd);
}
</script>
</body></html>"""


# ---------- Daily Auto-Pilot Scheduler Daemon ----------

_scheduled_triggers_today = set()

def _background_scheduler_worker():
    import time as _t
    from datetime import datetime
    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            current_hm = now.strftime("%H:%M")

            # Purge triggers from previous days
            expired = {k for k in _scheduled_triggers_today if not k.endswith(today_str)}
            _scheduled_triggers_today.difference_update(expired)

            from uploader import _state, run_batch, con as bcon, log
            c = bcon()

            # 1. Global Batch Auto-Pilot Schedule check
            g_row = c.execute("SELECT auto_schedule, slots FROM global_schedule WHERE id=1").fetchone()
            if g_row and g_row[0]:
                try:
                    g_slots = json.loads(g_row[1]) if g_row[1] else []
                except Exception:
                    g_slots = []
                for slot in g_slots:
                    if not slot.get("enabled", True):
                        continue
                    slot_time = str(slot.get("time", "")).strip()
                    if not slot_time:
                        continue
                    parts = slot_time.split(":")
                    if len(parts) == 2:
                        try:
                            norm_slot_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                        except Exception:
                            continue
                    else:
                        norm_slot_time = slot_time

                    if norm_slot_time == current_hm:
                        trigger_key = f"global_{norm_slot_time}_{today_str}"
                        if trigger_key not in _scheduled_triggers_today:
                            _scheduled_triggers_today.add(trigger_key)
                            slot_count = max(1, int(slot.get("count", 1)))
                            if not _state.get("running", False):
                                log(f"⏰ [Daily Auto-Pilot] It is {norm_slot_time} — starting scheduled batch upload of {slot_count} video(s) per channel!")
                                threading.Thread(
                                    target=run_batch,
                                    kwargs={"test_mode": False, "schedule": False, "custom_cap": slot_count},
                                    daemon=True
                                ).start()
                            else:
                                log(f"⚠️ [Daily Auto-Pilot] Slot {norm_slot_time} ({slot_count} vids) matched, but engine is currently busy.")

            # 2. Per-Channel Schedule check
            rows = c.execute("SELECT channel_id, folder, schedule_slots, auto_schedule FROM channels "
                            "WHERE folder IS NOT NULL AND auto_schedule=1").fetchall()
            c.close()

            for cid, folder, slots_json, auto_enabled in rows:
                if not auto_enabled or not folder or not Path(folder).is_dir():
                    continue
                try:
                    slots = json.loads(slots_json) if slots_json else []
                except Exception:
                    slots = []

                for slot in slots:
                    if not slot.get("enabled", True):
                        continue
                    slot_time = str(slot.get("time", "")).strip()
                    if not slot_time:
                        continue
                    parts = slot_time.split(":")
                    if len(parts) == 2:
                        try:
                            norm_slot_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                        except Exception:
                            continue
                    else:
                        norm_slot_time = slot_time

                    if norm_slot_time == current_hm:
                        trigger_key = f"{cid}_{norm_slot_time}_{today_str}"
                        if trigger_key not in _scheduled_triggers_today:
                            _scheduled_triggers_today.add(trigger_key)
                            slot_count = max(1, int(slot.get("count", 1)))
                            if not _state.get("running", False):
                                log(f"⏰ [Channel Schedule] It is {norm_slot_time} — starting scheduled upload of {slot_count} video(s) for Channel {cid[:12]}…")
                                threading.Thread(
                                    target=run_batch,
                                    kwargs={"test_mode": False, "schedule": False, "target_channel": cid, "custom_cap": slot_count},
                                    daemon=True
                                ).start()
                            else:
                                log(f"⚠️ [Channel Schedule] Slot {norm_slot_time} ({slot_count} vids) matched for {cid[:12]}…, but engine is currently busy.")
        except Exception:
            pass
        _t.sleep(15)

threading.Thread(target=_background_scheduler_worker, daemon=True).start()


for _dist in (BASE / "web" / "dist", EXE_DIR.parent / "web" / "dist", EXE_DIR / "web" / "dist"):
    if _dist.exists():
        app.mount("/dashboard", StaticFiles(directory=str(_dist), html=True), name="dashboard")
        break
(BASE / "avatars").mkdir(exist_ok=True)
app.mount("/avatars", StaticFiles(directory=str(BASE / "avatars")), name="avatars")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("YT_AUTO_PORT", "8000")))
