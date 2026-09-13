#!/usr/bin/env python
"""yt-auto uploader — folder → AI metadata → sequential multi-channel uploads.

Sub-commands:
  setfolder <channel_id> <folder>   bind a video folder to a channel
  channels                          list authed channels + folders
  dryrun <folder>                   preview: parsed titles, tags, slots (no upload)
  selftest                          parser/slot/db assertions

Library use (app.py worker):
  run_batch(test_mode=True/False)   the whole sequential loop in a thread
  stop_batch()                      graceful stop flag
"""
import json
import os
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research import canonical_topic, video_stats, autocomplete, yt

BASE = Path(os.environ["YT_AUTO_DATA"]) if os.environ.get("YT_AUTO_DATA") else Path(__file__).parent
DB = BASE / "batch.db"
VIDEO_EXT = (".mp4", ".mov", ".webm", ".avi", ".mkv")
SMALL = {"of", "the", "in", "and", "to", "a", "an", "for", "at", "on", "with", "my"}
ACRONYMS = {"ai", "seo", "gta", "ugc", "asmr"}
UPLOAD_COST = 1          # videos.insert in its own bucket (2026 pricing)
DAILY_BUCKET = 100       # uploads/day, whole project


def con():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS channels(
        channel_id TEXT PRIMARY KEY, folder TEXT, cap INT DEFAULT 5,
        schedule_slots TEXT DEFAULT '[]', auto_schedule INT DEFAULT 0)""")
    cols = {r[1] for r in c.execute("PRAGMA table_info(channels)").fetchall()}
    if "cap" not in cols:
        try:
            c.execute("ALTER TABLE channels ADD COLUMN cap INT DEFAULT 5")
        except sqlite3.OperationalError:
            pass
    if "schedule_slots" not in cols:
        try:
            c.execute("ALTER TABLE channels ADD COLUMN schedule_slots TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
    if "auto_schedule" not in cols:
        try:
            c.execute("ALTER TABLE channels ADD COLUMN auto_schedule INT DEFAULT 0")
        except sqlite3.OperationalError:
            pass
    c.execute("""CREATE TABLE IF NOT EXISTS global_schedule(
        id INTEGER PRIMARY KEY, auto_schedule INT DEFAULT 0, slots TEXT DEFAULT '[]')""")
    c.execute("INSERT OR IGNORE INTO global_schedule(id, auto_schedule, slots) VALUES (1, 0, '[]')")
    c.execute("""CREATE TABLE IF NOT EXISTS uploads(
        channel_id TEXT, filename TEXT, state TEXT, video_id TEXT,
        title TEXT, error TEXT, updated_at TEXT,
        PRIMARY KEY(channel_id, filename))""")
    c.commit()
    return c


# ---------- filename → title ----------

def title_from_filename(path) -> str:
    name = Path(path).stem
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    words = name.split(" ")
    out = []
    for i, w in enumerate(words):
        if any("\u0980" <= ch <= "\u09FF" or "\u0900" <= ch <= "\u097F" for ch in w):
            out.append(w)                                   # Bangla/Hindi: untouched
        elif w.isupper() or w.lower() in ACRONYMS:
            out.append(w.upper() if w.lower() in ACRONYMS else w)   # AI, 2026, SEO
        elif i == 0 or w.lower() not in SMALL:
            out.append(w.capitalize())
        else:
            out.append(w.lower())
    title = " ".join(out)
    return title[:100]


# ---------- metadata ----------

def sanitize_tags(tags: list) -> list:
    """YouTube rejects comma-stuffed mega-tags and overlong ones — split, clean, cap."""
    out, seen = [], set()
    for t in tags:
        for part in str(t).split(","):
            p = part.strip()
            if 2 <= len(p) <= 60 and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
            if len(out) >= 25:
                return out
    return out


def assemble_metadata(title: str) -> dict:
    topic = canonical_topic(title)
    agg = {"tags": [], "hours": []}
    try:
        from index import con as icon_con, index_videos, corpus_search, aggregate
        c = icon_con()
        vids = index_videos(c, topic)
        if not vids:
            vids = corpus_search(topic)
        if vids:
            agg = aggregate(vids[:15])
    except Exception:
        agg = {"tags": [], "hours": []}

    tags = sanitize_tags(agg.get("tags", []))[:15]
    hours = agg.get("hours", [])

    # If no local indexed tags match this specific topic, fetch real tags from YouTube autocomplete
    if len(tags) < 3:
        try:
            from research import generate_tags_from_autocomplete
            auto_data = generate_tags_from_autocomplete(topic)
            auto_tags = sanitize_tags(auto_data.get("tags", []))
            for t in auto_tags:
                if t not in tags:
                    tags.append(t)
            if not hours:
                hours = auto_data.get("hours", [])
        except Exception:
            pass

    try:
        kws = autocomplete(topic)
    except Exception:
        kws = []

    return {"title": title, "tags": tags[:15], "keywords": kws,
            "hours": hours, "description": None}


def ai_description(meta: dict) -> str:
    """Real AI descriptions only — requires OPENROUTER_API_KEY. No fake fallback."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set — export it to upload")

    title = meta.get("title", "").strip()
    tags = meta.get("tags", [])
    relevant_keywords = ", ".join(tags[:8]) if tags else title

    prompt = (
        f"You are a professional YouTube SEO copywriter.\n"
        f"Write a compelling, engaging, and SEO-optimized YouTube video description (120-180 words) "
        f"specifically for a video titled: \"{title}\".\n\n"
        f"STRICT REQUIREMENTS:\n"
        f"1. Context Accuracy: The description MUST strictly focus on the content and topic implied by the title \"{title}\".\n"
        f"2. No Hallucinations: Do NOT mention or invent unrelated places, tours (e.g. Sajek, Paris), games, or topics unless they are explicitly in the title.\n"
        f"3. Structure:\n"
        f"   - An engaging opening hook about the video's subject.\n"
        f"   - 2-3 sentences highlighting what viewers will see, experience, or learn.\n"
        f"   - A clear call-to-action (Like, Comment, and Subscribe for more).\n"
        f"4. Keywords: Naturally incorporate relevant keywords ({relevant_keywords}).\n"
        f"5. Hashtags: End with 3-4 relevant hashtags based directly on \"{title}\".\n"
        f"6. Output: Plain text description only. Do NOT include markdown titles, explanations, or code blocks."
    )
    import urllib.request
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({
            "model": "meta-llama/llama-3.3-70b-instruct",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional YouTube SEO specialist. You write accurate, engaging video descriptions strictly tailored to the video's actual title and topic without hallucinating unrelated topics or destinations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7
        }).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"][:2000]


