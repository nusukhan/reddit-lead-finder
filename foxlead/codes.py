# foxlead/codes.py
# Email ke 6 digit codes: account banane par (verify) aur password bhoolne par (reset).
# Code database mein seedha nahi - SECRET_KEY ke saath hash. Har user + kaam ka ek hi zinda code.
#   verify: 30 minute, reset: 15 minute · 5 galat koshishen = code khatam · naya code 1 minute baad

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from . import config, db

TTL_MINUTES = {"verify": 30, "reset": 15}
MAX_TRIES = 5
RESEND_SECONDS = 60


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(user_id, purpose, code):
    return hmac.new(config.SECRET_KEY.encode(), f"{user_id}:{purpose}:{code}".encode(), hashlib.sha256).hexdigest()


def wait_seconds(user_id, purpose):
    """Naya code bhejne se pehle kitne second aur rukna hai (0 = abhi bhej sakte ho)."""
    with db.connect() as conn:
        row = conn.execute("SELECT sent_at FROM email_codes WHERE user_id = ? AND purpose = ?", (user_id, purpose)).fetchone()
    if not row:
        return 0
    sent = datetime.fromisoformat(row["sent_at"].replace("Z", "+00:00"))
    return max(0, RESEND_SECONDS - int((_now() - sent).total_seconds()))


def new_code(user_id, purpose):
    """Naya 6 digit code banao (purana khatam) aur wapas do - email mein bhejne ke liye."""
    code = f"{secrets.randbelow(10 ** 6):06d}"
    now = _now()
    with db.connect() as conn:
        conn.execute("""INSERT INTO email_codes (user_id, purpose, code_hash, expires_at, attempts, sent_at)
                        VALUES (?, ?, ?, ?, 0, ?)
                        ON CONFLICT(user_id, purpose) DO UPDATE SET code_hash = excluded.code_hash,
                            expires_at = excluded.expires_at, attempts = 0, sent_at = excluded.sent_at""",
                     (user_id, purpose, _hash(user_id, purpose, code),
                      _iso(now + timedelta(minutes=TTL_MINUTES[purpose])), _iso(now)))
    return code


def check(user_id, purpose, code):
    """'ok' (code istemal ho gaya), 'wrong', 'expired' ya 'locked' (5 galat koshishen)."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM email_codes WHERE user_id = ? AND purpose = ?", (user_id, purpose)).fetchone()
        if not row or row["expires_at"] < _iso(_now()):
            return "expired"
        if row["attempts"] >= MAX_TRIES:
            return "locked"
        if len(code) == 6 and hmac.compare_digest(row["code_hash"], _hash(user_id, purpose, code)):
            conn.execute("DELETE FROM email_codes WHERE user_id = ? AND purpose = ?", (user_id, purpose))
            return "ok"
        conn.execute("UPDATE email_codes SET attempts = attempts + 1 WHERE user_id = ? AND purpose = ?", (user_id, purpose))
        return "locked" if row["attempts"] + 1 >= MAX_TRIES else "wrong"


def tries_left(user_id, purpose):
    with db.connect() as conn:
        row = conn.execute("SELECT attempts FROM email_codes WHERE user_id = ? AND purpose = ?", (user_id, purpose)).fetchone()
    return MAX_TRIES - row["attempts"] if row else 0
