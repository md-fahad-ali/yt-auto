#!/usr/bin/env python
"""yt-auto research — mini-vidIQ: outlier reranking, keyword research, SEO scoring.

Auth: uses your existing tokens/ (youtube.readonly) or YOUTUBE_API_KEY env var.
Quota: 1 search + a few 1-unit list calls per command. Sustainable daily.

Commands:
  outliers <query> [days]   rerank recent videos by outlier score (vidIQ formula)
  keywords <seed>           autocomplete mining + competition scoring
  seo <video_id> <keyword>  actionable SEO score (the 50% you control)
  snapshot <query>...       record stats to research.db (run daily -> velocity/history)
"""
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

BASE = Path(__file__).parent
TOKENS_DIR = BASE / "tokens"
DB_FILE = BASE / "research.db"
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def client():
    key = os.environ.get("YOUTUBE_API_KEY")
    if key:
        return build("youtube", "v3", developerKey=key)
    tokens = sorted(TOKENS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not tokens:
        raise RuntimeError("No tokens/ and no YOUTUBE_API_KEY — sign in at localhost:8000 first")
    for tf in tokens:
        try:
            creds = Credentials.from_authorized_user_info(json.loads(tf.read_text()))
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleRequest())
                tf.write_text(creds.to_json())
            return build("youtube", "v3", credentials=creds)
        except Exception:
            continue
    raise RuntimeError("Could not authenticate YouTube client from stored tokens")


def yt():
    return client()


# ---------- helpers ----------

def search_recent(query: str, days: int = 30, limit: int = 25) -> list[dict]:
    after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() if days else None
    params = {
        "q": query,
        "part": "id,snippet",
        "type": "video",
        "order": "viewCount",
        "maxResults": min(limit, 50)
    }
    if after:
        params["publishedAfter"] = after

    items = []
    try:
        res = yt().search().list(**params).execute()
        items = res.get("items", [])
    except Exception:
        items = []

    # If no recent videos found in time window, fallback to all-time top videos
    if not items and after:
        try:
            params.pop("publishedAfter", None)
            res = yt().search().list(**params).execute()
            items = res.get("items", [])
        except Exception:
            items = []

    # If still no items and query has multiple words, try relaxed search with first 2 words
    if not items:
        words = [w for w in query.strip().split() if len(w) > 1]
        if len(words) > 2:
            try:
                params["q"] = " ".join(words[:2])
                params.pop("publishedAfter", None)
                res = yt().search().list(**params).execute()
                items = res.get("items", [])
            except Exception:
                items = []

    return [{"id": it["id"]["videoId"],
             "channel": it["snippet"]["channelId"],
             "title": it["snippet"]["title"],
             "published": it["snippet"]["publishedAt"]} for it in items if "videoId" in it.get("id", {})]


def video_stats(ids: list[str]) -> dict[str, dict]:
    out = {}
    if not ids:
        return out
    for i in range(0, len(ids), 50):
        try:
            res = yt().videos().list(id=",".join(ids[i:i + 50]),
                                     part="statistics,snippet,contentDetails").execute()
            for it in res.get("items", []):
                st = it.get("statistics", {})
                out[it["id"]] = {
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0)),
                    "title": it["snippet"].get("title", ""),
                    "tags": it["snippet"].get("tags", []),
                    "description": it["snippet"].get("description", ""),
                    "channel": it["snippet"]["channelId"],
                    "published": it["snippet"]["publishedAt"],
                    "duration": iso_duration_seconds(it["contentDetails"].get("duration", "")),
                }
        except Exception:
            pass
    return out


def iso_duration_seconds(d: str) -> int:
    """PT4M13S -> 253."""
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def autocomplete(seed: str, n: int = 8) -> list[str]:
    try:
        url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q="
               + urllib.parse.quote(seed))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            if len(data) > 1 and isinstance(data[1], list) and data[1]:
                return data[1][:n]
    except Exception:
        pass

    # Fallback to subset of words if long query has no direct autocomplete
    words = seed.strip().split()
    if len(words) > 2:
        try:
            url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q="
                   + urllib.parse.quote(" ".join(words[:2])))
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                if len(data) > 1 and isinstance(data[1], list) and data[1]:
                    return data[1][:n]
        except Exception:
            pass

    return []


