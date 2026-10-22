# db_setup.py
# Phase 1, Kadam 1: leads.json ko ek DATABASE (foxlead.db) mein daalo.
#
# Yeh samajhne ke liye hai ke database kaise kaam karta hai:
#   - ek database file banao (foxlead.db)
#   - ek "leads" table banao (jaise Excel sheet: id, title, score, ...)
#   - leads.json se saari leads us table mein daal do
#
# sqlite3 Python mein PEHLE se hota hai - kuch install nahi karna.
 
import sqlite3      # database (SQLite) - Python mein built-in
import json         # leads.json padhne ke liye
import os
 
DB_FILE = "foxlead.db"       # hamari database file ka naam
JSON_FILE = "leads.json"     # jahan se leads aati hain
 
 
# -------- 1) Database se judo (file na ho to khud ban jati hai) --------
# connect() ek "connection" deta hai - database se baat karne ka raasta.
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()          # cursor = database ko hukum dene wala
print(f"Database '{DB_FILE}' ready.")
 
 
# -------- 2) "leads" table banao (agar pehle se na ho) --------
# Yeh SQL hai (database ki zabaan). Table = sheet. Har () wali line = ek column.
# "IF NOT EXISTS" matlab: agar table pehle se hai to dobara mat banao.
cur.execute("""
CREATE TABLE IF NOT EXISTS leads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- har lead ka apna number (khud badhta)
    title       TEXT,        -- lead ka naam
    link        TEXT UNIQUE, -- post ka link (UNIQUE = ek link ek hi baar aaye)
    score       INTEGER,     -- 1-10 score
    source      TEXT,        -- LaraJobs / Reddit / WWR
    verdict     TEXT,        -- apply / reply / skip
    competition TEXT,        -- low / n/a
    note        TEXT,        -- AI ka chhota note
    is_job      INTEGER      -- 1 = job, 0 = reddit post
)
""")
print("Table 'leads' ready.")
 
 
# -------- 3) leads.json padho --------
if not os.path.exists(JSON_FILE):
    print(f"ERROR: {JSON_FILE} nahi mili. Pehle classify/enrich chala ke leads banao.")
    conn.close()
    exit()
 
with open(JSON_FILE, "r", encoding="utf-8") as f:
    leads = json.load(f)
 
print(f"\n{len(leads)} leads '{JSON_FILE}' se padhi.")
 
 
# -------- helper: analysis text se ek field nikaalo (COMPETITION/WORTH/NOTE) --------
def get_field(analysis, key):
    for line in (analysis or "").splitlines():
        if line.lower().strip().startswith(key.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""
 
 
# verdict nikaalo (jobs = apply; reddit = worth ke hisaab se)
def verdict_of(lead):
    is_job = bool(lead.get("is_job")) or "reddit.com" not in lead.get("link", "").lower()
    if is_job:
        return "apply"
    w = get_field(lead.get("comment_analysis", ""), "worth").lower()
    return {"yes": "reply", "maybe": "maybe", "no": "skip"}.get(w, "review")
 
 
# -------- 4) har lead ko table mein daalo --------
added = 0
for lead in leads:
    comp = get_field(lead.get("comment_analysis", ""), "competition") or "n/a"
    note = get_field(lead.get("comment_analysis", ""), "note") or ""
    is_job = 1 if ("reddit.com" not in lead.get("link", "").lower()) else 0
 
    # INSERT OR IGNORE: agar yeh link pehle se table mein hai (UNIQUE), to skip.
    # "?" ka matlab: yahan value aayegi - yeh surakshit tareeka hai (SQL injection se bachta hai).
    cur.execute("""
        INSERT OR IGNORE INTO leads (title, link, score, source, verdict, competition, note, is_job)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        lead.get("title", ""),
        lead.get("link", ""),
        int(lead.get("score", 0)),
        lead.get("subreddit", ""),
        verdict_of(lead),
        comp,
        note,
        is_job,
    ))
    if cur.rowcount:      # rowcount = kitni rows add hueen (0 agar skip)
        added += 1
 
conn.commit()             # commit = pakka save karo (bina iske save nahi hota)
print(f"{added} nayi leads database mein daali (purani skip hueen).")
 
 
# -------- 5) ab database se padh ke dikhao (yeh asli maza hai) --------
print("\n" + "="*50)
print("Database se leads (score ke hisaab se, upar best):\n")
 
# SELECT = padho. "ORDER BY score DESC" = score zyada wali upar.
cur.execute("SELECT score, verdict, source, title FROM leads ORDER BY score DESC")
for row in cur.fetchall():      # fetchall = saari rows lao
    score, verdict, source, title = row
    print(f"  [{score}/10] {verdict:6} {source:12} {title[:45]}")
 
# bonus: ek SQL sawaal - sirf 'apply' wali kitni hain?
cur.execute("SELECT COUNT(*) FROM leads WHERE verdict = 'apply'")
apply_count = cur.fetchone()[0]
print(f"\n==> Total {apply_count} 'apply' leads database mein.")
 
print("="*50)
 
 
# -------- 6) connection band karo (hamesha aakhir mein) --------
conn.close()
print(f"\nHo gaya! '{DB_FILE}' file ban gayi - yeh tumhari database hai.")
print("Ise kholne ke liye 'DB Browser for SQLite' (free app) use kar sakti ho.")
 