# ---------- publish slots (best hours, native scheduling) ----------

def publish_slots(topic_hint: str, n: int, hours: list = None) -> list[str]:
    if not hours:
        try:
            from index import con as icon_con, index_videos, corpus_search, aggregate
            vids = index_videos(icon_con(), topic_hint)
            if not vids:
                vids = corpus_search(topic_hint)
            hours = aggregate(vids[:15]).get("hours", []) if vids else []
        except Exception:
            hours = []
    now = datetime.now().astimezone()
    slots, cursor = [], now + timedelta(minutes=90)
    if hours:
        first = None
        for off in range(0, 72):                      # find next occurrence of best hour
            cand = (now + timedelta(hours=off)).replace(minute=0, second=0, microsecond=0)
            if cand.strftime("%H:00") in hours and cand > now + timedelta(minutes=30):
                first = cand; break
        if first:
            cursor = first
    for _ in range(n):
        if cursor <= now + timedelta(minutes=30):
            cursor = now + timedelta(minutes=90)
        slots.append(cursor.isoformat(timespec="seconds"))
        cursor += timedelta(minutes=90)
    return slots


# ---------- batch worker ----------

_stop = False
_state = {"running": False, "channel": None, "video": None, "phase": "idle", "log": [], "completed_channels": []}


_skip_sleep = False