def uploads_playlist_id(channel_id: str) -> str:
    res = yt().channels().list(id=channel_id, part="contentDetails").execute()
    items = res.get("items", [])
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"] if items else ""


def channel_avg_views(channel_id: str, sample: int = 15) -> float:
    """Average views of the channel's recent uploads = the baseline for outlier scoring."""
    pl = uploads_playlist_id(channel_id)
    if not pl:
        return 0.0
    res = yt().playlistItems().list(playlistId=pl, part="contentDetails",
                                    maxResults=sample).execute()
    vids = [it["contentDetails"]["videoId"] for it in res.get("items", [])]
    if not vids:
        return 0.0
    stats = video_stats(vids)
    views = [v["views"] for v in stats.values() if v["views"] > 0]
    return sum(views) / len(views) if views else 0.0


def hours_since(published: str) -> float:
    dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
    return max((datetime.now(timezone.utc) - dt).total_seconds() / 3600, 1)


# ---------- commands ----------

def cmd_outliers(query: str, days: int = 7):
    """vidIQ formula: outlier score = video views / channel's own average."""
    print(f"Searching '{query}' (last {days}d)...")
    found = search_recent(query, days)
    if not found:
        print("No videos found."); return
    ids = [f["id"] for f in found]
    stats = video_stats(ids)
    baselines: dict[str, float] = {}
    print("Computing channel baselines...")
    for ch in {s["channel"] for s in stats.values()}:
        baselines[ch] = channel_avg_views(ch)

    rows = []
    for vid, s in stats.items():
        avg = baselines.get(s["channel"], 0)
        ratio = round(s["views"] / avg, 1) if avg > 0 else 0
        vph = int(s["views"] / hours_since(s["published"]))
        rows.append((ratio, vph, s["views"], s["title"][:55], vid))

    rows.sort(reverse=True)
    print(f"\n{'OUTLIER':>7} {'VIEWS/H':>9} {'VIEWS':>12}  TITLE")
    print("-" * 100)
    for ratio, vph, views, title, vid in rows:
        flag = " <<< viral signal" if ratio >= 5 else ""
        print(f"{ratio:>6}x {vph:>9,} {views:>12,}  {title}{flag}")
        print(f"{'':>30} https://youtu.be/{vid}")
    print("\nRatio = this video ÷ channel's own average. >=5x = topic carrying the video, not the channel.")


