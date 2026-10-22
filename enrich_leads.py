# enrich_leads.py
# Maqsad: Top leads ke COMMENTS laao, phir:
#   1) count - kitne log already comment kar chuke (competition/bheed)
#   2) LLM - comments padh kar batao worth it ya nahi, OP ne extra kya kaha
# Yeh leads.json ko behtar (enriched) banata hai.
 
import os
import json
import time
import re
import requests
import xml.etree.ElementTree as ET
from google import genai   # Google ka naya AI package (google-genai)
 
# .env se keys (laptop). GitHub pe .env nahi hota - keys environment
# (Secrets) se aati hain, to dotenv na ho to bhi code chale.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
 
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    print("ERROR: GOOGLE_API_KEY nahi mili! .env check karo.")
    exit(1)
 
client = genai.Client(api_key=api_key)
MODEL_NAME = "gemini-3.8-flash"
 
 
def ask_llm(prompt):
    """Google (Gemini) se jawab lo. Limit lage to ruk ke dobara."""
    for attempt in range(4):
        try:
            resp = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            return resp.text
        except Exception as e:
            msg = str(e)
            if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                print("(limit, ruk...)", end=" ")
                time.sleep(30)
                continue
            if attempt == 0:
                print(f"\n   [ASLI ERROR: {msg[:160]}]")
            time.sleep(3)
    return "COMPETITION: n/a\nWORTH: maybe\nNOTE: Google se jawab nahi aaya"
 
headers = {"User-Agent": "lead-finder by Nusu"}
ns = {"atom": "http://www.w3.org/2005/Atom"}
 
# --- leads.json load karo ---
with open("leads.json", "r", encoding="utf-8") as f:
    leads = json.load(f)
 
print(f"leads.json se {len(leads)} leads load hueen.\n")
 
 
# --- Helper: yeh lead Reddit ki hai ya job site ki? ---
# Sirf Reddit posts pe comments hote hain. LaraJobs/WWR job listings
# hain - unke comments nahi, to un pr comment-check SKIP karte hain.
def is_reddit(link):
    return "reddit.com" in (link or "").lower()
 
 
# --- Helper: ek post ke comments laao (429 par retry) ---
def fetch_comments(link):
    url = link.rstrip("/") + ".rss"
    for attempt in range(3):
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.content
        if r.status_code == 429:
            print("(429 ruk...)", end=" ")
            time.sleep(15)
            continue
        return None
    return None
 
 
# --- Helper: RSS se comments ka saaf text nikaalo ---
def parse_comments(content):
    root = ET.fromstring(content)
    entries = root.findall("atom:entry", ns)
    comments = []
    for i, entry in enumerate(entries):
        if i == 0:
            continue   # pehli entry khud post hai, chhodo
        content_el = entry.find("atom:content", ns)
        text = content_el.text if content_el is not None else ""
        clean = re.sub("<[^>]+>", " ", text or "")
        clean = " ".join(clean.split())
        # "removed/deleted" waale system comments chhodo (woh asli log nahi)
        if "[deleted]" in clean or "has been automatically removed" in clean:
            continue
        if clean:
            comments.append(clean)
    return comments
 
 
# --- Helper: LLM se comments ka khulasa ---
def analyze_comments(lead, comments):
    # pehle 15 asli comments bhejo (bahut saare mehnge)
    sample = "\n".join(f"- {c[:200]}" for c in comments[:15])
 
    prompt = f"""A freelance Laravel/SaaS developer is deciding whether to reply to this Reddit post.
 
POST TITLE: {lead['title']}
 
REAL COMMENTS (other people's replies):
{sample if sample else "(no real comments yet)"}
 
Based on the comments, answer:
- COMPETITION: how crowded is this? (low / medium / high)
- WORTH: should the developer bother replying? (yes / maybe / no)
- NOTE: one short sentence - any useful detail (budget mentioned? already found someone? too many applicants?)
 
Answer in EXACTLY this format:
COMPETITION: low or medium or high
WORTH: yes or maybe or no
NOTE: one short sentence"""
 
    return ask_llm(prompt)
 
 
# --- Har lead ko enrich karo ---
for i, lead in enumerate(leads, start=1):
    print(f"[{i}/{len(leads)}] {lead['title'][:45]}...")
 
    # JOB POST (LaraJobs/WWR)? -> comments hote hi nahi, skip karo.
    if not is_reddit(lead["link"]):
        print("   job post hai (LaraJobs/WWR) - comment-check skip")
        lead["comment_count"] = 0
        lead["comment_analysis"] = ("COMPETITION: n/a\n"
                                    "WORTH: yes\n"
                                    "NOTE: Job listing - apply directly, no Reddit comments.")
        lead["is_job"] = True
        continue
 
    lead["is_job"] = False
    content = fetch_comments(lead["link"])
    if content is None:
        print("   comments nahi mile (skip)")
        lead["comment_count"] = 0
        lead["comment_analysis"] = "comments not available"
        time.sleep(8)
        continue
 
    comments = parse_comments(content)
    lead["comment_count"] = len(comments)
    print(f"   {len(comments)} real comments (competition)")
 
    # LLM se khulasa
    try:
        analysis = analyze_comments(lead, comments)
        lead["comment_analysis"] = analysis
        print(f"   {analysis.strip().splitlines()[0] if analysis else ''}")
    except Exception as e:
        lead["comment_analysis"] = "LLM error"
        print(f"   LLM error: {e}")
 
    time.sleep(8)   # Reddit + LLM ko saans do
 
 
# --- enriched leads save karo ---
with open("leads.json", "w", encoding="utf-8") as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)
 
print(f"\n{'='*50}")
print(f"\n{len(leads)} leads enrich ho gayeen (comments + analysis), leads.json mein save.")
print("\nSummary:\n")
 
for lead in leads:
    print(f"[{lead['score']}/10] {lead['title'][:55]}")
    print(f"   comments: {lead.get('comment_count', 0)}")
    for line in lead.get("comment_analysis", "").splitlines():
        if line.strip():
            print(f"   {line.strip()}")
    print(f"   {lead['link']}\n")
 