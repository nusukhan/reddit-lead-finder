# foxlead/config.py
# Saari settings ek jagah: .env se keys, database ka rasta, model ka naam.

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# .env file se keys padho (laptop pe). Server pe keys seedhi environment se aati hain.
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# database file (FOXLEAD_DB se badal sakte ho - jaise demo/test ke liye alag file)
DB_PATH = os.getenv("FOXLEAD_DB", str(BASE_DIR / "instance" / "foxlead.sqlite3"))

# login session + email links (verify / reset) ko sign karne wali secret key.
# .env mein FLASK_SECRET_KEY ho to wo; warna instance/secret_key file mein ek baar
# bana kar save kar lo (taake restart par sab log out na hon aur links chalte rahein).
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "")
if not SECRET_KEY:
    _key_file = Path(DB_PATH).parent / "secret_key"
    if _key_file.exists():
        SECRET_KEY = _key_file.read_text().strip()
    else:
        import secrets as _secrets
        _key_file.parent.mkdir(parents=True, exist_ok=True)
        SECRET_KEY = _secrets.token_hex(32)
        _key_file.write_text(SECRET_KEY)

# Google login (optional) - Google Cloud Console se milte hain
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

# Claude (scoring + comment check)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME = "claude-haiku-5-5"

# Emails mein dashboard ka link (online jaane par apni website ka address daalna)
APP_URL = os.getenv("APP_URL", "http://127.0.0.1:5000").rstrip("/")

# Telegram alerts (optional): @BotFather se bot banao, token + bot ka username yahan
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_NAME = os.getenv("TELEGRAM_BOT_NAME", "").lstrip("@")

# Email bhejne wala Gmail account
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# Admin panel kaun dekh sakta hai: .env mein ADMIN_EMAILS=aap@gmail.com,doosra@gmail.com
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()}

# Plans - har plan ki hadein (qeemat Stripe mein set hoti hai, yahan sirf dikhane ke liye)
PLANS = {
    "free": {"name": "Free", "price": 0, "scan_every_hours": 24, "drafts_per_day": 10, "chat_per_day": 10,
             "telegram": False, "weekly_report": False, "team": False},
    "pro":  {"name": "Pro", "price": 9, "scan_every_hours": 1, "drafts_per_day": 30, "chat_per_day": 50,
             "telegram": True, "weekly_report": True, "team": True},
}

# Stripe (payment) - Stripe dashboard se: secret key, Pro plan ka price ID, webhook secret
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# robot ki hadein (kharcha aur waqt control mein rahe)
MAX_SCORE_PER_USER = 40     # ek run mein ek user ke liye zyada se zyada itni posts Claude ko
AGE_DAYS_CHOICES = (3, 7)   # user chunta hai: pichhle kitne din ki posts check hon (nayi hamesha upar)
AGE_DAYS_DEFAULT = 3
FETCH_MAX_AGE_HOURS = max(AGE_DAYS_CHOICES) * 24   # robot itni purani tak laata hai, phir har user apni hadd lagata hai

# profile/field badalne par foran scan (tests mein FOXLEAD_AUTO_SCAN=0 - asli internet/Claude na chale)
AUTO_SCAN_ON_PROFILE = os.getenv("FOXLEAD_AUTO_SCAN", "1") == "1"