def format_api_error(e) -> str:
    """Extract clean, full error message and reason from Google API HttpError."""
    if hasattr(e, "content") and e.content:
        try:
            raw = e.content.decode("utf-8") if isinstance(e.content, bytes) else str(e.content)
            data = json.loads(raw)
            err_obj = data.get("error", {})
            msg = err_obj.get("message", "")
            errors = err_obj.get("errors", [])
            reason = errors[0].get("reason", "") if errors else ""
            code = err_obj.get("code", "")
            if reason and msg:
                return f"[HTTP {code}] {reason}: {msg}"
            if msg:
                return f"[HTTP {code}] {msg}"
        except Exception:
            pass
    s = str(e)
    return re.sub(r"\s+", " ", s).strip()


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry, flush=True)
    _state.setdefault("log", []).append(entry)
    if len(_state["log"]) > 100:
        _state["log"] = _state["log"][-100:]


def stop_batch():
    global _stop, _skip_sleep
    _stop = True
    _skip_sleep = True
    _state.update(running=False, phase="idle", channel=None, video=None)
    log("Batch stopped by user ⏹️")


def skip_rest():
    global _skip_sleep
    _skip_sleep = True


def _sleep(seconds: float) -> bool:
    """Interruptible sleep: returns True if a stop was requested mid-sleep."""
    global _skip_sleep
    _skip_sleep = False
    end = time.time() + max(0.0, seconds)
    while not _stop and not _skip_sleep:
        remaining = end - time.time()
        if remaining <= 0:
            return False
        time.sleep(min(0.2, remaining))
    _skip_sleep = False
    return _stop


