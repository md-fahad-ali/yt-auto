# 📦 Batch Uploader — Detailed Build Plan

Folder → AI metadata → sequential multi-channel uploads → React sidebar UI.

---

## What we're building

**Every channel has its own configured folder** (set once in the channel's
settings). Starting a batch walks each channel → reads THAT channel's folder
→ uploads its videos → rests → next channel.

```
Channel settings (per channel, set once):
  Channel A → /Videos/A   (avatar gear icon in sidebar)
  Channel B → /Videos/B

START BATCH
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│ CHANNEL A (green dot in sidebar, folder /Videos/A)      │
│   /Videos/A/Sajek_tour_2026.mp4                         │
│     → title "Sajek Tour 2026" (from filename)           │
│     → viral tags from our index (0 quota)               │
│     → description from OpenRouter AI                    │
│     → upload via API (notifySubscribers=false)          │
│   ⏳ randomized rest 3–8 min → next file                 │
│   (cap: 5/channel/day; empty folder = skip channel)     │
│                                                         │
│ ⏸  inter-channel rest 20–40 min (no ban patterns)      │
│                                                         │
│ CHANNEL B (green dot moves, folder /Videos/B) → ...     │
└─────────────────────────────────────────────────────────┘
```

Validated by research: Google's own [youtube-bulk-uploader](https://github.com/google-marketing-solutions/youtube-bulk-uploader)
uses filename→metadata + duplicate-check-by-filename; the [multi-channel guide](https://bundle.social/blog/youtube-api-upload-guide)
mandates staggered sequential uploads.

---

## Components

### 1. `uploader.py` — the batch engine (backend core)

**Filename → title parser**
```
"Sajek_tour_2026.mp4"  → "Sajek Tour 2026"
"ai_video_kivabe.mp4"  → "AI Video Kivabe"
```
- strip extension, `_`/`-` → spaces, collapse spaces, smart title-case
  (keep Bangla characters untouched), truncate to 100 chars

**Metadata assembly per video (before any upload call):**
- **tags**: reuse the ideas engine — `canonical_topic` on title words →
  `index_videos` / `corpus_search` → `aggregate().tags[:15]` (0 quota)
- **description**: OpenRouter call —
  `POST https://openrouter.ai/api/v1/chat/completions`
  model default `meta-llama/llama-3.3-70b-instruct` (configurable),
  prompt = title + viral tags + keywords → 150–250 word description,
  hashtags at end. **Fallback without API key:** template built from
  title + tags (system still works, just less pretty)
- **category**: 22 (People & Blogs) default

**Ban-safety timing engine (from the documented rules):**

| Rule | Value | Why (source) |
|---|---|---|
| Sequential only — never parallel uploads | always | multi-channel best practice |
| `notifySubscribers=False` on every insert | always | official param for bulk uploaders — avoids notification spam |
| Randomized delay between videos | 3–8 min (config) | no robot-perfect timing |
| Per-channel daily cap | 5 (config, ≤ existing app cap) | spam-pattern avoidance |
| Inter-channel rest | 20–40 min randomized | the "rest" you asked for |
| Global daily counter | ≤100 uploads (project bucket) | hard API ceiling |
| Metadata validated BEFORE the call | always | failed calls still burn quota |

**Error-specific behavior (never one dumb retry loop):**

| API error | Action |
|---|---|
| `rateLimitExceeded` | exponential backoff (2^n + jitter), max 5 tries |
| `userRateLimitExceeded` | throttle that channel +30 min |
| `uploadRateLimitExceeded` | back off hours, resume later |
| `quotaExceeded` (daily) | STOP batch, resume after midnight PT |
| `uploadLimitExceeded` | skip channel for the day (channel-level limit) |
| 500/503 | limited retries with backoff |
| invalid metadata | skip video, log, no retry |

**State machine + resume (SQLite `uploads` table):**
```
video states: PENDING → PROCESSING → POSTED | FAILED | SKIPPED
```
- idempotency key = (channel_id, filename) — restarting the batch NEVER
  re-uploads a finished file
- crash-safe: state written after every change; same DB pattern as index.db

### 2. Channel settings + batch state in SQLite + API endpoints

**`batch.db`** (new SQLite file — consistent with index.db/research.db):

```sql
CREATE TABLE channels (
  channel_id TEXT PRIMARY KEY,
  folder     TEXT,          -- per-channel video folder (set once via UI)
  cap        INT DEFAULT 5  -- per-channel daily upload cap
);

CREATE TABLE uploads (      -- state machine + idempotency (replaces batch_state.json)
  channel_id TEXT, filename TEXT,
  state      TEXT,          -- PENDING → PROCESSING → POSTED | FAILED | SKIPPED
  video_id   TEXT,          -- YouTube ID once POSTED
  title      TEXT, error    TEXT,
  updated_at TEXT,
  PRIMARY KEY (channel_id, filename)   -- idempotency key: restarting never re-uploads
);
```

| Endpoint | Purpose |
|---|---|
| `GET /api/channels` | list authed channels: id, name, avatar URL **+ their configured folder** |
| `POST /api/channels/{id}/folder` | set/update a channel's folder `{folder}` (validates it exists, is readable) |
| `POST /api/batch/start` | `{test_mode?}` → runs ALL channels that have folders set |
| `POST /api/batch/stop` | graceful stop after current video |
| `GET /api/batch/status` | `{current_channel, channels:[{id,name,avatar,folder,state,done,total}], current_video, log_tail}` — polled every 3s |
| `GET /api/batch/preview/{channel_id}` | that channel's folder: file list + parsed titles (dry run) |

`test_mode=true` → delays become 5–10 seconds (for E2E verification).

### 3. React UI (`web/` — Vite + React, plain fetch, no heavy libs)

**Sidebar (your spec):**
- channel avatars ONLY — 44px round images
- hover → tooltip with channel name
- active channel = pulsing **green circle** ring (moves as the batch advances)
- states: idle (gray) → active (green pulse) → done (solid green ✓) →
  error/limited (red)
- **small gear icon on hover → channel settings: folder address input
  (+ optional cap)** — set once per channel

**Main panel:**
- overview row per channel: avatar + folder path + file count
- Start (runs all channels with folders set) / Stop
- current channel card: avatar, name, folder, video progress (3/12),
  current video filename, per-channel rows with ✅/⏳/⏹
- live log tail (last 8 lines)

**Serving:** `npm run build` → FastAPI serves `web/dist` at `/dashboard`;
elder upload page stays untouched at `/`.

### 4. Verification plan (must pass before done)

1. Unit: filename parser cases (English, Bangla, hyphens, long names);
   description fallback template; state resume (kill mid-batch → restart →
   no duplicate uploads)
2. E2E `test_mode`: 2 channels × 2 tiny ffmpeg videos → verify both channels
   received correct titles/tags/descriptions, `notifySubscribers=False`,
   green dot moved 1→2 in UI (opencli browser check)
3. Timing audit: real mode logs show randomized intervals, caps respected

---

## Build order

| Phase | Deliverable | Depends on |
|---|---|---|
| 1 | `uploader.py`: parser + metadata assembly + state file (CLI dry-run prints, no uploads) | — |
| 2 | `channels.json` config + folder validation + OpenRouter integration + template fallback | 1 |
| 3 | Batch worker: per-channel folder walk + timing engine + error table + real uploads (test_mode) | 1,2 |
| 4 | API endpoints + status polling | 3 |
| 5 | React sidebar dashboard (gear → folder settings) + wire to status | 4 |
| 6 | Full E2E on 2 channels (2 test videos each, in two folders) + docs update | 5 |

## Locked-in decisions (user-confirmed)

1. **OpenRouter**: key provided — `OPENROUTER_API_KEY` env var, model default
   `meta-llama/llama-3.3-70b-instruct` (template fallback still built in)
2. **Visibility + timing — native scheduling**: uploads go out as
   `privacyStatus=private` + `publishAt=<best hour>` → **YouTube flips them
   public automatically** at the scheduled time. No manual review.
   - best hours source: `aggregate().hours` (winning publish hours for the
     video's topic from the ideas engine), fallback +2h if no data
   - spread rule: consecutive videos in a channel get consecutive slots
     (next best hour + buffer), never stacked on one timestamp

## Needs from user

- export OPENROUTER_API_KEY=... in the shell before running the batch worker

## Honest limits (same rules as always)

- 100 uploads/day across ALL channels (project bucket) — the batch stops itself there
- ~7/day hidden limit possible on some projects → our error table backs off hours
- Channel-level caps vary; `uploadLimitExceeded` = that channel done for the day
- This uploads only — never likes/comments/views (the actual ban vectors)
