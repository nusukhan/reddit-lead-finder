# foxlead/db.py
# SQLite database: users, unki profiles, posts, har user ke scores/leads, aur runs.
# sqlite3 Python mein pehle se hota hai - kuch install nahi karna.

import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL DEFAULT '',
    password_hash TEXT,                -- Google wale users ka NULL ho sakta hai
    google_sub    TEXT UNIQUE,         -- Google account ki pakki ID
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    profession    TEXT NOT NULL,       -- template id: laravel, design, devops...
    title         TEXT NOT NULL,       -- "UI/UX designer"
    skills        TEXT NOT NULL,
    ideal_client  TEXT NOT NULL,
    country       TEXT NOT NULL DEFAULT '',
    remote_only   INTEGER NOT NULL DEFAULT 1,
    subreddits    TEXT NOT NULL DEFAULT '[]',   -- JSON list
    keywords      TEXT NOT NULL DEFAULT '[]',   -- JSON list
    feeds         TEXT NOT NULL DEFAULT '[]',   -- JSON list of feed keys
    threshold     INTEGER NOT NULL DEFAULT 7,
    email_enabled INTEGER NOT NULL DEFAULT 1,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    link       TEXT NOT NULL UNIQUE,
    source     TEXT NOT NULL,          -- "r/forhire" ya feed key jaise "larajobs"
    title      TEXT NOT NULL,
    text       TEXT NOT NULL DEFAULT '',
    is_job     INTEGER NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_posts (
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id       INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    score         INTEGER NOT NULL,
    reason        TEXT NOT NULL DEFAULT '',
    is_lead       INTEGER NOT NULL DEFAULT 0,
    verdict       TEXT NOT NULL DEFAULT '',     -- Apply / Reply / Maybe / Skip / Review
    competition   TEXT NOT NULL DEFAULT '',
    comment_count INTEGER NOT NULL DEFAULT 0,
    note          TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'new',  -- new / replied / applied / won / skipped
    status_at     TEXT,
    scored_at     TEXT NOT NULL,
    emailed_at    TEXT,
    PRIMARY KEY (user_id, post_id)
);
CREATE INDEX IF NOT EXISTS idx_user_posts_lead ON user_posts(user_id, is_lead);

CREATE TABLE IF NOT EXISTS runs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    time    TEXT NOT NULL,
    fetched INTEGER NOT NULL DEFAULT 0,
    new     INTEGER NOT NULL DEFAULT 0,
    scored  INTEGER NOT NULL DEFAULT 0,
    leads   INTEGER NOT NULL DEFAULT 0,
    status  TEXT NOT NULL
);

-- har Claude call ka hisaab (admin panel mein kharcha dikhane ke liye)
CREATE TABLE IF NOT EXISTS usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,       -- score / comments / draft
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_user ON usage(user_id, kind, at);

-- chatbot ki baatcheet (har user ki apni)
CREATE TABLE IF NOT EXISTS chat_messages (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role    TEXT NOT NULL,              -- user / assistant
    content TEXT NOT NULL,
    at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);

-- agency team: owner ki profile + leads sab members share karte hain
CREATE TABLE IF NOT EXISTS teams (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    owner_id   INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS team_invites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id     INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    email       TEXT NOT NULL COLLATE NOCASE,
    token       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    accepted_at TEXT
);

-- email ke 6 digit codes (account verify / password reset) - code hash mein, seedha nahi
CREATE TABLE IF NOT EXISTS email_codes (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose    TEXT NOT NULL,          -- verify / reset
    code_hash  TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts   INTEGER NOT NULL DEFAULT 0,
    sent_at    TEXT NOT NULL,
    PRIMARY KEY (user_id, purpose)
);