def run_batch(test_mode: bool = False, schedule: bool = True, target_channel: str = None, custom_cap: int = None):
    global _stop
    _stop = False
    _state.update(running=True, channel=None, video=None, phase="working", completed_channels=[], log=[])
    from wake import prevent_sleep, allow_sleep
    sleep_handle = prevent_sleep()
    c = con()
    c.execute("UPDATE uploads SET state='PENDING' WHERE state='PROCESSING'")
    c.commit()
    if target_channel:
        chans = c.execute("SELECT channel_id, folder, cap FROM channels "
                          "WHERE channel_id=? AND folder IS NOT NULL", (target_channel,)).fetchall()
    else:
        chans = c.execute("SELECT channel_id, folder, cap FROM channels "
                          "WHERE folder IS NOT NULL ORDER BY channel_id").fetchall()
    delay_vid = (5, 10) if test_mode else (15, 30)
    delay_ch = (5, 10) if test_mode else (30, 50)
    try:
        for ch_idx, (cid, folder, cap) in enumerate(chans):
            if _stop:
                break
            _state.update(channel=cid, video=None, phase="working")
            files = sorted(p for p in Path(folder).iterdir()
                           if p.suffix.lower() in VIDEO_EXT and p.is_file())
            done = {r[0] for r in c.execute(
                "SELECT filename FROM uploads WHERE channel_id=? AND state='POSTED'", (cid,))}
            todo = [f for f in files if f.name not in done]
            skipped = len(files) - len(todo)
            cap_limit = custom_cap if custom_cap is not None else (cap if cap is not None else 5)
            if todo:
                will_upload = min(cap_limit, len(todo))
                log(f"Channel {cid[:12]}…: found {len(todo)} new video(s) (upload cap: {cap_limit} — uploading {will_upload} in this run)"
                    + (f" ({skipped} already uploaded — skipped)" if skipped else ""))
            elif skipped:
                log(f"Channel {cid[:12]}…: nothing new — all {skipped} video(s) in {folder} "
                    f"already uploaded ✅")
            else:
                log(f"Channel {cid[:12]}…: folder empty ({folder})")
            count = 0
            todo_idx = 0
            for f in todo:
                if _stop:
                    break
                if count >= cap_limit:
                    log(f"Channel {cid[:12]}…: reached upload cap of {cap_limit} video(s) ✅")
                    break
                _state["video"] = f.name
                title = title_from_filename(f)
                c.execute("INSERT OR REPLACE INTO uploads VALUES (?,?,?,?,?,?,?)",
                          (cid, f.name, "PROCESSING", None, title, None,
                           datetime.now(timezone.utc).isoformat(timespec="seconds")))
                c.commit()
                try:
                    meta = assemble_metadata(title)
                    meta["description"] = ai_description(meta)
                    slots = publish_slots(topic_hint=canonical_topic(title),
                                          n=1, hours=meta.get("hours", []))
                    creds = Credentials_from_file(cid)
                    resp = insert_video(creds, f, meta, slots[0] if slots else None,
                                        test_mode, schedule)
                    c.execute("UPDATE uploads SET state='POSTED', video_id=?, error=NULL, "
                              "updated_at=? WHERE channel_id=? AND filename=?",
                              (resp, datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               cid, f.name))
                    c.commit()
                    log(f"✅ {title} → https://youtu.be/{resp}")
                    if not test_mode:
                        try:
                            f.unlink(missing_ok=True)   # folder self-drains; uploads table is cleared at batch end
                            log(f"🗑️ Source file deleted: {f.name}")
                        except OSError as e:
                            log(f"⚠️ Uploaded OK but could not delete {f.name}: {e}")
                    count += 1
                except Exception as e:
                    err = str(e)
                    readable_err = format_api_error(e)
                    c.execute("UPDATE uploads SET state='FAILED', error=?, updated_at=? "
                              "WHERE channel_id=? AND filename=?",
                              (readable_err[:500], datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               cid, f.name))
                    c.commit()
                    log(f"❌ {f.name}: {readable_err}")
                    if "quotaExceeded" in err or "quotaExceeded" in readable_err:
                        log("Daily project quota exhausted — batch stops, resumes after reset.")
                        _stop = True
                        break
                    if "uploadLimitExceeded" in err or "uploadRateLimitExceeded" in err or "uploadLimitExceeded" in readable_err:
                        log("Channel upload allowance hit — skipping to next channel.")
                        break
                    _sleep(3)
                todo_idx += 1
                if todo_idx < len(todo) and not _stop and count < cap_limit:
                    if _sleep(random.uniform(*delay_vid)):
                        break
            _state.setdefault("completed_channels", []).append(cid)
            log(f"Channel {cid[:12]}… finished ({count} uploaded).")
            if not _stop and count > 0 and ch_idx + 1 < len(chans):
                import time as _t
                _state.update(channel=None, video=None, phase="resting",
                              rest_until=_t.time() + random.uniform(*delay_ch))
                if _sleep(_state["rest_until"] - _t.time()):
                    break
            _state.update(phase="working", rest_until=None)
    finally:
        allow_sleep(sleep_handle)
        _state.update(running=False, channel=None, video=None, phase="idle")
        c.execute("DELETE FROM uploads")
        c.commit()
        log("Batch finished — records cleared. Next Start uploads folders fresh.")


def Credentials_from_file(cid: str):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
    import authstore
    creds = Credentials.from_authorized_user_info(authstore.load(cid))
    if creds.expired:
        creds.refresh(GoogleRequest())
        authstore.save(cid, creds)
    return creds


