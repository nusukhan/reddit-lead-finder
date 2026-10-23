# foxlead/pipeline.py
# ROBOT: har ghante (ya "Scan now" par) chalta hai.
#   1) sab users ke sources se posts EK baar laao (Reddit, job boards)
#   2) har user ke liye: block list + keywords se chhaanto, phir Claude se score
#   3) achhe leads (score >= user ki hadd): Reddit wale par comments check
#   4) user ko email (naye leads + aaj ke follow-ups), aur run ka hisaab
#
# Chalana:  python -m foxlead.pipeline            (sab users, ek baar)
#           python -m foxlead.pipeline --loop     (har ghante, chalta rahe)
#           python -m foxlead.pipeline --user you@example.com

import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from . import config, db, llm, mailer, notify, plans, scoring, sources
from .professions import FEEDS

SLOW_SOURCES_HOURS = 3      # Remote OK / Hacker News: 3 ghante mein ek baar (unki request)
HOT_HOURS = 3               # itni nayi Reddit post + bohat kam replies = "hot"
SCORE_WORKERS = 8           # Claude se itni posts ek saath score (ek-ek karne se scan bohat lamba tha)


def log(msg):
    print(msg, flush=True)


def ago_iso(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------- 1) fetch ----------------

def fetch_and_store(subreddits, feed_keys, searches=()):
    """Posts laa kar database mein daalo (pehle se ho to chhod do). Return: errors list.
    searches: [(subreddits, keywords), ...] - har user ke field ke keywords se Reddit search.
    Reddit ek line mein (rate limit), baaki har job board saath-saath - scan jaldi khatam hota hai."""
    def reddit():
        got_all, errs = [], []
        if subreddits:
            got, err = sources.fetch_reddit(subreddits)
            got_all += got
            errs += err
            log(f"  Reddit: {len(got)} new posts from {len(subreddits)} subreddits")
        done = set()
        for subs, words in searches:
            key = (tuple(sorted(s.lower() for s in subs)), tuple(sorted(words)))
            if not subs or not words or key in done:      # do users ka ek jaisa search = ek hi request
                continue
            done.add(key)
            got, err = sources.search_reddit(subs, words)
            got_all += got
            errs += err
            log(f"  Reddit search ({', '.join(sorted(words)[:4])}…): {len(got)} posts")
        return got_all, errs

    def feed(key):
        got, err = sources.fetch_feed(key)
        log(f"  {FEEDS[key]['label']}: {len(got)} jobs")
        if not err:
            with db.connect() as conn:
                db.set_meta(conn, "fetched:" + key, db.now_utc())
        return got, err

    with db.connect() as conn:
        last = {k: db.get_meta(conn, "fetched:" + k) for k in feed_keys}
    todo = []
    for key in feed_keys:
        slow = FEEDS[key]["type"] in ("hn", "remoteok")
        if slow and last[key] and last[key] > ago_iso(hours=SLOW_SOURCES_HOURS):
            log(f"  {FEEDS[key]['label']}: fetched recently, skipping")
        else:
            todo.append(key)
    posts, errors = [], []
    with ThreadPoolExecutor(max_workers=1 + max(1, len(todo))) as pool:
        jobs = [pool.submit(reddit)] + [pool.submit(feed, k) for k in todo]
        for j in jobs:
            got, err = j.result()
            posts += got
            errors += err
    now = db.now_utc()
    with db.connect() as conn:
        for p in posts:
            conn.execute("""INSERT OR IGNORE INTO posts (link, source, title, text, is_job, fetched_at, posted_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (p["link"], p["source"], p["title"], p["text"], p["is_job"], now, p["posted_at"]))
    return errors


# ---------------- Reddit comments ----------------

def fetch_comments(link):
    content = sources.get(link.rstrip("/") + ".rss")
    if content is None:
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    out = []
    for i, e in enumerate(root.findall("atom:entry", sources.ATOM)):
        if i == 0:
            continue                                   # pehli entry khud post hai
        text = sources.clean(e.findtext("atom:content", "", sources.ATOM))
        if text and "[deleted]" not in text and "has been automatically removed" not in text:
            out.append(text)
    return out


# ---------------- 2-4) har user ----------------

class StopRun(Exception):
    """Aisi galti jo har user par hogi (jaise galat API key) - poora run roko."""


def user_sources(profile):
    return {"r/" + s.lower() for s in profile["subreddits"]}, set(profile["feeds"])


def process_user(user, profile):
    uid = user["id"]
    reddit_src, feed_src = user_sources(profile)
    with db.connect() as conn:
        # sirf user ke chune din (3 ya 7) ki posts - post kab hui, Foxlead ne kab dekhi wo nahi
        rows = conn.execute("""
            SELECT p.* FROM posts p
            WHERE COALESCE(p.posted_at, p.fetched_at) >= ?
              AND NOT EXISTS (SELECT 1 FROM user_posts up WHERE up.user_id = ? AND up.post_id = p.id)
            ORDER BY COALESCE(p.posted_at, p.fetched_at) DESC                    -- nayi posts pehle
        """, (ago_iso(days=profile["max_age_days"]), uid)).fetchall()
        not_relevant = [r["title"] for r in conn.execute("""
            SELECT p.title FROM user_posts up JOIN posts p ON p.id = up.post_id
            WHERE up.user_id = ? AND up.feedback = 'not_relevant' ORDER BY up.scored_at DESC LIMIT 8""", (uid,))]
    mine = [r for r in rows if r["source"].lower() in reddit_src or r["source"] in feed_src]

    words = scoring.terms(profile)
    to_score, skipped = [], []
    for p in mine:
        blob = p["title"] + " " + p["text"]
        if db.blocked(blob, profile["blocklist"]):
            skipped.append((p, "Hidden by your block list"))
        elif not scoring.matches(blob, words):
            skipped.append((p, "No keyword match"))
        else:
            to_score.append(p)
    # pehle wo jin ke TITLE mein field ka keyword hai, phir baaki - dono mein nayi pehle (sort stable hai)
    to_score.sort(key=lambda p: scoring.relevance(p, profile) >= 6, reverse=True)
    later = to_score[config.MAX_SCORE_PER_USER:]          # baaki agli baar
    to_score = to_score[:config.MAX_SCORE_PER_USER]
    log(f"  {user['email']}: {len(mine)} new posts, {len(skipped)} filtered out, scoring {len(to_score)}"
        + (f" ({len(later)} wait for next run)" if later else ""))
    # chhaante hue posts save NAHI karte: keyword/block list badle (ya code behtar ho) to agle scan mein
    # khud dobara parkhe jaate hain. Ye check muft hai (Claude nahi), aur sirf taazi posts par hota hai.

    def score_one(p):
        try:
            return scoring.score_post(uid, profile, p, not_relevant), None
        except llm.LLMError as e:
            return None, e

    with ThreadPoolExecutor(max_workers=SCORE_WORKERS) as pool:   # Claude ko ek saath kai posts
        results = list(pool.map(score_one, to_score))
    if any(e and "API key" in str(e) for _, e in results):
        raise StopRun(next(str(e) for _, e in results if e and "API key" in str(e)))

    new_leads, scored, failures = [], 0, 0
    for p, (res, err) in zip(to_score, results):
        if err:
            failures += 1
            log(f"    ! {err}")
            continue
        score, reason = res
        if score == 0:                                      # jawab samajh nahi aaya - agli baar dobara
            failures += 1
            continue
        scored += 1
        lead = {"score": score, "reason": reason, "is_lead": int(score >= profile["threshold"]),
                "verdict": "", "competition": "", "comment_count": 0, "note": "", "hot": 0}
        if lead["is_lead"]:
            if p["is_job"]:
                lead.update(verdict="Apply", note="Job listing — apply directly.")
            else:
                comments = fetch_comments(p["link"])
                time.sleep(2)
                if comments is None:
                    lead.update(verdict="Review", note="Couldn't load the comments — open the post to check.")
                else:
                    lead["comment_count"] = len(comments)
                    try:
                        c = scoring.check_comments(uid, profile, p, comments)
                        lead.update(competition=c["competition"], note=c["note"],
                                    verdict={"yes": "Reply", "maybe": "Maybe", "no": "Skip"}.get(c["worth"], "Review"))
                    except llm.LLMError:
                        lead.update(verdict="Review", note="Comment check failed — open the post to check.")
                fresh = p["posted_at"] and p["posted_at"] >= ago_iso(hours=HOT_HOURS)
                lead["hot"] = int(bool(fresh) and lead["comment_count"] <= 2 and lead["verdict"] in ("Reply", "Review"))
            log(f"    LEAD [{score}/10] {lead['verdict']}{' HOT' if lead['hot'] else ''}: {p['title'][:70]}")
        with db.connect() as conn:
            conn.execute("""INSERT OR IGNORE INTO user_posts
                (user_id, post_id, score, reason, is_lead, verdict, competition, comment_count, note, hot, scored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, p["id"], score, reason, lead["is_lead"], lead["verdict"], lead["competition"],
                 lead["comment_count"], lead["note"], lead["hot"], db.now_utc()))
        if lead["is_lead"]:
            new_leads.append({**dict(p), **lead, "source_label": source_label(p["source"])})

    status = deliver(user, profile, new_leads)
    if new_leads and user["telegram_chat_id"] and notify.configured() and plans.limits(user)["telegram"]:
        try:
            sent = notify.lead_alert(user["telegram_chat_id"], profile["telegram_alerts"], new_leads)
            if sent:
                log(f"    telegram: {sent} lead(s) sent")
        except notify.TelegramError as e:
            log(f"    ! telegram failed: {e}")
    if status is None:
        status = "found" if new_leads else ("no_new" if not to_score else ("score_failed" if failures and not scored else "no_leads"))
    with db.connect() as conn:
        conn.execute("INSERT INTO runs (user_id, time, fetched, new, scored, leads, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (uid, db.now_utc(), len(mine), len(to_score), scored, len(new_leads), status))
    return new_leads


def source_label(source):
    return source if source.startswith("r/") else FEEDS.get(source, {}).get("label", source)


def deliver(user, profile, new_leads):
    """Naye leads + aaj ke follow-ups ka email. Return run status (ya None = koi email nahi)."""
    today = datetime.now(timezone.utc).date().isoformat()
    with db.connect() as conn:
        due = conn.execute("""
            SELECT p.id, p.title, p.link, up.user_note FROM user_posts up JOIN posts p ON p.id = up.post_id
            WHERE up.user_id = ? AND up.remind_at IS NOT NULL AND up.remind_at <= ? AND up.reminded_at IS NULL
              AND up.feedback = ''""", (user["id"], today)).fetchall()
    if not profile["email_enabled"] or not (new_leads or due):
        return None
    if not user["email_verified"]:
        # bina tasdeeq ke kisi ke inbox mein email nahi (koi doosre ka email daal kar spam na karwa sake)
        log(f"    ({user['email']} not verified yet - no email)")
        return None
    if not mailer.configured():
        log("    (email not configured - skipping email)")
        return None
    new_leads = sorted(new_leads, key=lambda l: ({"Apply": 0, "Reply": 1, "Maybe": 2, "Review": 3}.get(l["verdict"], 4), -l["score"]))
    try:
        mailer.send_digest({"email": user["email"], "title": profile["title"]}, new_leads, due)
    except mailer.MailError as e:
        log(f"    ! email failed: {e}")
        return "email_failed"
    now = db.now_utc()
    with db.connect() as conn:
        for l in new_leads:
            conn.execute("UPDATE user_posts SET emailed_at = ? WHERE user_id = ? AND post_id = ?", (now, user["id"], l["id"]))
        for d in due:
            conn.execute("UPDATE user_posts SET reminded_at = ? WHERE user_id = ? AND post_id = ?", (now, user["id"], d["id"]))
    log(f"    emailed {user['email']}: {len(new_leads)} leads, {len(due)} follow-ups")
    return "emailed" if new_leads else None


def weekly_stats(conn, user_id):
    since = ago_iso(days=7)
    s = conn.execute("""
        SELECT SUM(is_lead = 1 AND scored_at >= ?) AS leads,
               SUM(status IN ('replied','applied','talking','won','lost') AND status_at >= ?) AS contacted,
               SUM(status = 'won' AND status_at >= ?) AS won,
               COALESCE(SUM(CASE WHEN status = 'won' AND status_at >= ? THEN deal_value END), 0) AS earned,
               SUM(remind_at IS NOT NULL AND remind_at <= date('now', '+7 days') AND feedback = '') AS followups
        FROM user_posts WHERE user_id = ?""", (since, since, since, since, user_id)).fetchone()
    top = conn.execute("""
        SELECT p.*, up.score, up.verdict, up.note, up.reason, up.comment_count, up.hot FROM user_posts up
        JOIN posts p ON p.id = up.post_id
        WHERE up.user_id = ? AND up.is_lead = 1 AND up.status = 'new' AND up.feedback = '' AND up.verdict IN ('Apply','Reply')
        ORDER BY up.score DESC, up.scored_at DESC LIMIT 5""", (user_id,)).fetchall()
    return ({k: (s[k] or 0) for k in ("leads", "contacted", "won", "earned", "followups")},
            [{**dict(t), "source_label": source_label(t["source"])} for t in top])


def maybe_send_weekly(user, profile, force=False):
    """Monday ko (ya --weekly par) pichhle hafte ka summary email - har user ko hafte mein ek baar."""
    monday = datetime.now(timezone.utc).weekday() == 0
    recent = user["weekly_sent_at"] and user["weekly_sent_at"] > ago_iso(days=6)
    if not (force or (monday and not recent)) or not profile["weekly_report"] or not plans.limits(user)["weekly_report"]:
        return
    if not user["email_verified"] or not mailer.configured():
        return
    with db.connect() as conn:
        stats, top = weekly_stats(conn, user["id"])
    try:
        mailer.send_weekly(user, profile["title"], stats, top)
    except mailer.MailError as e:
        log(f"    ! weekly report failed: {e}")
        return
    with db.connect() as conn:
        conn.execute("UPDATE users SET weekly_sent_at = ? WHERE id = ?", (db.now_utc(), user["id"]))
    log(f"    weekly report sent to {user['email']}")


def run_for_users(user_ids=None, weekly=False):
    """Robot ka ek chakkar. user_ids=None -> sab active users. weekly=True -> report abhi bhejo."""
    db.init_db()
    if notify.configured():
        try:
            n = notify.sync_updates()        # jinhone Telegram par Start dabaya, unhe jodo
            if n:
                log(f"Telegram: {n} user(s) connected")
        except notify.TelegramError as e:
            log(f"  ! telegram sync failed: {e}")
    with db.connect() as conn:
        users = conn.execute("""SELECT u.* FROM users u JOIN profiles p ON p.user_id = u.id
                                WHERE u.disabled = 0 ORDER BY u.id""").fetchall()
        if user_ids is not None:
            users = [u for u in users if u["id"] in set(user_ids)]
        # team members ko skip - owner ka scan poori team ke liye hai
        owners = {r["id"]: r["owner_id"] for r in conn.execute("SELECT id, owner_id FROM teams")}
        users = [u for u in users if not u["team_id"] or owners.get(u["team_id"]) == u["id"]]
        if user_ids is None:
            # robot (har ghanta): plan ki hadd se pehle dobara scan nahi (Free = din mein ek)
            def due(u):
                last = conn.execute("SELECT MAX(time) FROM runs WHERE user_id = ?", (u["id"],)).fetchone()[0]
                hours = plans.limits(u)["scan_every_hours"]
                return not last or last <= ago_iso(hours=hours, minutes=-5)
            users = [u for u in users if due(u)]
        profiles = {u["id"]: db.get_profile(conn, u["id"]) for u in users}
    if not users:
        log("No users with a profile yet - nothing to do.")
        return
    subs = sorted({s.lower(): s for u in users for s in profiles[u["id"]]["subreddits"]}.values(), key=str.lower)
    feeds = sorted({f for u in users for f in profiles[u["id"]]["feeds"] if f in FEEDS})
    log(f"Fetching for {len(users)} user(s)…")
    searches = [(profiles[u["id"]]["subreddits"], sorted(scoring.terms(profiles[u["id"]]))) for u in users]
    errors = fetch_and_store(subs, feeds, searches)
    for e in errors:
        log(f"  ! could not fetch: {e}")
    for u in users:
        try:
            process_user(u, profiles[u["id"]])
            maybe_send_weekly(u, profiles[u["id"]], force=weekly)
        except StopRun as e:
            log(f"STOPPED: {e}")
            with db.connect() as conn:
                conn.execute("INSERT INTO runs (user_id, time, status) VALUES (?, ?, 'score_failed')", (u["id"], db.now_utc()))
            return


def main():
    ap = argparse.ArgumentParser(description="Foxlead robot - find and score leads for every user.")
    ap.add_argument("--loop", action="store_true", help="run every hour until stopped")
    ap.add_argument("--user", help="only this user's email")
    ap.add_argument("--weekly", action="store_true", help="send the weekly report now (normally Mondays)")
    args = ap.parse_args()
    ids = None
    if args.user:
        db.init_db()
        with db.connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (args.user,)).fetchone()
        if row is None:
            sys.exit(f"No user with email {args.user}")
        ids = [row["id"]]
    while True:
        started = time.time()
        run_for_users(ids, weekly=args.weekly)
        args.weekly = False                  # --loop ke saath sirf pehli baar
        if not args.loop:
            break
        log("Done. Next run in an hour.")
        time.sleep(max(60, 3600 - (time.time() - started)))


if __name__ == "__main__":
    main()
