# foxlead/notify.py
# Telegram alerts. Jodne ka tareeqa:
#   1) profile par "Connect Telegram" -> link t.me/<bot>?start=<ek-baar-ka-code>
#   2) user Telegram mein Start dabata hai -> bot ko "/start <code>" milta hai
#   3) sync_updates() wo code dhoond kar user ko us chat se jod deta hai
# Phir robot naye leads (ya sirf HOT leads) Telegram par bhejta hai.

import secrets

import requests

from . import config, db
from .professions import FEEDS


class TelegramError(Exception):
    pass


def configured():
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_BOT_NAME)


def call(method, **params):
    try:
        r = requests.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}", json=params, timeout=20)
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        raise TelegramError(f"Telegram unreachable: {e.__class__.__name__}") from e
    if not data.get("ok"):
        raise TelegramError(data.get("description", "Telegram error"))
    return data["result"]


def send(chat_id, text):
    call("sendMessage", chat_id=chat_id, text=text[:4000], disable_web_page_preview=True)


def connect_link(user_id):
    """Is user ke liye Telegram link (code na ho to naya banao)."""
    with db.connect() as conn:
        code = conn.execute("SELECT telegram_code FROM users WHERE id = ?", (user_id,)).fetchone()[0]
        if not code:
            code = secrets.token_urlsafe(16)
            conn.execute("UPDATE users SET telegram_code = ? WHERE id = ?", (code, user_id))
    return f"https://t.me/{config.TELEGRAM_BOT_NAME}?start={code}"


def sync_updates():
    """Bot ke naye messages padho; '/start <code>' wale users ko unke chat se jodo. Return: kitne jude."""
    with db.connect() as conn:
        offset = int(db.get_meta(conn, "telegram_offset", 0))
    updates = call("getUpdates", offset=offset, timeout=0, allowed_updates=["message"])
    linked = 0
    for u in updates:
        offset = max(offset, u["update_id"] + 1)
        msg = u.get("message") or {}
        text, chat = (msg.get("text") or "").strip(), (msg.get("chat") or {}).get("id")
        if not chat or not text.startswith("/start "):
            continue
        code = text.split(" ", 1)[1].strip()
        with db.connect() as conn:
            user = conn.execute("SELECT id, name FROM users WHERE telegram_code = ?", (code,)).fetchone()
            if user:   # code ek hi baar chalta hai
                conn.execute("UPDATE users SET telegram_chat_id = ?, telegram_code = NULL WHERE id = ?", (str(chat), user["id"]))
        if user:
            linked += 1
            send(chat, f"✅ Connected to Foxlead, {user['name'] or 'there'}! New leads will arrive here. "
                       f"Change what you get on your profile: {config.APP_URL}/profile")
    with db.connect() as conn:
        db.set_meta(conn, "telegram_offset", offset)
    return linked


def lead_alert(chat_id, mode, leads):
    """Naye leads Telegram par. mode: all = sab, hot = sirf HOT, off = kuch nahi."""
    if mode == "off" or not chat_id:
        return 0
    picked = [l for l in leads if mode == "all" or l.get("hot")]
    if not picked:
        return 0
    picked.sort(key=lambda l: (-int(bool(l.get("hot"))), -l["score"]))
    lines = []
    for l in picked[:8]:
        src = l["source"] if l["source"].startswith("r/") else FEEDS.get(l["source"], {}).get("label", l["source"])
        lines.append(f"{'🔥 HOT · ' if l.get('hot') else ''}[{l['score']}/10] {l['verdict']} · {src}\n{l['title'][:140]}\n{l['link']}")
    head = f"🦊 {len(picked)} new lead{'s' if len(picked) != 1 else ''} for you" if mode == "all" else \
           f"🔥 {len(picked)} hot lead{'s' if len(picked) != 1 else ''} — reply first!"
    more = f"\n\n…and {len(picked) - 8} more on your dashboard: {config.APP_URL}/dashboard" if len(picked) > 8 else ""
    send(chat_id, head + "\n\n" + "\n\n".join(lines) + more)
    return len(picked)
