# foxlead/web.py
# Website: signup / login (email+password aur Google), profile (field chuno),
# aur har user ka apna dashboard. Chalane ke liye:  python -m foxlead.web
#
# Security ki baatein:
#   - password kabhi seedha save nahi hota, sirf uska hash (werkzeug - scrypt)
#   - har POST par CSRF token check hota hai (koi doosri site form na bhej sake)
#   - har API sirf LOGGED-IN user ka apna data deti hai (user_id session se)

import re
import json
import time
import secrets
import threading
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, make_response, redirect, render_template,
                   request, session, url_for)
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from . import chat, config, db, drafts, i18n, llm, mailer, notify, plans
from .i18n import t
from .professions import BY_ID, FEEDS, PROFESSIONS

app = Flask(__name__)

app.config.update(
    SECRET_KEY=config.SECRET_KEY,           # config khud bana kar instance/secret_key mein rakhta hai
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)

db.init_db()

# -------- Google login (sirf tab jab .env mein Google ki keys hon) --------
oauth = None
if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
    from authlib.integrations.flask_client import OAuth
    oauth = OAuth(app)
    oauth.register(
        name="google",
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# quotes / < > wali "emails" mana - ye kahin HTML/JS mein jaa kar gadbad na karein
EMAIL_RE = re.compile(r"^[^@\s<>\"'`]+@[^@\s<>\"'`]+\.[^@\s<>\"'`]+$")
# lead ke stages: new -> replied/applied -> talking -> won / lost  (skipped = chhod diya)
STATUSES = {"new", "replied", "applied", "talking", "won", "lost", "skipped"}
# profile ki wo cheezen jin ke badalne se leads badalte hain (inme badlaav = dobara scan)
SEARCH_KEYS = ("profession", "title", "skills", "ideal_client", "country", "remote_only",
               "subreddits", "keywords", "feeds", "threshold", "blocklist")


# ================= helpers =================

def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    """Har POST mein form ka csrf_token (ya X-CSRF-Token header) session wale se milna chahiye."""
    if request.method == "POST":
        if request.path == "/stripe/webhook":
            return          # Stripe ka apna signature check hota hai (neeche) - browser form nahi
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("csrf") or ""
        # khaali token kabhi qubool nahi (warna "" == "" se check pass ho jaata)
        if not expected or not sent or not secrets.compare_digest(sent, expected):
            abort(400, "CSRF token galat hai - page refresh karke dobara try karo.")


@app.before_request
def set_lang():
    """Zubaan: jo user ne AAKHRI BAAR khud chuni (cookie) - wahi chalegi, aur account mein bhi save.
    Cookie na ho (naya device) to account wali. Dono na hon to English.
    (Pehle account ki purani 'en' cookie ko dabaa deti thi - signup se pehle Urdu chuno to bhi English aata tha.)"""
    code = request.cookies.get("lang", "")
    code = code if code in i18n.LANGS else ""
    uid = session.get("uid")
    if uid:
        with db.connect() as conn:
            row = conn.execute("SELECT lang FROM users WHERE id = ?", (uid,)).fetchone()
            if row and code and row["lang"] != code:
                conn.execute("UPDATE users SET lang = ? WHERE id = ?", (code, uid))
        if row and not code:
            code = row["lang"]
    g.lang = code if code in i18n.LANGS else "en"


@app.context_processor
def inject_lang():
    return {"_": t, "lang": g.get("lang", "en"), "text_dir": "rtl" if g.get("lang") == "ur" else "ltr",
            "LANGS": i18n.LANGS, "js_strings": i18n.js_strings()}


@app.route("/lang/<code>")
def set_language(code):
    """Zubaan badlo (user ki pasand save + cookie), phir wapas usi page par."""
    if code not in i18n.LANGS:
        abort(404)
    uid = session.get("uid")
    if uid:
        with db.connect() as conn:
            conn.execute("UPDATE users SET lang = ? WHERE id = ?", (code, uid))
    nxt = request.args.get("next")
    resp = make_response(redirect(safe_next(nxt) if nxt else url_for("home")))
    resp.set_cookie("lang", code, max_age=365 * 86400, samesite="Lax", httponly=True)
    return resp


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if user is None or user["disabled"]:
        session.clear()             # account band ho gaya - foran log out
        return None
    return user


def is_admin(user):
    return bool(user) and user["email"].lower() in config.ADMIN_EMAILS


def workspace_id(user):
    """Kis ke leads/profile par kaam ho raha hai: team member -> owner ke, warna apne."""
    if user["team_id"]:
        with db.connect() as conn:
            row = conn.execute("SELECT owner_id FROM teams WHERE id = ?", (user["team_id"],)).fetchone()
        if row:
            return row["owner_id"]
    return user["id"]


def is_member(user):
    """Team mein hai lekin owner nahi (profile owner sambhalta hai)."""
    return workspace_id(user) != user["id"]


app.jinja_env.globals.update(is_admin=is_admin, plan_of=plans.plan_of, is_member=is_member, PLANS=config.PLANS)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("login", next=request.path))
        if not is_admin(user):
            abort(404)              # admin page ka hona bhi na pata chale
        return view(user, *args, **kwargs)
    return wrapped


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="login required"), 401
            return redirect(url_for("login", next=request.path))
        return view(user, *args, **kwargs)
    return wrapped


def start_session(user_id):
    session.clear()                 # purana session khatam (session fixation se bachao)
    session["uid"] = user_id
    session.permanent = True
    with db.connect() as conn:
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (db.now_utc(), user_id))

DISABLED_MSG = "This account has been disabled. Please contact the Foxlead team."


# -------- email links: verify (3 din) aur password reset (1 ghanta) --------
_signer = URLSafeTimedSerializer(config.SECRET_KEY)
VERIFY_MAX_AGE, RESET_MAX_AGE = 3 * 86400, 3600