def insert_video(creds, path: Path, meta: dict, publish_at, test_mode: bool,
                 schedule: bool = True) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    yt = build("youtube", "v3", credentials=creds)
    status = {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    if schedule and not test_mode and publish_at:
        status["privacyStatus"] = "private"      # flips public automatically at publishAt
        status["publishAt"] = publish_at
    body = {"snippet": {"title": meta["title"], "description": meta["description"],
                        "tags": meta["tags"], "categoryId": "22"},
            "status": status}
    media = MediaFileUpload(str(path), resumable=True, chunksize=8 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media,
                             notifySubscribers=False)
    resp = None
    while resp is None:
        if _stop:
            raise RuntimeError("Upload aborted by user stop request.")
        status, resp = req.next_chunk()
    return resp["id"]


# ---------- CLI ----------

def cmd_channels():
    for cid, folder, cap in con().execute("SELECT * FROM channels"):
        print(f"{cid}  folder={folder}  cap={cap}")


def cmd_setfolder(cid, folder, cap=None):
    if not Path(folder).is_dir():
        sys.exit(f"Folder does not exist: {folder}")
    c = con()
    if cap is not None:
        try:
            cap_val = max(1, int(cap))
            c.execute("INSERT INTO channels(channel_id, folder, cap) VALUES (?,?,?) "
                      "ON CONFLICT(channel_id) DO UPDATE SET folder=excluded.folder, cap=excluded.cap", (cid, folder, cap_val))
        except ValueError:
            sys.exit(f"Invalid cap value: {cap}")
    else:
        c.execute("INSERT INTO channels(channel_id, folder) VALUES (?,?) "
                  "ON CONFLICT(channel_id) DO UPDATE SET folder=excluded.folder", (cid, folder))
        row = c.execute("SELECT cap FROM channels WHERE channel_id=?", (cid,)).fetchone()
        cap_val = row[0] if row and row[0] is not None else 5
    c.commit()
    c.close()
    print(f"OK {cid} → {folder} (cap={cap_val})")


def cmd_setcap(cid, cap):
    try:
        cap_val = max(1, int(cap))
    except ValueError:
        sys.exit(f"Invalid cap value: {cap}")
    c = con()
    c.execute("INSERT INTO channels(channel_id, cap) VALUES (?,?) "
              "ON CONFLICT(channel_id) DO UPDATE SET cap=excluded.cap", (cid, cap_val))
    c.commit()
    c.close()
    print(f"OK {cid} cap → {cap_val}")


def cmd_dryrun(folder):
    c = con()
    for p in sorted(Path(folder).iterdir()):
        if p.suffix.lower() not in VIDEO_EXT:
            continue
        title = title_from_filename(p)
        meta = assemble_metadata(title)
        slots = publish_slots(title, 1, meta.get("hours", []))
        print(f"\n📄 {p.name}")
        print(f"   title : {title}")
        print(f"   tags  : {', '.join(meta['tags'][:8]) or '—'}")
        print(f"   slot  : {slots[0] if slots else '—'}")


def selftest():
    assert title_from_filename("Sajek_tour_2026.mp4") == "Sajek Tour 2026"
    assert title_from_filename("ai_video_kivabe_banabo.mp4") == "AI Video Kivabe Banabo"
    assert title_from_filename("MY_vlog-test final .mp4") == "MY Vlog Test Final"
    s = publish_slots("test video", 2, hours=["14:00"])
    d0 = datetime.fromisoformat(s[0]); d1 = datetime.fromisoformat(s[1])
    assert d0 > datetime.now(d0.tzinfo) and d1 > d0
    c = con()
    c.execute("INSERT OR REPLACE INTO uploads VALUES ('t','x.mp4','PENDING',NULL,'T',NULL,'n')")
    assert c.execute("SELECT state FROM uploads WHERE channel_id='t'").fetchone()[0] == "PENDING"
    c.execute("DELETE FROM uploads WHERE channel_id='t'"); c.commit()
    print("✅ selftest passed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    a = sys.argv[1:]
    if a[0] == "selftest":
        selftest()
    elif a[0] == "setfolder" and len(a) >= 3:
        cmd_setfolder(a[1], a[2], a[3] if len(a) >= 4 else None)
    elif a[0] == "setcap" and len(a) >= 3:
        cmd_setcap(a[1], a[2])
    elif a[0] == "channels":
        cmd_channels()
    elif a[0] == "dryrun" and len(a) >= 2:
        cmd_dryrun(a[1])
    else:
        print(__doc__)
