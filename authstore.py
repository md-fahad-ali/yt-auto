"""Single source of truth for authenticated channels: batch.db.

Replaces tokens/*.json — all channel logins live in the channel_auth table.
The .db file is now a secret (like .env): never commit or share it.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
DB = BASE / "batch.db"


def _con():
    c = sqlite3.connect(DB, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS channel_auth(
        channel_id TEXT PRIMARY KEY,
        name       TEXT,
        token_json TEXT,
        updated_at TEXT)""")
    c.commit()
    return c


def save(channel_id: str, creds, name: str = ""):
    if hasattr(creds, "to_json"):
        js = creds.to_json()
    elif isinstance(creds, str):
        js = creds
    else:
        js = json.dumps(creds)
    c = _con()
    c.execute("INSERT INTO channel_auth(channel_id, name, token_json, updated_at) "
              "VALUES (?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET "
              "token_json=excluded.token_json, updated_at=excluded.updated_at, "
              "name=CASE WHEN excluded.name!='' THEN excluded.name ELSE channel_auth.name END",
              (channel_id, name, js,
               datetime.now(timezone.utc).isoformat(timespec="seconds")))
    c.commit()
    c.close()


def load(channel_id: str) -> dict | None:
    row = _con().execute("SELECT token_json FROM channel_auth WHERE channel_id=?",
                         (channel_id,)).fetchone()
    return json.loads(row[0]) if row else None


def load_all() -> dict[str, dict]:
    return {r[0]: json.loads(r[1]) for r in
            _con().execute("SELECT channel_id, token_json FROM channel_auth ORDER BY channel_id")}


def names() -> dict[str, str]:
    return {r[0]: (r[1] or "") for r in
            _con().execute("SELECT channel_id, name FROM channel_auth")}


def set_name(channel_id: str, name: str):
    c = _con()
    c.execute("UPDATE channel_auth SET name=? WHERE channel_id=?", (name, channel_id))
    c.commit()
    c.close()


def delete(channel_id: str) -> bool:
    c = _con()
    cur = c.execute("DELETE FROM channel_auth WHERE channel_id=?", (channel_id,))
    c.commit()
    gone = cur.rowcount > 0
    c.close()
    return gone


def migrate_from_files():
    """One-time: import tokens/*.json + avatars/*.json names, then remove files."""
    imported = 0
    for tp in sorted((BASE / "tokens").glob("*.json")):
        try:
            info = json.loads(tp.read_text())
            cid = tp.stem
            name = ""
            av = BASE / "avatars" / f"{cid}.json"
            if av.exists():
                name = json.loads(av.read_text()).get("title", "")
                av.unlink()
            save(cid, info, name=name)
            tp.unlink()
            imported += 1
        except Exception:
            pass
    d = BASE / "tokens"
    if d.exists() and not any(d.glob("*")):
        d.rmdir()
    return imported


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["migrate"]:
        n = migrate_from_files()
        print(f"migrated {n} channel(s) into {DB.name}; tokens/ removed")
        for cid, info in load_all().items():
            print(" ", cid, [s.split("/")[-1] for s in info.get("scopes", [])])