def make_token(kind, user):
    data = {"uid": user["id"], "em": user["email"]}
    if kind == "reset":
        # password badalte hi purana reset link bekaar ho jaye
        data["ph"] = (user["password_hash"] or "none")[-16:]
    return _signer.dumps(data, salt=kind)


def read_token(kind, token, max_age):
    """Sahi aur waqt ke andar link ho to user row, warna None."""
    try:
        data = _signer.loads(token, salt=kind, max_age=max_age)
    except BadSignature:                    # galat ya expire (SignatureExpired bhi isi mein)
        return None
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (data.get("uid"),)).fetchone()
    if user is None or user["email"].lower() != str(data.get("em", "")).lower() or user["disabled"]:
        return None
    if kind == "reset" and (user["password_hash"] or "none")[-16:] != data.get("ph"):
        return None
    return user


def send_verification(user):
    """Verify link email karo. Email set na ho to chupchaap chhod do (False)."""
    if not mailer.configured():
        return False
    url = url_for("verify_email", token=make_token("verify", user), _external=True)
    try:
        mailer.send_verify(user["email"], user["name"], url)
    except mailer.MailError:
        return False
    with db.connect() as conn:
        conn.execute("UPDATE users SET verify_sent_at = ? WHERE id = ?", (db.now_utc(), user["id"]))
    return True