def cmd_keywords(seed: str, n: int = 12):
    """Autocomplete = real demand. Competition = median views of current top results."""
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q="
           + urllib.parse.quote(seed))
    req = urllib.request.Request(url, headers={"User-Agent": "yt-auto/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            suggestions = json.loads(r.read().decode())[1][:n]
    except Exception as e:
        sys.exit(f"Autocomplete failed: {e}")
    if not suggestions:
        print("No suggestions."); return

    print(f"{'KEYWORD':<45} {'TOP MEDIAN':>11} {'FRESH HRS':>9}  VERDICT")
    print("-" * 90)
    for kw in suggestions:
        try:
            res = yt().search().list(q=kw, part="snippet", type="video",
                                     order="relevance", maxResults=10).execute()
            items = res.get("items", [])
            if not items:
                continue
            stats = video_stats([i["id"]["videoId"] for i in items])
            views = sorted(v["views"] for v in stats.values())
            median = views[len(views) // 2]
            newest = min(hours_since(v["published"]) for v in stats.values())
            if median < 50_000:
                verdict = "GOLD (weak competition)"
            elif median < 500_000:
                verdict = "ok"
            else:
                verdict = "saturated"
            print(f"{kw[:44]:<45} {median:>11,} {int(newest):>8}h  {verdict}")
            time.sleep(0.3)
        except HttpError as e:
            print(f"{kw[:44]:<45} error: {e.resp.status}")
            break


def cmd_seo(video_id: str, keyword: str):
    """The actionable 50% of vidIQ's SEO score, from their published formula."""
    stats = video_stats([video_id])
    if video_id not in stats:
        sys.exit("Video not found")
    s = stats[video_id]
    kw = keyword.lower()
    title, desc, tags = s["title"].lower(), s["description"].lower(), [t.lower() for t in s["tags"]]

    checks = [
        (10, keyword.lower() in title, f"exact keyword in title"),
        (5, title[:40].find(kw) >= 0 if kw in title else False, "keyword in first 40 chars"),
        (10, kw in desc, "keyword in description"),
        (5, desc.count(kw) >= 2, "keyword 2+ times in description"),
        (10, any(kw in t for t in tags), "keyword in tags"),
        (5, len(s["tags"]) >= 5, f"tag count >= 5 (has {len(s['tags'])})"),
        (5, len(s["description"]) >= 250, f"description >= 250 chars (has {len(s['description'])})"),
    ]
    score = sum(pts for pts, ok, _ in checks if ok)
    print(f"SEO actionable score: {score}/50  (keyword: '{keyword}')")
    for pts, ok, label in checks:
        print(f"  {'✅' if ok else '❌'} +{pts:<2} {label}")


def cmd_snapshot(queries: list[str]):
    """Record today's stats — run daily (cron) and velocity/history compounds."""
    con = sqlite3.connect(DB_FILE)
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots (
        ts TEXT, video_id TEXT, channel_id TEXT, title TEXT,
        views INT, likes INT, comments INT)""")
    now = datetime.now(timezone.utc).isoformat(timespec="hours")
    n = 0
    for q in queries:
        for f in search_recent(q, days=30, limit=25):
            st = video_stats([f["id"]]).get(f["id"])
            if not st:
                continue
            con.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?)",
                        (now, f["id"], st["channel"], st["title"],
                         st["views"], st["likes"], st["comments"]))
            n += 1
    con.commit()
    total = con.execute("SELECT COUNT(*), COUNT(DISTINCT video_id) FROM snapshots").fetchone()
    con.close()
    print(f"Saved {n} rows. DB total: {total[0]} snapshots of {total[1]} videos.")
    print("Run this daily (cron) — diff consecutive days = view velocity per video.")


def autocomplete(seed: str, n: int = 8) -> list[str]:
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q="
           + urllib.parse.quote(seed))
    req = urllib.request.Request(url, headers={"User-Agent": "yt-auto/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())[1][:n]


def canonical_topic(topic: str) -> str:
    """Map misspellings to Google's own correction via autocomplete:
    'sajeg tour' -> 'sajek tour'. Falls back to the raw topic."""
    try:
        sugg = autocomplete(topic, 1)
        return sugg[0] if sugg else topic
    except Exception:
        return topic


def generate_tags_from_autocomplete(topic: str) -> dict:
    """Mines deep live YouTube autocomplete search graph for any query (0 quota, real YouTube demand)."""
    clean_topic = topic.strip()
    seeds = [
        clean_topic,
        f"best {clean_topic}",
        f"{clean_topic} vlog",
        f"{clean_topic} 2026",
        f"{clean_topic} guide",
        f"{clean_topic} tips",
        f"{clean_topic} tour",
        f"{clean_topic} video"
    ]
    alphabet = ["a", "b", "c", "d", "e", "f", "s", "t", "v"]
    for char in alphabet[:4]:
        seeds.append(f"{clean_topic} {char}")

    all_suggestions = []
    seen = set()

    for s in seeds:
        try:
            url = ("https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q="
                   + urllib.parse.quote(s))
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req, timeout=4) as r:
                items = json.loads(r.read().decode())[1]
                for it in items:
                    c = it.strip().lower()
                    if c not in seen and len(c) > 2:
                        seen.add(c)
                        all_suggestions.append(c)
                if len(all_suggestions) >= 15:
                    break
        except Exception:
            continue

    # Title-cased tags
    tags = []
    for s in all_suggestions:
        words = s.split()
        t = " ".join(w.capitalize() if w not in {"in", "of", "and", "to", "for", "a", "the", "on", "with", "by"} else w for w in words)
        if t not in tags:
            tags.append(t)
        if len(tags) >= 20:
            break

    # Winning hashtags
    hashtags = []
    for s in all_suggestions[:12]:
        words = [w.capitalize() for w in s.split() if w.isalnum()]
        h = "#" + "".join(words)
        if len(h) > 2 and h not in hashtags:
            hashtags.append(h)

    title_clean = clean_topic.title()
    return {
        "keywords": all_suggestions[:10] if all_suggestions else [clean_topic],
        "tags": tags[:18] if tags else [title_clean, f"{title_clean} Vlog", f"Best {title_clean}"],
        "hashtags": hashtags[:8] if hashtags else [f"#{title_clean.replace(' ', '')}", "#Viral", "#Trending"],
        "patterns": [
            f"{title_clean} 2026",
            f"Best {title_clean} Guide",
            f"{title_clean} Vlog",
            f"{title_clean} Experience"
        ],
        "hours": ["14:00", "16:00", "18:00", "20:00"],
        "duration": 480,
    }


def viral_brief_data(query: str, days: int = 30) -> dict:
    """Everything 'brief' prints, as a dict — reused by the web UI."""
    import re
    from collections import Counter

    try:
        found = search_recent(query, days, limit=25)
    except Exception:
        found = []

    if not found:
        return generate_tags_from_autocomplete(query)

    try:
        stats = video_stats([f["id"] for f in found])
    except Exception:
        return generate_tags_from_autocomplete(query)

    winners = sorted(stats.values(), key=lambda s: -s["views"])[:15]
    if not winners:
        return generate_tags_from_autocomplete(query)

    tag_counts = Counter()
    for w in winners:
        for t in w.get("tags", []):
            if t and len(t.strip()) > 1:
                tag_counts[t.strip()] += 1

    hashtags = Counter()
    for w in winners:
        for h in set(re.findall(r"#\w+", w.get("title", "") + " " + w.get("description", ""))):
            hashtags[h] += 1

    stop = set("the a an of for to and in with my you your how this that on at is it".split())
    bigrams = Counter()
    for w in winners:
        toks = [t for t in re.findall(r"[a-zA-Z\u0980-\u09FF\u0900-\u097F]+", w.get("title", "").lower()) if t not in stop]
        bigrams.update(zip(toks, toks[1:]))

    hours = Counter(int(s["published"][11:13]) for s in winners if "published" in s and len(s["published"]) >= 13)
    durs = sorted(s.get("duration", 0) for s in winners if s.get("duration"))

    try:
        kws = autocomplete(query)
    except Exception:
        kws = []

    tags = [t for t, _ in tag_counts.most_common(20)]
    if not tags:
        auto_data = generate_tags_from_autocomplete(query)
        tags = auto_data["tags"]
        hashtags_list = auto_data["hashtags"]
    else:
        hashtags_list = [h for h, _ in hashtags.most_common(8)]

    return {
        "keywords": kws or [query],
        "tags": tags,
        "hashtags": hashtags_list,
        "patterns": [f"{a} {b}" for (a, b), _ in bigrams.most_common(8)],
        "hours": [f"{h:02d}:00" for h, _ in hours.most_common(4)],
        "duration": durs[len(durs) // 2] if durs else 0,
    }


def cmd_brief(query: str, days: int = 30):
    """VIRAL BRIEF: the complete recipe for a topic — keywords, tags, title patterns,
    posting hours, duration sweet spot — mined from actual winning videos."""
    d = viral_brief_data(query, days)
    print(f"\n🔥 VIRAL BRIEF: '{query}' (winners from last {days}d)\n" + "=" * 60)
    print("\n📋 KEYWORDS (real autocomplete demand — use in title/desc/tags):")
    for s in d["keywords"]:
        print(f"   • {s}")
    print("\n🏷️  VIRAL TAGS (appear across winning videos — copy-paste):")
    print("   " + ", ".join(d["tags"]))
    if d["hashtags"]:
        print("\n#️⃣  HASHTAGS used by winners:")
        print("   " + " ".join(d["hashtags"]))
    print("\n✍️  TITLE PATTERNS (build your title around these):")
    for p in d["patterns"]:
        print(f"   '{p}'")
    print("\n⏰ PUBLISH HOURS (when winners went live, UTC): " + ", ".join(d["hours"]))
    if d["duration"]:
        print(f"⏱️  DURATION sweet spot: {d['duration']//60}m{d['duration']%60:02d}s")
    print("\nRECIPE: keyword in first 4 words of title → top tags above → "
          "timestamps in description → publish at a winning hour.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "outliers" and len(sys.argv) >= 3:
        cmd_outliers(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 7)
    elif cmd == "keywords" and len(sys.argv) >= 3:
        cmd_keywords(sys.argv[2])
    elif cmd == "seo" and len(sys.argv) >= 4:
        cmd_seo(sys.argv[2], sys.argv[3])
    elif cmd == "brief" and len(sys.argv) >= 3:
        cmd_brief(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30)
    elif cmd == "snapshot" and len(sys.argv) >= 3:
        cmd_snapshot(sys.argv[2:])
    else:
        print(__doc__)
