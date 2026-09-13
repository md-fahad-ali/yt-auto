#!/usr/bin/env python
"""yt-auto index — the optimized engine: search once, index forever.

Same viral-tag output as research.py's live engine, but served from a local
SQLite index refreshed via channel RSS (0 quota) + 1-unit batch harvests.
Kept side-by-side with the live engine for benchmarking (compare command).

Commands:
  seed <topic>       spend 1 search, harvest winners into the index
  refresh <topic>    RSS-refresh known channels (0 quota) + harvest new videos
  tags <topic>       aggregated viral tags from the index
  compare <topic>    live engine vs index engine, side-by-side + overlap %
"""
import json
import os
import re
import sqlite3
import sys
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from research import search_recent, video_stats, autocomplete

BASE = Path(os.environ["YT_AUTO_DATA"]) if os.environ.get("YT_AUTO_DATA") else Path(__file__).parent
DB = BASE / "index.db"
NS = {"yt": "http://www.youtube.com/xml/schemas/2015", "a": "http://www.w3.org/2005/Atom"}


def con():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS topics(topic TEXT PRIMARY KEY, seeded_at TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS videos(video_id TEXT PRIMARY KEY, channel_id TEXT,
        title TEXT, published TEXT, views INT, tags TEXT, description TEXT, fetched_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS topic_videos(topic TEXT, video_id TEXT,
        PRIMARY KEY(topic, video_id))""")
    c.commit()
    return c


def store_videos(c, topic: str, stats: dict):
    now = datetime.now(timezone.utc).isoformat(timespec="hours")
    for vid, s in stats.items():
        c.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?)",
                  (vid, s["channel"], s["title"], s["published"], s["views"],
                   json.dumps(s["tags"]), s["description"], now))
        c.execute("INSERT OR IGNORE INTO topic_videos VALUES (?,?)", (topic, vid))


def cmd_seed(topic: str):
    found = search_recent(topic, days=30, limit=25)
    if not found:
        print(f"No results for '{topic}'."); return
    stats = video_stats([f["id"] for f in found])
    c = con()
    store_videos(c, topic, stats)
    c.execute("INSERT OR REPLACE INTO topics VALUES (?,?)",
              (topic, datetime.now(timezone.utc).isoformat(timespec="hours")))
    c.commit()
    chans = len({s["channel"] for s in stats.values()})
    print(f"Seeded '{topic}': {len(stats)} videos, {chans} channels now tracked. "
          f"Cost: 1 search + 2 units. Future refreshes: ~0.")


def channel_rss_ids(channel_id: str) -> list[str]:
    """Official public feed — 0 quota. Latest 15 uploads."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yt-auto/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            root = ET.fromstring(r.read())
        return [e.find("yt:videoId", NS).text for e in root.findall("a:entry", NS)]
    except Exception:
        return []


def uploads_playlist_ids(channel_id: str) -> list[str]:
    """1-unit fallback when RSS fails. UCxxx -> UUxxx, 50 videos per call."""
    from research import yt
    pl = "UU" + channel_id[2:]
    try:
        res = yt().playlistItems().list(playlistId=pl, part="contentDetails",
                                        maxResults=50).execute()
        return [i["contentDetails"]["videoId"] for i in res.get("items", [])]
    except Exception:
        return []


def cmd_refresh(topic: str):
    c = con()
    chans = [r[0] for r in c.execute(
        "SELECT DISTINCT channel_id FROM videos v JOIN topic_videos t ON v.video_id=t.video_id "
        "WHERE t.topic=?", (topic,))]
    if not chans:
        print(f"'{topic}' not seeded — run: index.py seed {topic}"); return
    new_ids, rss_hits, rss_fails = [], 0, 0
    for ch in chans:
        ids = channel_rss_ids(ch)
        if ids:
            rss_hits += 1
        else:
            rss_fails += 1
            ids = uploads_playlist_ids(ch)
        known = {r[0] for r in c.execute(
            "SELECT video_id FROM videos WHERE channel_id=?", (ch,))}
        new_ids += [i for i in ids if i not in known]
    stats = video_stats(new_ids) if new_ids else {}
    store_videos(c, topic, stats)
    total = c.execute("SELECT COUNT(*) FROM topic_videos WHERE topic=?", (topic,)).fetchone()[0]
    c.commit()
    print(f"Refreshed '{topic}': {rss_hits} channels via RSS (0 quota), "
          f"{rss_fails} via playlist fallback (1 unit each), "
          f"+{len(stats)} new videos. Index now {total} videos.")


def index_videos(c, topic: str) -> list[dict]:
    rows = c.execute(
        "SELECT v.video_id, title, published, views, tags, description FROM videos v "
        "JOIN topic_videos t ON v.video_id=t.video_id WHERE t.topic=? ORDER BY views DESC",
        (topic,)).fetchall()
    return [{"id": r[0], "title": r[1], "published": r[2], "views": r[3],
             "tags": json.loads(r[4]), "description": r[5]} for r in rows]


def aggregate(winners: list[dict]) -> dict:
    tag_counts, hashtags, bigrams, hours = Counter(), Counter(), Counter(), Counter()
    stop = set("the a an of for to and in with my you your how this that on at is it".split())
    for w in winners:
        for t in w["tags"]:
            tag_counts[t.strip()] += 1
        for h in set(re.findall(r"#\w+", w["title"] + " " + w["description"])):
            hashtags[h] += 1
        toks = [t for t in re.findall(r"[a-zA-Z\u0980-\u09FF\u0900-\u097F]+", w["title"].lower())
                if t not in stop]
        bigrams.update(zip(toks, toks[1:]))
        hours[int(w["published"][11:13])] += 1
    return {"tags": [t for t, _ in tag_counts.most_common(20)],
            "hashtags": [h for h, _ in hashtags.most_common(8)],
            "patterns": [f"{a} {b}" for (a, b), _ in bigrams.most_common(8)],
            "hours": [f"{h:02d}:00" for h, _ in hours.most_common(4)]}


def corpus_search(topic: str, min_hits: int = 3) -> list[dict]:
    """Full-text search over YOUR harvested videos — answers topics never
    seeded, at 0 quota. This is the vidIQ move: search your own corpus."""
    terms = [t for t in re.findall(r"\w{3,}", topic)][:5]
    if not terms:
        return []
    where = " AND ".join(
        f"(title LIKE ? OR tags LIKE ? OR description LIKE ?)" for _ in terms)
    params = []
    for t in terms:
        like = f"%{t}%"
        params += [like, like, like]
    rows = con().execute(
        f"SELECT video_id, title, published, views, tags, description FROM videos "
        f"WHERE {where} ORDER BY views DESC LIMIT 25", params).fetchall()
    vids = [{"id": r[0], "title": r[1], "published": r[2], "views": r[3],
             "tags": json.loads(r[4]), "description": r[5]} for r in rows]
    return vids if len(vids) >= min_hits else []


def cmd_harvest(regions: str = "US,GB,CA,AU,BD,IN,PK"):
    """Day-one corpus filler: the official trending chart, 1 unit per 50 videos.
    No search.list, no seeds needed — the viral videos come to you."""
    from research import yt
    total = 0
    c = con()
    for region in regions.split(","):
        try:
            res = yt().videos().list(chart="mostPopular", regionCode=region.strip(),
                                     part="snippet,statistics,contentDetails",
                                     maxResults=50).execute()
            items = res.get("items", [])
            stats = {}
            for it in items:
                st = it.get("statistics", {})
                stats[it["id"]] = {
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0)),
                    "title": it["snippet"].get("title", ""),
                    "tags": it["snippet"].get("tags", []),
                    "description": it["snippet"].get("description", ""),
                    "channel": it["snippet"]["channelId"],
                    "published": it["snippet"]["publishedAt"],
                    "duration": 0,
                }
            if stats:
                store_videos(c, f"trending:{region.strip()}", stats)
                total += len(stats)
        except Exception as e:
            print(f"  {region}: {e}")
    c.commit()
    n = c.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    print(f"Harvested {total} trending videos. Corpus total: {n} videos. "
          f"Cost: {len(regions.split(','))} units — no searches used.")


