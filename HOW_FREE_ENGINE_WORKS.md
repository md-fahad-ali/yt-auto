# 🆓 How the Free Engine Works — Explained

The "free engine" is [index.py](index.py). It serves the **exact same viral tags**
as the paid API, but costs **zero quota per request**. This file teaches you how.

---

## The one idea everything is built on

> **Google's API answers cost quota. Remembering answers is free.**

The API charges you every time you ask. But the tags of a winning video
rarely change. So: **ask once, write the answer down, and read your notes
forever.**

That's it. Everything below is just that idea, organized.

```
        ┌──────────────────────────────────────────────┐
        │  FIRST TIME anyone asks about a topic        │
        │                                              │
 USER ──►  /api/ideas ──► search.list (1 search)  ──┐  │
        │                                            ▼  │
        │                    videos.list (1 unit = 50 videos)
        │                                            │  │
        │                    tags of winners ──► index.db
        │                    (SQLite file on your Mac) │
        └──────────────────────────────────────────────┘

        ┌──────────────────────────────────────────────┐
        │  EVERY TIME AFTER (today, next year, 10k users)
        │                                              │
 USER ──►  /api/ideas ──► read index.db ──► same tags │
        │                                              │
        │  QUOTA SPENT: 0     TIME: ~0.01 seconds     │
        └──────────────────────────────────────────────┘
```

This is exactly how vidIQ survives: they asked Google once in 2011
and have been reading their notes ever since.

---

## The three tables (index.db)

Open the database anytime:

```bash
sqlite3 index.db
```

| Table | What it stores | Example row |
|---|---|---|
| `topics` | every topic ever researched | `('cox bazar', '2026-08-27T18:00')` |
| `videos` | one row per video, **with its full tag list as JSON** | `('CciXWrcN2bI', ..., '["cox's bazar beach, ..."]')` |
| `topic_videos` | which videos belong to which topic | `('cox bazar', 'CciXWrcN2bI')` |

A video is stored once, but can belong to many topics
(cox bazar AND bangladesh travel AND beach vlog all point to the same video).

---

## The code, function by function

### 1. `con()` — opens the database

Creates the 3 tables if they don't exist. SQLite = a single file,
no server, zero setup. That's why we chose it.

### 2. `cmd_seed(topic)` — the ONE expensive call

```python
found = search_recent(topic, days=30, limit=25)   # ← 1 search (the cost!)
stats = video_stats([f["id"] for f in found])     # ← 1-2 units (50 videos/call)
store_videos(c, topic, stats)                     # ← free: just SQL INSERTs
```

Runs ONCE per topic, ever. After this, the topic exists in your notes.

### 3. `channel_rss_ids(channel_id)` — the zero-quota refresh magic

```python
url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
```

Google publishes a **public RSS feed for every channel** — the latest 15
uploads, no API key, no quota, free forever. This is how the index discovers
new videos from tracked channels without spending anything.

(A real app cut its quota from 1,440,000 units/day to ~100 using exactly
this trick: https://zenn.dev/harness/articles/youtube-data-api-rss-quota-reduction)

### 4. `uploads_playlist_ids(channel_id)` — the 1-unit backup

If RSS fails: every channel's uploads playlist = channel ID with `UC`→`UU`.
`playlistItems.list` costs 1 unit instead of a 100-unit search. 100× cheaper.

### 5. `index_videos(c, topic)` — reading your notes

One SQL query: all videos for this topic, best views first. Free, instant.

### 6. `aggregate(winners)` — turning videos into "viral tags"

This is where the tag list you see in the UI comes from:

```python
for w in winners:                    # top 15 videos by views
    for t in w["tags"]:              # their REAL tags (from Google)
        tag_counts[t.strip()] += 1   # count how many winners share each tag
```

**A tag used by many winning videos = a viral tag.** No generation, no AI,
no invention — pure counting of what Google already told us.
It also counts: hashtags from titles/descriptions, word-pairs from titles
(= title patterns), and publish hours (= best upload times).

### 7. How the website uses it ([app.py](app.py) `/api/ideas`)

```
user types topic
  →  canonical_topic()          # fixes typos via Google autocomplete ("sajeg"→"sajek")
  →  is it in index.db?  ──yes──►  serve from index        (0 quota)  ⚡
                          └─no──►  live API research        (1 search)
                                  + background seed          → next time it's free
```

---

## The quota math — why this scales to 10,000 users

| Action | Cost |
|---|---|
| Seeding a NEW topic (once, ever) | 1 search + ~2 units |
| Serving that topic to user #2, #3, ... #10,000 | **0** |
| Refreshing via RSS | **0** |
| Refreshing via playlist fallback | 1 unit per channel |

100 searches/day budget = **100 new topics per day = 36,500 topics per year.**
Your customers will search the same few thousand topics repeatedly —
after the first search, every serving is free.

---

## Proof it's not fake (audit trail)

1. The DB stores the raw JSON Google returned — compare anytime:
   ```bash
   .venv/bin/python index.py compare "cox bazar"
   ```
   Runs BOTH engines side by side, shows tag-by-tag ✅ matches.
2. Or verify one video yourself: open it on YouTube, check its tags
   with any tag-viewer — identical to what your DB stores.
3. Delete `index.db` → free engine serves nothing until it asks Google again.
   Fake data can't survive that.

---

## Your daily commands

```bash
.venv/bin/python index.py seed "new topic"      # once per new topic
.venv/bin/python index.py refresh "topic"       # weekly — RSS, ~free
.venv/bin/python index.py tags "topic"          # see the free tags
.venv/bin/python index.py compare "topic"       # quality check vs live API
```

## Honest limits

- The index is only as fresh as your last refresh — hot niches need
  `refresh` more often (RSS makes that free)
- It only knows topics someone searched before — new topics still need
  1 live search (that's the discovery budget)
- Google's search results themselves drift between calls — the index
  freezes ONE moment of truth; `compare` tells you if it drifted
