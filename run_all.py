# run_all.py
# Maqsad: poora pipeline EK command se chalao (GitHub Actions har ghanta yahi chalata hai):
#   1) fetch_posts.py    -> posts.json
#   2) seen.json se purani posts hatao (sirf NAYI posts LLM ko jayein)
#   3) classify_posts.py -> leads.json (+ scored.json)
#   4) enrich_leads.py   -> leads.json mein comments/competition
#   5) send_email.py     -> email
#   6) seen.json update  -> agli baar wahi posts dobara na aayein
#   7) history.json + make_dashboard.py -> dashboard/index.html (har run ke aakhir mein)
#
# seen.json ka asool:
#   - jo post LLM ne score kar di (lead NAHI bani) -> foran seen (dobara score na ho)
#   - jo LEAD bani -> seen SIRF tab jab email chala jaye (email fail = agli baar dobara)
#   - score 0 = LLM se jawab nahi aaya -> seen NAHI, agli baar dobara try

import os
import sys
import json
import subprocess
from datetime import datetime, timezone

SEEN_FILE = "seen.json"
HISTORY_FILE = "history.json"
MAX_NEW_PER_RUN = 80   # ek run mein itni nayi posts max (GitHub ka 30 min timeout + Gemini limit)
MAX_SEEN = 5000        # seen.json hamesha barhti na rahe - sirf aakhri 5000 links rakho
MAX_RUNS = 2000        # history.json mein aakhri 2000 runs (~3 mahine hourly)


def run(script):
    """Ek script chalao. Exit code 0 nahi = fail -> False."""
    print(f"\n{'#'*50}\n# {script}\n{'#'*50}", flush=True)
    result = subprocess.run([sys.executable, script])
    return result.returncode == 0


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -------- seen.json load (list - purani pehle, nayi aakhir mein) --------
seen = load_json(SEEN_FILE, [])
seen_set = set(seen)


def mark_seen(links):
    for link in links:
        if link and link not in seen_set:
            seen_set.add(link)
            seen.append(link)
    save_json(SEEN_FILE, seen[-MAX_SEEN:])


# -------- is run ka hisaab (dashboard ke liye) --------
run_info = {"time": now_utc(), "fetched": 0, "new": 0, "scored": 0, "leads": 0, "status": ""}
emailed_leads = []   # sirf woh leads jo email ho gayeen - yehi dashboard par jaati hain


def get_field(analysis, key):
    """comment_analysis se COMPETITION / WORTH / NOTE nikaalo."""
    for line in (analysis or "").splitlines():
        if line.lower().strip().startswith(key.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def lead_record(lead):
    """Ek lead ka chhota record history.json ke liye (send_email.py wala verdict)."""
    analysis = lead.get("comment_analysis", "")
    is_job = "reddit.com" not in lead.get("link", "").lower()
    if is_job:
        verdict = "Apply"
    else:
        worth = get_field(analysis, "worth").lower()
        verdict = {"yes": "Reply", "maybe": "Maybe", "no": "Skip"}.get(worth, "Review")
    return {
        "found_at": run_info["time"],
        "title": lead.get("title", ""),
        "link": lead.get("link", ""),
        "source": lead.get("subreddit", ""),
        "score": int(lead.get("score", 0)),
        "verdict": verdict,
        "competition": "" if is_job else get_field(analysis, "competition"),
        "comment_count": lead.get("comment_count", 0),
        "note": get_field(analysis, "note"),
        "reason": get_field(lead.get("llm_answer", ""), "reason"),   # LLM ne score kyun diya
        "text": (lead.get("text") or "")[:700],                       # post/job ka shuru ka hissa
        "is_job": is_job,
    }


def finish(code, status):
    """Run ka hisaab history.json mein likho, dashboard banao, phir band karo."""
    run_info["status"] = status
    history = load_json(HISTORY_FILE, {"runs": [], "leads": []})
    history["runs"] = (history.get("runs", []) + [run_info])[-MAX_RUNS:]
    history["leads"] = history.get("leads", []) + emailed_leads
    save_json(HISTORY_FILE, history)
    run("make_dashboard.py")   # dashboard fail ho to bhi pipeline ka nateeja wahi rahe
    sys.exit(code)


# -------- 1) posts lao --------
if not run("fetch_posts.py"):
    print("ERROR: fetch_posts.py fail ho gaya.")
    finish(1, "fetch_failed")


# -------- 2) sirf NAYI posts rakho --------
posts = load_json("posts.json", [])
new_posts = [p for p in posts if p.get("link") not in seen_set]
run_info["fetched"] = len(posts)
print(f"\n==> {len(posts)} posts mileen, {len(new_posts)} nayi (baaki pehle dekh chuke).")


def priority(post):
    """Job boards pehle score hon (wahan asli leads zyada hain), Reddit baad mein."""
    link = post.get("link", "").lower()
    if "larajobs.com" in link:
        return 0
    if "weworkremotely.com" in link:
        return 1
    return 2


new_posts.sort(key=priority)   # sort "stable" hai - har group ke andar order wahi rehta hai

if len(new_posts) > MAX_NEW_PER_RUN:
    print(f"    Is run mein sirf {MAX_NEW_PER_RUN} score karenge, baaki agle ghante.")
    new_posts = new_posts[:MAX_NEW_PER_RUN]
run_info["new"] = len(new_posts)

if not new_posts:
    print("Kuch naya nahi - email nahi bhejenge.")
    finish(0, "no_new")

save_json("posts.json", new_posts)   # classify ab sirf nayi posts dekhega


# -------- 3) score karo --------
# purani leads.json/scored.json hata do - warna classify fail ho to purana data use ho jaye
for old in ("leads.json", "scored.json"):
    if os.path.exists(old):
        os.remove(old)

if not run("classify_posts.py"):
    print("ERROR: classify_posts.py fail ho gaya.")
    finish(1, "classify_failed")

leads = load_json("leads.json", [])
lead_links = {l["link"] for l in leads}
scored = load_json("scored.json", [])
run_info["scored"] = len(scored)
run_info["leads"] = len(leads)

# jo score ho gayeen aur lead nahi baneen -> seen (score 0 = LLM fail, unhe chhodo)
mark_seen(p["link"] for p in scored
          if p.get("score", 0) > 0 and p["link"] not in lead_links)

if not leads:
    print("\nKoi lead nahi mili (score 7+) - email nahi bhejenge.")
    finish(0, "no_leads")


# -------- 4) comments/competition --------
# yeh fail ho to bhi email bhejo - leads.json classify wali hi rahegi (bina comments ke)
if not run("enrich_leads.py"):
    print("WARNING: enrich_leads.py fail - leads bina comment-analysis ke bhej rahe hain.")


# -------- 5) email --------
if not run("send_email.py"):
    print("ERROR: email nahi gaya - leads seen.json mein NAHI daali, agli baar dobara aayengi.")
    finish(1, "email_failed")


# -------- 6) email chala gaya -> leads bhi seen + dashboard par --------
mark_seen(lead_links)
emailed_leads = [lead_record(l) for l in load_json("leads.json", [])]
print(f"\nHo gaya! {len(leads)} leads email ho gayeen, seen.json mein {len(seen_set)} links.")
finish(0, "emailed")