def cmd_tags(topic: str):
    c = con()
    vids = index_videos(c, topic)
    if not vids:
        print(f"'{topic}' not in index — run: index.py seed {topic}"); return
    d = aggregate(vids[:15])
    try:
        d["keywords"] = autocomplete(topic)
    except Exception:
        d["keywords"] = []
    print(f"INDEX tags for '{topic}' ({len(vids)} videos, 0 quota to serve):")
    print("🏷️  " + ", ".join(d["tags"]))
    if d["hashtags"]:
        print("#️⃣  " + " ".join(d["hashtags"]))


def cmd_compare(topic: str):
    from research import viral_brief_data
    c = con()
    live = viral_brief_data(topic, days=30)
    vids = index_videos(c, topic)
    idx = aggregate(vids[:15]) if vids else {"tags": []}

    lt, it = live["tags"][:10], idx["tags"][:10]
    overlap = len(set(lt) & set(it))
    pct = int(overlap / max(len(set(lt) | set(it)), 1) * 100)

    print(f"\n⚖️  BENCHMARK '{topic}': LIVE search vs INDEX\n" + "=" * 70)
    print(f"{'LIVE (fresh, costs quota)':<35} INDEX (stored, 0 quota)")
    print("-" * 70)
    for i in range(max(len(lt), len(it))):
        l = lt[i] if i < len(lt) else ""
        r = it[i] if i < len(it) else ""
        match = " ✅" if l and l == r else ""
        print(f"{str(i+1)+'. '+l:<35} {str(i+1)+'. '+r}{match}")
    print("-" * 70)
    print(f"Overlap: {overlap} common tags — {pct}% agreement")
    print(f"Videos used: live=top 25 searched / index={len(vids)} stored")
    print(f"Quota: live=1 search + 2 units / index=0")
    print(f"\n{pct >= 60}→ {'engines AGREE — index is trustworthy for this topic' if pct >= 60 else 'low overlap — refresh index or niche too new'}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "seed":
        cmd_seed(sys.argv[2])
    elif cmd == "refresh":
        cmd_refresh(sys.argv[2])
    elif cmd == "harvest":
        cmd_harvest(sys.argv[2] if len(sys.argv) > 2 else "US,GB,CA,AU,BD,IN,PK")
    elif cmd == "tags":
        cmd_tags(sys.argv[2])
    elif cmd == "compare":
        cmd_compare(sys.argv[2])
    else:
        print(__doc__)