def safe_next(target):
    """Login ke baad sirf apni hi site ke page par wapas bhejo (bahar ki site par nahi)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard")


# login par baar baar galat password -> thodi der rok do (laptop/single server ke liye kaafi)
_failed = {}
FAIL_LIMIT, FAIL_WINDOW = 5, 15 * 60


def too_many_failures(key):
    recent = [t for t in _failed.get(key, []) if time.time() - t < FAIL_WINDOW]
    _failed[key] = recent
    return len(recent) >= FAIL_LIMIT


def record_failure(key):
    _failed.setdefault(key, []).append(time.time())


def split_list(text, limit=30):
    """'a, b\nc' -> ['a','b','c'] (khaali aur duplicate hata kar)."""
    items, seen = [], set()
    for part in re.split(r"[,\n]", text or ""):
        part = part.strip()
        if part and part.lower() not in seen:
            seen.add(part.lower())
            items.append(part)
    return items[:limit]


# ================= pages =================

# -------- phone app (PWA) --------
@app.route("/sw.js")
def service_worker():
    # root se serve - taake poori site (scope "/") is ke under aaye
    resp = app.send_static_file("sw.js")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Content-Type"] = "application/javascript"
    return resp


@app.route("/manifest.webmanifest")
def manifest():
    resp = app.send_static_file("manifest.webmanifest")
    resp.headers["Content-Type"] = "application/manifest+json"
    return resp


@app.route("/offline")
def offline():
    return render_template("offline.html")


@app.route("/")
def home():
    return redirect(url_for("dashboard") if current_user() else url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user():
        return redirect(url_for("dashboard"))
    form = {"name": "", "email": ""}
    if request.method == "POST":
        form["name"] = request.form.get("name", "").strip()[:80]
        form["email"] = request.form.get("email", "").strip().lower()[:200]
        password = request.form.get("password", "")
        if not form["name"]:
            flash(t("Please enter your name."))
        elif not EMAIL_RE.match(form["email"]):
            flash(t("Please enter a valid email address."))
        elif len(password) < 8:
            flash(t("Password must be at least 8 characters."))
        else:
            new_id = None
            with db.connect() as conn:
                if conn.execute("SELECT 1 FROM users WHERE email = ?", (form["email"],)).fetchone():
                    flash(t("An account with this email already exists — log in instead."))
                else:
                    new_id = conn.execute(
                        "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
                        (form["email"], form["name"], generate_password_hash(password), db.now_utc())).lastrowid
            # session sirf tab jab user pakka save ho chuka ho (connection band hone ke BAAD -
            # warna start_session ka apna connection isi lock par atak jata tha)
            if new_id:
                start_session(new_id)
                with db.connect() as conn:
                    new_user = conn.execute("SELECT * FROM users WHERE id = ?", (new_id,)).fetchone()
                send_verification(new_user)     # email set na ho to bhi signup chalta rahe
                flash(t("Account created! Now choose your field so Foxlead knows what to look for."), "success")
                return redirect(url_for("profile"))
    return render_template("signup.html", form=form, google=oauth is not None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        key = email or request.remote_addr
        if too_many_failures(key):
            flash(t("Too many wrong attempts. Please wait 15 minutes and try again."))
        else:
            with db.connect() as conn:
                user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and user["password_hash"] and check_password_hash(user["password_hash"], password):
                if user["disabled"]:
                    flash(t(DISABLED_MSG))
                    return render_template("login.html", email=email, google=oauth is not None)
                start_session(user["id"])
                flash(t("Welcome back, {name}! You're logged in.", name=user["name"] or user["email"]), "success")
                return redirect(safe_next(request.args.get("next")))
            record_failure(key)
            if user and not user["password_hash"]:
                flash(t("This account uses Google login — use “Continue with Google”."))
            else:
                flash(t("Wrong email or password."))
    return render_template("login.html", email=email, google=oauth is not None)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash(t("You're logged out. See you soon!"), "success")
    return redirect(url_for("login"))


@app.route("/verify/<token>")
def verify_email(token):
    user = read_token("verify", token, VERIFY_MAX_AGE)
    if user is None:
        flash(t("That verification link is invalid or has expired — log in and send a new one."))
        return redirect(url_for("login"))
    with db.connect() as conn:
        conn.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user["id"],))
    flash(t("Your email is verified. Lead alerts will now reach your inbox."), "success")
    return redirect(url_for("dashboard") if current_user() else url_for("login"))


@app.route("/verify/resend", methods=["POST"])
@login_required
def verify_resend(user):
    if user["email_verified"]:
        return jsonify(ok=True, verified=True)
    if user["verify_sent_at"] and user["verify_sent_at"] > iso_ago(minutes=2):
        return jsonify(error=t("We just sent one — please wait a couple of minutes.")), 429
    if not send_verification(user):
        return jsonify(error=t("Couldn't send the email right now. Please try again later.")), 502
    return jsonify(ok=True)


_reset_sent = {}


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        # hamesha ek hi jawab - taake koi ye na jaan sake ke kaunsi email registered hai
        flash(t("If an account exists for that email, we've sent a link to reset the password. It works for 1 hour."), "success")
        recent = time.time() - _reset_sent.get(email, 0) < 120
        with db.connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and not user["disabled"] and not recent and mailer.configured():
            _reset_sent[email] = time.time()
            url = url_for("reset_password", token=make_token("reset", user), _external=True)
            try:
                mailer.send_reset(user["email"], user["name"], url)
            except mailer.MailError as e:
                app.logger.warning("reset email to user %s failed: %s", user["id"], e)   # user ko nahi batate, log mein likho
        return redirect(url_for("forgot"))
    return render_template("forgot.html")


@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = read_token("reset", token, RESET_MAX_AGE)
    if user is None:
        flash(t("That reset link is invalid or has expired. Please ask for a new one."))
        return redirect(url_for("forgot"))
    if request.method == "POST":
        pw, pw2 = request.form.get("password", ""), request.form.get("password2", "")
        if len(pw) < 8:
            flash(t("Password must be at least 8 characters."))
        elif pw != pw2:
            flash(t("The two passwords don't match."))
        else:
            with db.connect() as conn:   # link email se khula - matlab email bhi verified
                conn.execute("UPDATE users SET password_hash = ?, email_verified = 1 WHERE id = ?",
                             (generate_password_hash(pw), user["id"]))
            _failed.pop(user["email"].lower(), None)
            start_session(user["id"])
            flash(t("Password changed — you're logged in."), "success")
            return redirect(url_for("dashboard"))
    return render_template("reset.html", token=token)


@app.route("/login/google")
def login_google():
    if oauth is None:
        flash("Google login is not set up yet.")
        return redirect(url_for("login"))
    return oauth.google.authorize_redirect(url_for("google_callback", _external=True))


@app.route("/auth/google/callback")
def google_callback():
    if oauth is None:
        abort(404)
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash("Google login failed — please try again.")
        return redirect(url_for("login"))
    info = token.get("userinfo") or {}
    sub, email = info.get("sub"), (info.get("email") or "").lower()
    if not sub or not email or not info.get("email_verified"):
        flash("Google did not share a verified email address.")
        return redirect(url_for("login"))
    with db.connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()
        if user is None:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user is not None:   # pehle email se bana tha - ab Google bhi jod do (Google ne email verify kar di)
                conn.execute("UPDATE users SET google_sub = ?, email_verified = 1 WHERE id = ?", (sub, user["id"]))
            else:
                cur = conn.execute(
                    "INSERT INTO users (email, name, google_sub, email_verified, created_at) VALUES (?, ?, ?, 1, ?)",
                    (email, (info.get("name") or email.split("@")[0])[:80], sub, db.now_utc()))
                user = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        has_profile = db.get_profile(conn, user["id"]) is not None
    if user["disabled"]:
        flash(t(DISABLED_MSG))
        return redirect(url_for("login"))
    start_session(user["id"])
    return redirect(url_for("dashboard") if has_profile else url_for("profile"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile(user):
    if is_member(user):
        flash(t("Your team's profile is managed by the team owner."), "info")
        return redirect(url_for("team"))
    with db.connect() as conn:
        existing = db.get_profile(conn, user["id"])
    if request.method == "POST":
        f = request.form
        prof_id = f.get("profession", "custom")
        if prof_id not in BY_ID:
            prof_id = "custom"
        p = {
            "profession": prof_id,
            "title": f.get("title", "").strip()[:80] or BY_ID[prof_id]["label"],
            "skills": f.get("skills", "").strip()[:300],
            "ideal_client": f.get("ideal_client", "").strip()[:500],
            "country": f.get("country", "").strip()[:60],
            "remote_only": f.get("remote_only") == "1",
            "subreddits": [s.removeprefix("r/") for s in split_list(f.get("subreddits"), 15)
                           if re.fullmatch(r"(r/)?[A-Za-z0-9_]{2,21}", s)],
            "keywords": [k.lower() for k in split_list(f.get("keywords"), 30)],
            "feeds": [k for k in f.getlist("feeds") if k in FEEDS],
            "threshold": min(9, max(5, int(f.get("threshold", 7) or 7))),
            "email_enabled": f.get("email_enabled") == "1",
            "portfolio": f.get("portfolio", "").strip()[:200],
            "blocklist": split_list(f.get("blocklist"), 50),
            "weekly_report": f.get("weekly_report") == "1",
            "telegram_alerts": f.get("telegram_alerts") if f.get("telegram_alerts") in ("all", "hot", "off") else "all",
            "max_age_days": int(f.get("max_age_days")) if f.get("max_age_days", "").isdigit()
                            and int(f.get("max_age_days")) in config.AGE_DAYS_CHOICES else config.AGE_DAYS_DEFAULT,
        }
        if p["portfolio"] and not re.match(r"^https?://\S+$", p["portfolio"]):
            flash(t("Portfolio link should start with https:// — or leave it empty."))
        elif not p["skills"]:
            flash(t("Please list at least one skill — the AI scores posts against it."))
        elif not p["subreddits"] and not p["feeds"]:
            flash(t("Pick at least one place to search: a subreddit or a job board."))
        else:
            changed = existing is None or any(existing.get(k) != p[k] for k in SEARCH_KEYS)
            # sirf din (3/7) badle: purane faisle sahi hain, bas naye din wali posts ke liye scan
            window_changed = existing is not None and existing.get("max_age_days") != p["max_age_days"]
            with db.connect() as conn:
                db.save_profile(conn, user["id"], p)
                if changed:
                    # naya field / keywords: purane faisle mita kar sab posts naye hisaab se dobara dekho.
                    # Jin leads par user ne kaam kiya (status, note, draft, deal, reminder, assign, feedback) wo rehti hain.
                    conn.execute("""DELETE FROM user_posts WHERE user_id = ? AND (is_lead = 0 OR (
                        status = 'new' AND user_note = '' AND draft = '' AND deal_value IS NULL
                        AND remind_at IS NULL AND assigned_to IS NULL)) AND feedback = ''""", (user["id"],))
            if p["remote_only"] and not p["country"]:
                flash(t("Tip: add your country — then Foxlead can hide remote jobs that are limited to other countries."), "info")
            if (changed or window_changed) and config.AUTO_SCAN_ON_PROFILE and start_scan(user["id"], queue=True):
                flash(t("Profile saved. Foxlead is scanning for leads that fit you — they'll appear in a few minutes."), "success")
            else:
                flash(t("Profile saved. Foxlead will now look for leads that fit you."), "success")
            return redirect(url_for("dashboard"))
        existing = p   # form ko user ki likhi values ke saath dobara dikhao
    telegram = {"on": notify.configured(), "connected": bool(user["telegram_chat_id"]), "link": None,
                "allowed": plans.limits(user)["telegram"]}
    if telegram["on"] and telegram["allowed"] and not telegram["connected"]:
        telegram["link"] = notify.connect_link(user["id"])
    return render_template("profile.html", user=user, profile=existing,
                           professions=PROFESSIONS, feeds=FEEDS, telegram=telegram,
                           age_choices=config.AGE_DAYS_CHOICES, age_default=config.AGE_DAYS_DEFAULT)


@app.route("/telegram/check", methods=["POST"])
@login_required
def telegram_check(user):
    """User ne Telegram mein Start daba diya? Abhi dekh lo (robot ka intezar na karna pade)."""
    if not notify.configured():
        abort(404)
    try:
        notify.sync_updates()
    except notify.TelegramError as e:
        flash(f"Couldn't reach Telegram: {e}")
        return redirect(url_for("profile"))
    with db.connect() as conn:
        linked = conn.execute("SELECT telegram_chat_id FROM users WHERE id = ?", (user["id"],)).fetchone()[0]
    flash(t("Telegram connected — you'll get a message there with your next leads.") if linked
          else t("Not connected yet. Open the Telegram link, press Start, then check again."), "success" if linked else "info")
    return redirect(url_for("profile"))


@app.route("/telegram/disconnect", methods=["POST"])
@login_required
def telegram_disconnect(user):
    with db.connect() as conn:
        conn.execute("UPDATE users SET telegram_chat_id = NULL, telegram_code = NULL WHERE id = ?", (user["id"],))
    flash(t("Telegram disconnected."), "success")
    return redirect(url_for("profile"))


@app.route("/dashboard")
@login_required
def dashboard(user):
    with db.connect() as conn:
        if db.get_profile(conn, workspace_id(user)) is None:
            return redirect(url_for("team") if is_member(user) else url_for("profile"))
    return render_template("dashboard.html", user=user)


# ================= API (dashboard ka data) =================

def drafts_used_today(conn, user_id):
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return conn.execute("SELECT COUNT(*) FROM usage WHERE user_id = ? AND kind = 'draft' AND at >= ?",
                        (user_id, since)).fetchone()[0]


def team_members(conn, user):
    """Team ke log (assign karne ke liye). Team na ho to sirf khud."""
    if not user["team_id"]:
        return [{"id": user["id"], "name": user["name"] or user["email"]}]
    return [{"id": r["id"], "name": r["name"] or r["email"]} for r in
            conn.execute("SELECT id, name, email FROM users WHERE team_id = ? AND disabled = 0 ORDER BY name", (user["team_id"],))]


@app.route("/api/data")
@login_required
def api_data(user):
    wid = workspace_id(user)
    lim = plans.limits(user)
    with db.connect() as conn:
        prof = db.get_profile(conn, wid)
        rows = conn.execute("""
            SELECT p.id, p.link, p.source, p.title, p.text, p.is_job, p.posted_at,
                   up.score, up.reason, up.verdict, up.competition, up.comment_count, up.note,
                   up.status, up.status_at, up.scored_at AS found_at,
                   up.draft, up.draft_at, up.user_note, up.remind_at, up.hot, up.deal_value, up.assigned_to
            FROM user_posts up JOIN posts p ON p.id = up.post_id
            WHERE up.user_id = ? AND up.is_lead = 1 AND up.feedback = ''
            ORDER BY up.scored_at DESC
        """, (wid,)).fetchall()
        runs = conn.execute("SELECT time, fetched, new, scored, leads, status FROM runs "
                            "WHERE user_id = ? ORDER BY id DESC LIMIT 200", (wid,)).fetchall()
        used = drafts_used_today(conn, user["id"])
        members = team_members(conn, user)
    blocklist = prof["blocklist"] if prof else []
    # block list wale leads foran chhupa do (robot naye aise posts score hi nahi karega)
    leads = [dict(r) | {"is_job": bool(r["is_job"])} for r in rows
             if not db.blocked(r["title"] + " " + r["text"], blocklist)]
    return jsonify(
        user={"id": user["id"], "name": user["name"], "email": user["email"], "plan": plans.plan_of(user),
              "team": bool(user["team_id"]), "member": wid != user["id"]},
        team=members,
        plan={"key": plans.plan_of(user), "scan_every_hours": lim["scan_every_hours"]},
        profile={
            "title": prof["title"], "skills": prof["skills"], "country": prof["country"],
            "remote_only": bool(prof["remote_only"]), "threshold": prof["threshold"],
            "subreddits": prof["subreddits"], "keywords": prof["keywords"], "blocklist": blocklist,
            "feeds": [{"key": k, "label": FEEDS[k]["label"]} for k in prof["feeds"] if k in FEEDS],
        } if prof else None,
        leads=leads,
        runs=[dict(r) for r in runs],
        scan={"running": wid in _scanning},
        drafts={"used": used, "limit": lim["drafts_per_day"]},
    )


@app.route("/api/lead", methods=["POST"])
@login_required
def api_lead(user):
    """Lead badlo: status, apna note, follow-up reminder, ya 'not relevant'."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("id"), int):
        return jsonify(error="bad request"), 400
    sets, args = [], []
    if "status" in body:
        if body["status"] not in STATUSES:
            return jsonify(error="bad status"), 400
        sets += ["status = ?", "status_at = ?"]
        args += [body["status"], None if body["status"] == "new" else db.now_utc()]
    if "note" in body:
        if not isinstance(body["note"], str):
            return jsonify(error="bad note"), 400
        sets.append("user_note = ?")
        args.append(body["note"][:2000])
    if "remind_at" in body:
        remind = body["remind_at"]
        if remind is not None:
            try:
                remind = date.fromisoformat(remind).isoformat()    # sirf "YYYY-MM-DD"
            except (TypeError, ValueError):
                return jsonify(error="bad date"), 400
        sets += ["remind_at = ?", "reminded_at = NULL"]
        args.append(remind)
    if "feedback" in body:
        if body["feedback"] not in ("", "not_relevant"):
            return jsonify(error="bad feedback"), 400
        sets.append("feedback = ?")
        args.append(body["feedback"])
    if "deal_value" in body:
        value = body["deal_value"]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not 0 <= value <= 10_000_000):
            return jsonify(error=t("Deal value must be a number between 0 and 10,000,000")), 400
        sets.append("deal_value = ?")
        args.append(round(float(value), 2) if value is not None else None)
    if "assigned_to" in body:
        who = body["assigned_to"]
        with db.connect() as conn:
            allowed = {m["id"] for m in team_members(conn, user)}
        if who is not None and (not isinstance(who, int) or who not in allowed):
            return jsonify(error=t("You can only assign leads to people in your team.")), 400
        sets.append("assigned_to = ?")
        args.append(who)
    if not sets:
        return jsonify(error="nothing to change"), 400
    with db.connect() as conn:
        cur = conn.execute(f"UPDATE user_posts SET {', '.join(sets)} WHERE user_id = ? AND post_id = ?",
                           (*args, workspace_id(user), body["id"]))
    if cur.rowcount == 0:
        return jsonify(error=t("This lead no longer exists — refresh the page.")), 404
    return jsonify(ok=True)


