# run_all.py
# Maqsad: poora pipeline EK command se chalao (GitHub Actions har ghanta yahi chalata hai):
#   1) fetch_posts.py    -> posts.json
#   2) seen.json se purani posts hatao (sirf NAYI posts LLM ko jayein)
#   3) classify_posts.py -> leads.json (+ scored.json)
#   4) enrich_leads.py   -> leads.json mein comments/competition
#   5) send_email.py     -> email
#   6) seen.json update  -> agli baar wahi posts dobara na aayein
#
# seen.json ka asool:
#   - jo post LLM ne score kar di (lead NAHI bani) -> foran seen (dobara score na ho)
#   - jo LEAD bani -> seen SIRF tab jab email chala jaye (email fail = agli baar dobara)
#   - score 0 = LLM se jawab nahi aaya -> seen NAHI, agli baar dobara try

import os
import sys
import json
import subprocess

SEEN_FILE = "seen.json"
MAX_NEW_PER_RUN = 80   # ek run mein itni nayi posts max (GitHub ka 30 min timeout + Gemini limit)
MAX_SEEN = 5000        # seen.json hamesha barhti na rahe - sirf aakhri 5000 links rakho


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


# -------- seen.json load (list - purani pehle, nayi aakhir mein) --------
seen = load_json(SEEN_FILE, [])
seen_set = set(seen)


def mark_seen(links):
    for link in links:
        if link and link not in seen_set:
            seen_set.add(link)
            seen.append(link)
    save_json(SEEN_FILE, seen[-MAX_SEEN:])


# -------- 1) posts lao --------
if not run("fetch_posts.py"):
    print("ERROR: fetch_posts.py fail ho gaya.")
    sys.exit(1)


# -------- 2) sirf NAYI posts rakho --------
posts = load_json("posts.json", [])
new_posts = [p for p in posts if p.get("link") not in seen_set]
print(f"\n==> {len(posts)} posts mileen, {len(new_posts)} nayi (baaki pehle dekh chuke).")

if len(new_posts) > MAX_NEW_PER_RUN:
    print(f"    Is run mein sirf {MAX_NEW_PER_RUN} score karenge, baaki agle ghante.")
    new_posts = new_posts[:MAX_NEW_PER_RUN]

if not new_posts:
    print("Kuch naya nahi - email nahi bhejenge.")
    sys.exit(0)

save_json("posts.json", new_posts)   # classify ab sirf nayi posts dekhega


# -------- 3) score karo --------
# purani leads.json/scored.json hata do - warna classify fail ho to purana data use ho jaye
for old in ("leads.json", "scored.json"):
    if os.path.exists(old):
        os.remove(old)

if not run("classify_posts.py"):
    print("ERROR: classify_posts.py fail ho gaya.")
    sys.exit(1)

leads = load_json("leads.json", [])
lead_links = {l["link"] for l in leads}
scored = load_json("scored.json", [])

# jo score ho gayeen aur lead nahi baneen -> seen (score 0 = LLM fail, unhe chhodo)
mark_seen(p["link"] for p in scored
          if p.get("score", 0) > 0 and p["link"] not in lead_links)

if not leads:
    print("\nKoi lead nahi mili (score 7+) - email nahi bhejenge.")
    sys.exit(0)


# -------- 4) comments/competition --------
# yeh fail ho to bhi email bhejo - leads.json classify wali hi rahegi (bina comments ke)
if not run("enrich_leads.py"):
    print("WARNING: enrich_leads.py fail - leads bina comment-analysis ke bhej rahe hain.")


# -------- 5) email --------
if not run("send_email.py"):
    print("ERROR: email nahi gaya - leads seen.json mein NAHI daali, agli baar dobara aayengi.")
    sys.exit(1)


# -------- 6) email chala gaya -> leads bhi seen --------
mark_seen(lead_links)
print(f"\nHo gaya! {len(leads)} leads email ho gayeen, seen.json mein {len(seen_set)} links.")
