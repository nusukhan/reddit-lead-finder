# fetch_posts.py
# Maqsad: 3 jagah se posts/jobs lao -
#   A) Reddit (hiring + problem) - RSS/XML (Atom <entry>)
#   B) LaraJobs - Laravel jobs ka feed (RSS 2.0 <item>)
#   C) We Work Remotely - PHP/Laravel/Full-Stack jobs (RSS 2.0 <item>)
# Sab ek posts.json mein, duplicate hata kar.
 
import requests
import xml.etree.ElementTree as ET
import time
import json
import re
 
headers = {"User-Agent": "lead-finder by Nusu"}
 
# Reddit ki RSS "Atom" format hai - yeh namespace us ke liye
atom_ns = {"atom": "http://www.w3.org/2005/Atom"}
 
all_posts = []
seen_links = set()
 
 
def fetch_rss(url):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=20)
        except Exception as e:
            print(f"(net error, ruk...)", end=" ")
            time.sleep(10)
            continue
        if r.status_code == 200:
            return r.content
        if r.status_code == 429:
            print("(429 ruk...)", end=" ")
            time.sleep(15)
            continue
        print(f"(status {r.status_code})", end=" ")
        return None
    return None
 
 
def clean_text(t):
    t = re.sub("<[^>]+>", " ", t or "")   # HTML tags hatao
    return " ".join(t.split())
 
 
def add_post(subreddit, title, link, text):
    if not link or link in seen_links:
        return False
    seen_links.add(link)
    all_posts.append({
        "subreddit": subreddit,
        "title": (title or "").strip(),
        "link": link.strip(),
        "text": clean_text(text)[:1500],
    })
    return True
 
 
# --- XML parho. Kabhi site XML ki jagah HTML (block/captcha page) de deti hai -
#     tab poora script crash na ho, bas yeh feed skip ho jaye. ---
def parse_xml(content):
    try:
        return ET.fromstring(content)
    except ET.ParseError:
        print("(XML nahi mila, skip)", end=" ")
        return None


# --- Reddit ki Atom feed parho (<entry>) ---
def add_reddit(content, source):
    if content is None:
        return 0
    root = parse_xml(content)
    if root is None:
        return 0
    entries = root.findall("atom:entry", atom_ns)
    n = 0
    for e in entries:
        title = (e.find("atom:title", atom_ns).text if e.find("atom:title", atom_ns) is not None else "")
        link = e.find("atom:link", atom_ns).attrib.get("href", "") if e.find("atom:link", atom_ns) is not None else ""
        c = e.find("atom:content", atom_ns)
        text = c.text if c is not None else ""
        if add_post(source, title, link, text):
            n += 1
    return n
 
 
# --- LaraJobs/WWR ki RSS 2.0 feed parho (<item>) ---
def add_rss2(content, source):
    if content is None:
        return 0
    root = parse_xml(content)
    if root is None:
        return 0
    items = root.findall(".//item")
    n = 0
    for it in items:
        title = it.find("title").text if it.find("title") is not None else ""
        link = it.find("link").text if it.find("link") is not None else ""
        desc = it.find("description")
        text = desc.text if desc is not None else ""
        if add_post(source, title, link, text):
            n += 1
    return n
 
 
# ========= A) REDDIT =========
print("--- A) Reddit ---")
reddit_subs = ["forhire", "SaaS", "webdev", "laravel"]
reddit_queries = ["need a developer", "stuck on", "stripe issue", "need help with"]
for sub in reddit_subs:
    for q in reddit_queries:
        print(f"r/{sub} '{q}'...", end=" ")
        url = f"https://www.reddit.com/r/{sub}/search.rss?q={q}&restrict_sr=1&sort=new&t=month"
        print(f"{add_reddit(fetch_rss(url), f'r/{sub}')} posts")
        time.sleep(7)
 
 
# ========= B) LARAJOBS =========
print("\n--- B) LaraJobs ---")
print("larajobs...", end=" ")
print(f"{add_rss2(fetch_rss('https://larajobs.com/feed'), 'LaraJobs')} jobs")
time.sleep(3)
 
 
# ========= C) WE WORK REMOTELY =========
print("\n--- C) We Work Remotely ---")
wwr_feeds = {
    "WWR-FullStack": "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "WWR-Programming": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
}
for name, url in wwr_feeds.items():
    print(f"{name}...", end=" ")
    print(f"{add_rss2(fetch_rss(url), name)} jobs")
    time.sleep(3)
 
 
# ========= SAVE =========
print(f"\n==> Total {len(all_posts)} unique posts/jobs jama hueen\n")
with open("posts.json", "w", encoding="utf-8") as f:
    json.dump(all_posts, f, ensure_ascii=False, indent=2)
print("Saari posts 'posts.json' mein save ho gayeen.")
print("Ab classify_posts.py chalao.")
 