@app.route("/api/draft", methods=["POST"])
@login_required
def api_draft(user):
    """Is lead ke liye AI reply / cover letter draft likhwao (din mein had ke saath)."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("id"), int):
        return jsonify(error="bad request"), 400
    wid, limit = workspace_id(user), plans.limits(user)["drafts_per_day"]
    with db.connect() as conn:
        post = conn.execute("""SELECT p.* FROM user_posts up JOIN posts p ON p.id = up.post_id
                               WHERE up.user_id = ? AND up.post_id = ? AND up.is_lead = 1""",
                            (wid, body["id"])).fetchone()
        prof = db.get_profile(conn, wid)
        used = drafts_used_today(conn, user["id"])
    if post is None or prof is None:
        return jsonify(error=t("This lead no longer exists — refresh the page.")), 404
    if used >= limit:
        more = "" if plans.plan_of(user) == "pro" else t(" Upgrade to Pro for 30 a day.")
        return jsonify(error=t("You've used all {limit} drafts for today — more tomorrow.", limit=limit) + more), 429
    try:
        text = drafts.write_draft(user, prof, post)
    except llm.LLMError as e:
        return jsonify(error=t(str(e))), 502
    with db.connect() as conn:
        conn.execute("UPDATE user_posts SET draft = ?, draft_at = ? WHERE user_id = ? AND post_id = ?",
                     (text, db.now_utc(), wid, body["id"]))
    return jsonify(ok=True, draft=text, used=used + 1, limit=limit)


# "Scan now" - ek user ke liye robot background mein chalao (ek waqt mein ek hi baar)
_scanning = set()
_last_scan = {}
SCAN_COOLDOWN = 2 * 60      # scan khatam hone ke baad itna ruko (scan ab ~1 min leta hai)


@app.route("/api/scan", methods=["POST"])
@login_required
def api_scan(user):
    uid = workspace_id(user)                 # team member owner ki profile scan karta hai
    if uid in _scanning:
        return jsonify(ok=True, running=True)
    if plans.plan_of(user) == "free":        # Free: din mein ek scan (robot wala bhi gina jata hai)
        with db.connect() as conn:
            last = conn.execute("SELECT MAX(time) FROM runs WHERE user_id = ?", (uid,)).fetchone()[0]
        if last and last > iso_ago(days=1):
            return jsonify(error=t("The Free plan scans once a day — upgrade to Pro for hourly scans and Scan now.")), 429
    wait = SCAN_COOLDOWN - (time.time() - _last_scan.get(uid, 0))
    if wait > 0:
        return jsonify(error=t("Please wait {n} min before scanning again.", n=int(wait // 60) + 1)), 429
    start_scan(uid)
    return jsonify(ok=True, running=True)


_rescan = set()               # scan ke dauran profile badli - khatam hote hi nayi profile se dobara
_scan_lock = threading.Lock()


def start_scan(uid, queue=False):
    """Robot ko is user ke liye background mein chalao (ek waqt mein ek hi).
    Pehle se chal raha ho: queue=True par wo khatam hote hi dobara chalega (True), warna False."""
    with _scan_lock:
        if uid in _scanning:
            if queue:
                _rescan.add(uid)
            return queue
        _scanning.add(uid)
        _last_scan[uid] = time.time()

    def work():
        from .pipeline import run_for_users
        while True:
            try:
                run_for_users([uid])
            except Exception as e:             # ek scan ki galti se agla (queued) scan na ruke
                app.logger.warning("scan for user %s failed: %s", uid, e)
            with _scan_lock:
                if uid not in _rescan:
                    _last_scan[uid] = time.time()      # cooldown scan ke KHATAM hone se ginti shuru
                    _scanning.discard(uid)
                    return
                _rescan.discard(uid)

    threading.Thread(target=work, daemon=True).start()
    return True


# ================= Chatbot: Ask Foxlead =================

def chat_used_today(conn, user_id):
    # usage table se ginti - chat mitane se din ki hadd reset na ho
    return conn.execute("SELECT COUNT(*) FROM usage WHERE user_id = ? AND kind = 'chat' AND at >= ?",
                        (user_id, iso_ago(days=1))).fetchone()[0]


@app.route("/api/chat")
@login_required
def api_chat_history(user):
    with db.connect() as conn:
        rows = conn.execute("SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 40",
                            (user["id"],)).fetchall()[::-1]
        used = chat_used_today(conn, user["id"])
    return jsonify(messages=[dict(r) for r in rows], used=used, limit=plans.limits(user)["chat_per_day"])


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat(user):
    message = ((request.get_json(silent=True) or {}).get("message") or "").strip()
    if not message:
        return jsonify(error=t("Type a message first.")), 400
    if len(message) > 2000:
        return jsonify(error=t("That message is too long — keep it under 2000 characters.")), 400
    wid, limit = workspace_id(user), plans.limits(user)["chat_per_day"]
    with db.connect() as conn:
        profile = db.get_profile(conn, wid)
        used = chat_used_today(conn, user["id"])
    if profile is None:
        return jsonify(error=t("Set up your profile first.")), 400
    if used >= limit:
        more = "" if plans.plan_of(user) == "pro" else t(" Upgrade to Pro for 50 a day.")
        return jsonify(error=t("You've used all {limit} messages for today — more tomorrow.", limit=limit) + more), 429
    try:
        answer = chat.reply(user, profile, message, data_uid=wid)
    except llm.LLMError as e:
        return jsonify(error=t(str(e))), 502
    return jsonify(answer=answer, used=used + 1, limit=limit)


@app.route("/api/chat/clear", methods=["POST"])
@login_required
def api_chat_clear(user):
    with db.connect() as conn:   # din ki hadd usage table mein hai, is liye mitane se reset nahi hoti
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user["id"],))
    return jsonify(ok=True)


# ================= Plans + Stripe payment =================

@app.route("/billing")
@login_required
def billing(user):
    return render_template("billing.html", user=user, plan=plans.plan_of(user), stripe_ready=plans.stripe_ready(),
                           member=is_member(user), admin_gift=user["plan_source"] == "admin")


@app.route("/billing/checkout", methods=["POST"])
@login_required
def billing_checkout(user):
    if not plans.stripe_ready():
        flash(t("Payments aren't switched on yet — please try again later."))
        return redirect(url_for("billing"))
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    try:
        kwargs = {"customer": user["stripe_customer_id"]} if user["stripe_customer_id"] else {"customer_email": user["email"]}
        checkout = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": config.STRIPE_PRICE_PRO, "quantity": 1}],
            client_reference_id=str(user["id"]),        # webhook isi se pehchanta hai kis user ne pay kiya
            success_url=url_for("billing_done", _external=True),
            cancel_url=url_for("billing", _external=True),
            **kwargs)
    except stripe.StripeError as e:
        flash(f"Couldn't start the payment: {e.user_message or 'please try again'}")
        return redirect(url_for("billing"))
    return redirect(checkout.url, code=303)


@app.route("/billing/done")
@login_required
def billing_done(user):
    flash(t("Thanks! Your payment went through — Pro switches on within a minute."), "success")
    return redirect(url_for("billing"))


@app.route("/billing/portal", methods=["POST"])
@login_required
def billing_portal(user):
    """Stripe ka apna page: card badlo, invoice dekho, subscription band karo."""
    if not (plans.stripe_ready() and user["stripe_customer_id"]):
        return redirect(url_for("billing"))
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    try:
        portal = stripe.billing_portal.Session.create(customer=user["stripe_customer_id"], return_url=url_for("billing", _external=True))
    except stripe.StripeError as e:
        flash(f"Couldn't open billing: {e.user_message or 'please try again'}")
        return redirect(url_for("billing"))
    return redirect(portal.url, code=303)


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Stripe batata hai: payment hui / subscription badli / band hui. Sirf sahi signature wale messages."""
    if not (plans.stripe_ready() and config.STRIPE_WEBHOOK_SECRET):
        abort(404)
    import stripe
    payload = request.get_data()
    try:
        stripe.Webhook.construct_event(payload, request.headers.get("Stripe-Signature", ""), config.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        return jsonify(error="bad signature"), 400
    # signature sahi hai - ab wahi message saada JSON ki tarah padho
    # (stripe 16 ke objects dict nahi hote, un par .get() nahi chalta)
    event = json.loads(payload)
    kind, obj = event["type"], event["data"]["object"]
    with db.connect() as conn:
        if kind == "checkout.session.completed" and str(obj.get("client_reference_id") or "").isdigit():
            conn.execute("""UPDATE users SET plan = 'pro', plan_source = 'stripe', stripe_customer_id = ?,
                            stripe_subscription_id = ? WHERE id = ?""",
                         (obj.get("customer"), obj.get("subscription"), int(obj["client_reference_id"])))
        elif kind in ("customer.subscription.updated", "customer.subscription.deleted"):
            active = kind.endswith("updated") and obj.get("status") in ("active", "trialing", "past_due")
            conn.execute("UPDATE users SET plan = ? WHERE stripe_customer_id = ? AND plan_source = 'stripe'",
                         ("pro" if active else "free", obj.get("customer")))
    return jsonify(ok=True)


# ================= Agency / team =================

def owned_team(conn, user):
    return conn.execute("SELECT * FROM teams WHERE owner_id = ?", (user["id"],)).fetchone()


@app.route("/team")
@login_required
def team(user):
    with db.connect() as conn:
        mine = owned_team(conn, user)
        current = conn.execute("SELECT t.*, u.name AS owner_name, u.email AS owner_email FROM teams t "
                               "JOIN users u ON u.id = t.owner_id WHERE t.id = ?", (user["team_id"],)).fetchone() if user["team_id"] else None
        members = conn.execute("SELECT id, name, email, last_login_at FROM users WHERE team_id = ? ORDER BY id",
                               (user["team_id"],)).fetchall() if user["team_id"] else []
        invites = conn.execute("SELECT * FROM team_invites WHERE team_id = ? AND accepted_at IS NULL ORDER BY id DESC",
                               (mine["id"],)).fetchall() if mine else []
        has_profile = db.get_profile(conn, user["id"]) is not None
    return render_template("team.html", user=user, mine=mine, current=current, members=members, invites=invites,
                           can_create=plans.limits(user)["team"], has_profile=has_profile)


@app.route("/team/create", methods=["POST"])
@login_required
def team_create(user):
    name = request.form.get("name", "").strip()[:60]
    if not plans.limits(user)["team"]:
        flash(t("Teams are part of Pro — upgrade first."))
    elif user["team_id"]:
        flash(t("You're already in a team."))
    elif not name:
        flash(t("Give your team a name."))
    else:
        with db.connect() as conn:
            if db.get_profile(conn, user["id"]) is None:
                flash(t("Set up your profile first — your team will share it."))
            else:
                tid = conn.execute("INSERT INTO teams (name, owner_id, created_at) VALUES (?, ?, ?)",
                                   (name, user["id"], db.now_utc())).lastrowid
                conn.execute("UPDATE users SET team_id = ? WHERE id = ?", (tid, user["id"]))
                flash(t("Team created — now invite your people."), "success")
    return redirect(url_for("team"))


@app.route("/team/invite", methods=["POST"])
@login_required
def team_invite(user):
    email = request.form.get("email", "").strip().lower()
    with db.connect() as conn:
        mine = owned_team(conn, user)
        if mine is None:
            abort(403)
        if not EMAIL_RE.match(email):
            flash(t("Please enter a valid email address."))
            return redirect(url_for("team"))
        if conn.execute("SELECT 1 FROM users WHERE email = ? AND team_id = ?", (email, mine["id"])).fetchone():
            flash(t("That person is already in your team."))
            return redirect(url_for("team"))
        token = secrets.token_urlsafe(24)
        conn.execute("INSERT INTO team_invites (team_id, email, token, created_at) VALUES (?, ?, ?, ?)",
                     (mine["id"], email, token, db.now_utc()))
    link = url_for("team_join", token=token, _external=True)
    try:
        mailer.send_invite(email, user["name"] or user["email"], mine["name"], link)
        flash(t("Invite sent to {email}.", email=email), "success")
    except mailer.MailError:
        flash(f"Couldn't email the invite — send {email} this link yourself: {link}", "info")
    return redirect(url_for("team"))


@app.route("/team/join/<token>")
def team_join(token):
    user = current_user()
    if user is None:
        flash(t("Log in (or create an account with the invited email) to join the team."), "info")
        return redirect(url_for("login", next=request.path))
    with db.connect() as conn:
        inv = conn.execute("SELECT i.*, t.name, t.owner_id FROM team_invites i JOIN teams t ON t.id = i.team_id "
                           "WHERE i.token = ? AND i.accepted_at IS NULL", (token,)).fetchone()
        if inv is None or inv["created_at"] < iso_ago(days=14):
            flash("That invite link is invalid or has expired — ask for a new one.")
        elif inv["email"].lower() != user["email"].lower():
            flash(f"This invite is for {inv['email']} — log in with that email to join.")
        elif user["team_id"]:
            flash("You're already in a team — leave it first.")
        else:
            conn.execute("UPDATE users SET team_id = ? WHERE id = ?", (inv["team_id"], user["id"]))
            conn.execute("UPDATE team_invites SET accepted_at = ? WHERE id = ?", (db.now_utc(), inv["id"]))
            flash(t("Welcome to {team}! You now share the team's leads.", team=inv['name']), "success")
            return redirect(url_for("dashboard"))
    return redirect(url_for("team"))


@app.route("/team/remove/<int:uid>", methods=["POST"])
@login_required
def team_remove(user, uid):
    with db.connect() as conn:
        mine = owned_team(conn, user)
        if mine is None or uid == user["id"]:
            abort(403)
        conn.execute("UPDATE users SET team_id = NULL WHERE id = ? AND team_id = ?", (uid, mine["id"]))
        conn.execute("UPDATE user_posts SET assigned_to = NULL WHERE user_id = ? AND assigned_to = ?", (user["id"], uid))
    flash(t("Removed from the team."), "success")
    return redirect(url_for("team"))


@app.route("/team/invites/<int:iid>/cancel", methods=["POST"])
@login_required
def team_invite_cancel(user, iid):
    with db.connect() as conn:
        mine = owned_team(conn, user)
        if mine is None:
            abort(403)
        conn.execute("DELETE FROM team_invites WHERE id = ? AND team_id = ?", (iid, mine["id"]))
    return redirect(url_for("team"))


@app.route("/team/leave", methods=["POST"])
@login_required
def team_leave(user):
    with db.connect() as conn:
        if owned_team(conn, user):
            flash("You own this team — remove the members first, or keep it.")
            return redirect(url_for("team"))
        owner = workspace_id(user)
        conn.execute("UPDATE users SET team_id = NULL WHERE id = ?", (user["id"],))
        conn.execute("UPDATE user_posts SET assigned_to = NULL WHERE user_id = ? AND assigned_to = ?", (owner, user["id"]))
    flash(t("You left the team."), "success")
    return redirect(url_for("profile"))


# ================= Admin panel (sirf ADMIN_EMAILS wale) =================

def iso_ago(days=0, **kw):
    """Itna pehle ka waqt (UTC, ISO). iso_ago(7) = 7 din, iso_ago(minutes=2) = 2 minute."""
    return (datetime.now(timezone.utc) - timedelta(days=days, **kw)).strftime("%Y-%m-%dT%H:%M:%SZ")


@app.route("/admin")
@admin_required
def admin(user):
    d7, d30 = iso_ago(7), iso_ago(30)
    with db.connect() as conn:
        users = conn.execute("""
            SELECT u.id, u.name, u.email, u.created_at, u.last_login_at, u.disabled, u.plan, u.plan_source, u.team_id,
                   u.password_hash IS NULL AS google_only, pr.title,
                   (SELECT COUNT(*) FROM user_posts up WHERE up.user_id = u.id AND up.is_lead = 1) AS leads,
                   (SELECT COUNT(*) FROM runs r WHERE r.user_id = u.id) AS scans,
                   (SELECT MAX(time) FROM runs r WHERE r.user_id = u.id) AS last_scan,
                   (SELECT COUNT(*) FROM usage x WHERE x.user_id = u.id AND x.kind = 'draft') AS drafts,
                   (SELECT COALESCE(SUM(input_tokens), 0) FROM usage x WHERE x.user_id = u.id AND x.at >= ?) AS tin,
                   (SELECT COALESCE(SUM(output_tokens), 0) FROM usage x WHERE x.user_id = u.id AND x.at >= ?) AS tout
            FROM users u LEFT JOIN profiles pr ON pr.user_id = u.id
            ORDER BY u.created_at DESC
        """, (d30, d30)).fetchall()
        totals = conn.execute("""
            SELECT (SELECT COUNT(*) FROM users) AS users,
                   (SELECT COUNT(*) FROM users WHERE last_login_at >= ?) AS active7,
                   (SELECT COUNT(*) FROM user_posts WHERE is_lead = 1) AS leads,
                   (SELECT COUNT(*) FROM runs WHERE time >= ?) AS scans7,
                   (SELECT COUNT(*) FROM usage WHERE kind = 'draft' AND at >= ?) AS drafts30,
                   (SELECT COALESCE(SUM(input_tokens), 0) FROM usage WHERE at >= ?) AS tin,
                   (SELECT COALESCE(SUM(output_tokens), 0) FROM usage WHERE at >= ?) AS tout
        """, (d7, d7, d30, d30, d30)).fetchone()
        by_kind = conn.execute("""
            SELECT kind, COUNT(*) AS calls, SUM(input_tokens) AS tin, SUM(output_tokens) AS tout
            FROM usage WHERE at >= ? GROUP BY kind ORDER BY calls DESC
        """, (d30,)).fetchall()
        recent = conn.execute("""
            SELECT r.time, r.fetched, r.new, r.scored, r.leads, r.status, u.name, u.email
            FROM runs r JOIN users u ON u.id = r.user_id ORDER BY r.id DESC LIMIT 15
        """).fetchall()
    return render_template("admin.html", user=user, users=users, totals=totals, by_kind=by_kind,
                           recent=recent, cost=db.cost_usd)


@app.route("/admin/users/<int:uid>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(user, uid):
    if uid == user["id"]:
        flash("You can't disable your own account.")
        return redirect(url_for("admin"))
    with db.connect() as conn:
        target = conn.execute("SELECT email, disabled FROM users WHERE id = ?", (uid,)).fetchone()
        if target is None:
            abort(404)
        conn.execute("UPDATE users SET disabled = ? WHERE id = ?", (0 if target["disabled"] else 1, uid))
    flash(f"{target['email']} is now {'enabled' if target['disabled'] else 'disabled'}.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/users/<int:uid>/plan", methods=["POST"])
@admin_required
def admin_set_plan(user, uid):
    """Admin kisi ko muft Pro de sakta hai (ya wapas Free)."""
    plan = request.form.get("plan")
    if plan not in config.PLANS:
        abort(400)
    with db.connect() as conn:
        target = conn.execute("SELECT email, plan_source FROM users WHERE id = ?", (uid,)).fetchone()
        if target is None:
            abort(404)
        if target["plan_source"] == "stripe" and plan == "free":
            flash(f"{target['email']} pays through Stripe — cancel it in Stripe instead.")
            return redirect(url_for("admin"))
        conn.execute("UPDATE users SET plan = ?, plan_source = ? WHERE id = ?", (plan, "admin" if plan == "pro" else "", uid))
    flash(f"{target['email']} is now on {config.PLANS[plan]['name']}.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    # sirf apne laptop ke liye (127.0.0.1) - online server par gunicorn/waitress use karna
    app.run(host="127.0.0.1", port=5000, debug=False)