-- chhoti settings/yaaddasht (jaise: Remote OK aakhri baar kab fetch hua)
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Naye columns - purane database mein na hon to init_db() khud jod deta hai
NEW_COLUMNS = {
    "users": {
        "disabled": "INTEGER NOT NULL DEFAULT 0",       # admin ne account band kiya
        "last_login_at": "TEXT",
        "email_verified": "INTEGER NOT NULL DEFAULT 0", # email ki tasdeeq (Google wale khud verified)
        "verify_sent_at": "TEXT",
        "telegram_chat_id": "TEXT",                     # Telegram se juda hua chat
        "telegram_code": "TEXT",                        # jodne ka ek-baar wala code
        "weekly_sent_at": "TEXT",                       # aakhri weekly report kab gayi
        "plan": "TEXT NOT NULL DEFAULT 'free'",         # free / pro
        "plan_source": "TEXT NOT NULL DEFAULT ''",      # stripe / admin (admin ne muft diya)
        "stripe_customer_id": "TEXT",
        "stripe_subscription_id": "TEXT",
        "team_id": "INTEGER",                           # agency team (owner ki team)
        "lang": "TEXT NOT NULL DEFAULT 'en'",           # en / ur
        "timezone": "TEXT NOT NULL DEFAULT ''",         # browser ka time zone (jaise Asia/Karachi) - auto-scan "kis baje" ke liye
    },
    "profiles": {
        "portfolio": "TEXT NOT NULL DEFAULT ''",        # AI draft mein link ke liye
        "blocklist": "TEXT NOT NULL DEFAULT '[]'",      # ye words wale posts kabhi mat dikhao
        "weekly_report": "INTEGER NOT NULL DEFAULT 1",  # har Monday summary email
        "telegram_alerts": "TEXT NOT NULL DEFAULT 'all'",  # all / hot / off
        "max_age_days": "INTEGER NOT NULL DEFAULT 7",   # pichhle kitne din ki posts (3 ya 7)
        "scan_every": "INTEGER",                        # auto-scan har kitne ghante (0 = band, NULL = plan ka default)
        "scan_hour": "INTEGER",                         # 24 ghante wale scan ka waqt (0-23, user ke time zone mein; NULL = koi bhi)
        "email_every_scan": "INTEGER NOT NULL DEFAULT 0",  # 1 = koi lead na mile to bhi har scan ke baad email
    },
    "user_posts": {
        "draft": "TEXT NOT NULL DEFAULT ''",            # AI reply / cover letter draft
        "draft_at": "TEXT",
        "user_note": "TEXT NOT NULL DEFAULT ''",        # user ka apna note
        "remind_at": "TEXT",                            # follow-up kab yaad dilana hai
        "reminded_at": "TEXT",                          # reminder email kab gaya
        "feedback": "TEXT NOT NULL DEFAULT ''",         # 'not_relevant' = user ne reject kiya
        "hot": "INTEGER NOT NULL DEFAULT 0",            # bilkul nayi post, abhi koi reply nahi
        "deal_value": "REAL",                           # deal kitne $ ki (pipeline / kamai)
        "assigned_to": "INTEGER",                       # team mein kis member ke zimme hai
    },
    "posts": {
        "posted_at": "TEXT",                            # post asal mein kab likhi gayi
    },
}

PROFILE_LISTS = ("subreddits", "keywords", "feeds", "blocklist")

# Claude Haiku 5.5 ki qeemat ($ per 1M tokens) - admin panel ke andaaze ke liye
PRICE_IN, PRICE_OUT = 0.10, 0.50


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def connect():
    """Database se judo:  with db.connect() as conn: ...
    Block khatam = changes save (commit) + connection band. Error aaye to kuch save nahi hota.
    (sqlite3 ka apna 'with' connection band NAHI karta - is liye ye wrapper.)"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row          # row["email"] jaise padh sako
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # web app + robot ek saath padh/likh sakein
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, cols in NEW_COLUMNS.items():
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            for name, decl in cols.items():
                if name not in have:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def record_usage(conn, user_id, kind, usage):
    """Claude ke jawab ka token hisaab save karo (usage = response.usage)."""
    conn.execute("INSERT INTO usage (user_id, kind, input_tokens, output_tokens, at) VALUES (?, ?, ?, ?, ?)",
                 (user_id, kind, getattr(usage, "input_tokens", 0) or 0,
                  getattr(usage, "output_tokens", 0) or 0, now_utc()))


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, str(value)))


def cost_usd(input_tokens, output_tokens):
    return (input_tokens or 0) / 1e6 * PRICE_IN + (output_tokens or 0) / 1e6 * PRICE_OUT


def get_profile(conn, user_id):
    """Profile dict (lists JSON se nikaal ke) ya None."""
    row = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    profile = dict(row)
    for key in PROFILE_LISTS:
        profile[key] = json.loads(profile[key] or "[]")
    return profile


def save_profile(conn, user_id, p):
    conn.execute("""
        INSERT INTO profiles (user_id, profession, title, skills, ideal_client, country, remote_only,
                              subreddits, keywords, feeds, threshold, email_enabled, portfolio, blocklist,
                              weekly_report, telegram_alerts, max_age_days, scan_every, scan_hour,
                              email_every_scan, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            profession=excluded.profession, title=excluded.title, skills=excluded.skills,
            ideal_client=excluded.ideal_client, country=excluded.country, remote_only=excluded.remote_only,
            subreddits=excluded.subreddits, keywords=excluded.keywords, feeds=excluded.feeds,
            threshold=excluded.threshold, email_enabled=excluded.email_enabled,
            portfolio=excluded.portfolio, blocklist=excluded.blocklist, weekly_report=excluded.weekly_report,
            telegram_alerts=excluded.telegram_alerts, max_age_days=excluded.max_age_days,
            scan_every=excluded.scan_every, scan_hour=excluded.scan_hour,
            email_every_scan=excluded.email_every_scan, updated_at=excluded.updated_at
    """, (user_id, p["profession"], p["title"], p["skills"], p["ideal_client"], p["country"],
          int(p["remote_only"]), json.dumps(p["subreddits"]), json.dumps(p["keywords"]),
          json.dumps(p["feeds"]), int(p["threshold"]), int(p["email_enabled"]),
          p.get("portfolio", ""), json.dumps(p.get("blocklist", [])), int(p.get("weekly_report", True)),
          p.get("telegram_alerts", "all"), int(p.get("max_age_days", 7)), p.get("scan_every"), p.get("scan_hour"),
          int(p.get("email_every_scan", False)), now_utc()))


def blocked(text, blocklist):
    """Kya text mein block list ka koi word/company hai? (chhote-bade letter ka farq nahi)"""
    low = (text or "").lower()
    return any(w.lower() in low for w in blocklist if w)
