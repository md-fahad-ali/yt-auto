#!/usr/bin/env python
"""yt-auto analytics — REAL channel performance from the official YouTube Analytics API.

Data only the channel owner can see: views, watch time, retention, traffic sources,
subscriber activity — exact numbers from Google, not estimates.

Commands:
  overview [days]            channel totals
  videos [days] [limit]      per-video performance, best first
  traffic [video_id] [days]  where views come from (search/suggested/browse)
  retention <video_id>       average % watched + avg view duration
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

BASE = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]

TRAFFIC_LABELS = {
    "YT_SEARCH": "🔍 Search", "RELATED_VIDEO": "🔗 Suggested",
    "YT_CHANNEL": "📺 Channel page", "YT_PLAYLIST_PAGE": "📋 Playlist",
    "NOTIFICATION": "🔔 Notifications", "SUBSCRIBER": "🔔 Sub feed",
    "YT_OTHER_PAGE": "📄 Other pages", "NO_LINK_OTHER": "🌐 Direct/other",
    "SHORTS": "📱 Shorts feed", "HASHTAGS": "#️⃣ Hashtags",
    "SOUND_PAGE": "🎵 Sound page", "ADVERTISING": "💰 Ads",
    "ANNOTATION": "Annotation", "CAMPAIGN_CARD": "Campaign",
    "END_SCREEN": "End screen", "EXTERNAL_URL": "External",
    "PROMOTED": "Promoted", "SUBSCRIBER_TOWER": "Sub tower",
}


def analytics_client(cid: str):
    import authstore
    creds = Credentials.from_authorized_user_info(authstore.load(cid))
    if creds.expired or not creds.valid:
        creds.refresh(GoogleRequest())
        authstore.save(cid, creds)
    return build("youtubeanalytics", "v2", credentials=creds)


def pick_token() -> tuple[Path, str]:
    import authstore
    tokens = list(authstore.load_all().keys())
    if not tokens:
        sys.exit("No authenticated channels — sign in at localhost:8000 first")
    if len(sys.argv) >= 3 and sys.argv[1] in ("traffic", "retention") and sys.argv[2].startswith("UC"):
        # 3rd form: traffic <channel_file> <video_id> — not typical; default to first
        pass
    return tokens[0], tokens[0]


def daterange(days: int) -> tuple[str, str]:
    end = date.today() - timedelta(days=1)   # yesterday: analytics lags ~1-2 days
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def q(**params):
    """Run an analytics query with standard defaults."""
    yt = analytics_client(pick_token()[0])
    defaults = {"ids": "channel==MINE", "startDate": daterange(28)[0],
                "endDate": daterange(28)[1]}
    defaults.update(params)
    return yt.reports().query(**defaults).execute()


def cmd_overview(days: int = 28):
    start, end = daterange(days)
    r = q(startDate=start, endDate=end,
          metrics="views,estimatedMinutesWatched,averageViewDuration,"
                  "averageViewPercentage,subscribersGained,subscribersLost,likes,comments")
    c = {k: float(v) for k, v in zip(r["columnHeaders"], [0] * 0)} if False else None
    vals = r["rows"][0] if r.get("rows") else [0] * 8
    h = [x["name"] for x in r["columnHeaders"]]
    m = dict(zip(h, vals))
    mins = m.get("estimatedMinutesWatched", 0)
    avd = m.get("averageViewDuration", 0)
    print(f"Channel performance — last {days} days ({start} → {end})")
    print("=" * 46)
    print(f"Views            : {int(m.get('views', 0)):>10,}")
    print(f"Watch time       : {int(mins):>10,} min ({mins/60:.1f} hrs)")
    print(f"Avg view duration: {int(avd):>10,} s")
    print(f"Avg retention    : {m.get('averageViewPercentage', 0):>9.1f}%")
    print(f"Subs gained/lost : {int(m.get('subscribersGained', 0)):>4} / -{int(m.get('subscribersLost', 0))}")
    print(f"Likes / comments : {int(m.get('likes', 0)):>4} / {int(m.get('comments', 0))}")


def cmd_videos(days: int = 28, limit: int = 15):
    start, end = daterange(days)
    r = q(startDate=start, endDate=end, metrics="views,estimatedMinutesWatched,"
          "averageViewPercentage,subscribersGained,likes",
          dimensions="video", sort="-views", maxResults=limit)
    rows = r.get("rows", [])
    if not rows:
        print(f"No video data in the last {days} days (videos too new or none published).")
        return
    print(f"Top videos — last {days} days (exact Google data)")
    print(f"{'VIEWS':>9} {'WATCH_M':>8} {'RET%':>6} {'SUBS+':>6}  VIDEO")
    print("-" * 78)
    for vid, views, mins, ret, subs, likes in rows:
        print(f"{views:>9,} {mins:>8,} {ret:>5.0f}% {subs:>6,}  {vid}")
    print("\n(Video IDs — open youtube.com/watch?v=<ID>)")


def cmd_traffic(video_id: str = None, days: int = 28):
    start, end = daterange(days)
    params = dict(startDate=start, endDate=end,
                  metrics="views,estimatedMinutesWatched",
                  dimensions="insightTrafficSourceType", sort="-views")
    if video_id:
        params["filters"] = f"video=={video_id}"
    r = q(**params)
    rows = r.get("rows", [])
    if not rows:
        print("No traffic data yet."); return
    total = sum(x[1] for x in rows)
    print(f"Traffic sources{' — ' + video_id if video_id else ''} (last {days}d)")
    print("-" * 44)
    for src, views, mins in rows:
        pct = views / total * 100 if total else 0
        label = TRAFFIC_LABELS.get(src, src)
        print(f"{label:<22} {views:>9,} views  {pct:>5.1f}%")
    print(f"\nSearch high = SEO working. Suggested high = thumbnails/topic working.")


def cmd_retention(video_id: str):
    r = q(metrics="averageViewPercentage,averageViewDuration,views,"
          "estimatedMinutesWatched", filters=f"video=={video_id}")
    rows = r.get("rows")
    if not rows:
        print("No retention data for that video."); return
    ret, avd, views, mins = rows[0]
    print(f"Retention — {video_id}")
    print(f"  Average % watched : {ret:.1f}%")
    print(f"  Avg view duration : {int(avd)}s")
    print(f"  Views             : {int(views):,}")
    print(f"  Total watch time  : {int(mins):,} min")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    try:
        if cmd == "overview":
            cmd_overview(int(sys.argv[2]) if len(sys.argv) > 2 else 28)
        elif cmd == "videos":
            cmd_videos(int(sys.argv[2]) if len(sys.argv) > 2 else 28)
        elif cmd == "traffic":
            cmd_traffic(sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "all" else None)
        elif cmd == "retention" and len(sys.argv) >= 3:
            cmd_retention(sys.argv[2])
        else:
            print(__doc__)
    except HttpError as e:
        print(f"YouTube API error {e.resp.status}: {e._get_reason().strip()}")
        if "insufficientPermissions" in str(e):
            print("\nFix: re-login at http://localhost:8000 (logout → login) to grant the new analytics permission.")
