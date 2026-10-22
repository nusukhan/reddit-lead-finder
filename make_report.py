
# make_report.py
# Maqsad: leads.json ko ek saaf HTML page (leads.html) banao jo Umar bhai
# khol kar dekh sakein - score, competition, worth, note, link sab ek jagah.
 
import json
import html
from datetime import datetime
 
with open("leads.json", "r", encoding="utf-8") as f:
    leads = json.load(f)
 
print(f"leads.json se {len(leads)} leads load hueen.")
 
 
# --- helper: analysis text se ek field nikaalo (COMPETITION/WORTH/NOTE) ---
def get_field(analysis, key):
    for line in (analysis or "").splitlines():
        if line.lower().strip().startswith(key.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""
 
 
# --- "worth" ke hisaab se rang ---
def worth_color(worth):
    w = worth.lower()
    if w == "yes":
        return "#16a34a"   # green
    if w == "maybe":
        return "#d97706"   # orange
    if w == "no":
        return "#dc2626"   # red
    return "#6b7280"       # grey
 
 
# --- leads ko sort: pehle WORTH yes, phir kam competition ---
def sort_key(lead):
    worth = get_field(lead.get("comment_analysis", ""), "worth").lower()
    worth_rank = {"yes": 0, "maybe": 1, "no": 2}.get(worth, 3)
    return (worth_rank, lead.get("comment_count", 999))
 
leads.sort(key=sort_key)
 
 
# --- HTML banao ---
rows = ""
for lead in leads:
    worth = get_field(lead.get("comment_analysis", ""), "worth") or "?"
    comp = get_field(lead.get("comment_analysis", ""), "competition") or "?"
    note = get_field(lead.get("comment_analysis", ""), "note") or "-"
    title = html.escape(lead["title"])
    link = html.escape(lead["link"])
    sub = html.escape(lead.get("subreddit", ""))
    score = lead.get("score", "?")
    count = lead.get("comment_count", 0)
    color = worth_color(worth)
 
    rows += f"""
    <div class="card">
      <div class="top">
        <span class="badge" style="background:{color}">WORTH: {html.escape(worth).upper()}</span>
        <span class="score">Score {score}/10</span>
        <span class="comp">Competition: {html.escape(comp)} · {count} replies</span>
      </div>
      <a href="{link}" target="_blank" class="title">{title}</a>
      <div class="sub">{sub}</div>
      <div class="note">{html.escape(note)}</div>
    </div>"""
 
today = datetime.now().strftime("%d %b %Y, %I:%M %p")
 
page = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Reddit Leads for Umar</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; background:#f3f4f6;
         color:#111827; max-width:760px; margin:0 auto; padding:24px; }}
  h1 {{ font-size:1.5rem; margin:0 0 4px; }}
  .meta {{ color:#6b7280; font-size:0.9rem; margin-bottom:24px; }}
  .card {{ background:#fff; border:1px solid #e5e7eb; border-radius:10px;
          padding:16px; margin-bottom:12px; }}
  .top {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap;
         margin-bottom:8px; font-size:0.8rem; }}
  .badge {{ color:#fff; padding:2px 10px; border-radius:20px; font-weight:700; }}
  .score {{ color:#374151; font-weight:600; }}
  .comp {{ color:#6b7280; }}
  .title {{ display:block; font-size:1.05rem; font-weight:600; color:#1d4ed8;
           text-decoration:none; margin:4px 0; }}
  .title:hover {{ text-decoration:underline; }}
  .sub {{ color:#9ca3af; font-size:0.8rem; }}
  .note {{ color:#374151; font-size:0.92rem; margin-top:6px; }}
</style>
</head>
<body>
  <h1>Reddit Leads for Umar</h1>
  <div class="meta">{len(leads)} leads · {today} · best (WORTH: yes, low competition) on top</div>
  {rows}
</body>
</html>"""
 
with open("leads.html", "w", encoding="utf-8") as f:
    f.write(page)
 
print("leads.html ban gaya! Use double-click karke browser mein kholo.")
 