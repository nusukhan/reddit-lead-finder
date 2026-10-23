# foxlead/sources.py
# Posts/jobs laana: Reddit (kai subreddits EK request mein), RSS job boards,
# Hacker News "Who is hiring?" aur Remote OK. Har post ek dict banti hai:
#   {link, source, title, text, is_job, posted_at}

import re
import html
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

from .config import JOB_MAX_AGE_HOURS, POST_MAX_AGE_HOURS
from .professions import FEEDS

HEADERS = {"User-Agent": "foxlead-lead-finder/1.0"}
ATOM = {"atom": "http://www.w3.org/2005/Atom"}
REDDIT_CHUNK = 10          # ek request mein itne subreddits (r/a+b+c/new.rss)


def clean(text):
    """HTML tags hatao, &amp; jaise codes theek karo, faltu space hatao."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(html.unescape(text).split())


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse_iso(s):
    try:
        dt = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def too_old(dt, hours=POST_MAX_AGE_HOURS):
    return dt is not None and dt < datetime.now(timezone.utc) - timedelta(hours=hours)


_reddit_next_ok = 0.0     # Reddit (bina login) ek waqt mein ~1 request deta hai - agli kab bhej sakte hain


def _reddit_wait(r):
    """Reddit ke headers batate hain kitni requests bachi hain aur kab reset hogi - utna intezar yaad rakho."""
    global _reddit_next_ok
    try:
        remaining = float(r.headers.get("x-ratelimit-remaining", "1"))
        reset = float(r.headers.get("x-ratelimit-reset", "0"))
    except ValueError:
        return
    if remaining < 1 and reset:
        _reddit_next_ok = time.time() + min(reset, 90) + 1


def get(url, as_json=False):
    """GET with retry. Fail = None.
    Reddit: uske bataye waqt tak ruko (x-ratelimit-reset), baaki sites: 429 par 15 sec, network error par 5 sec."""
    reddit = "reddit.com" in url
    for attempt in range(3):
        if reddit and time.time() < _reddit_next_ok:
            time.sleep(_reddit_next_ok - time.time())
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
        except requests.RequestException:
            time.sleep(5)
            continue
        if reddit:
            _reddit_wait(r)
        if r.status_code == 200:
            try:
                return r.json() if as_json else r.content
            except ValueError:
                return None
        if r.status_code == 429:
            if not reddit or _reddit_next_ok <= time.time():
                time.sleep(15)      # waqt nahi bataya - 15 sec
            continue                # Reddit ne waqt bataya - wo intezar agli koshish se pehle khud hota hai
        return None
    return None


# ---------------- Reddit ----------------

def fetch_reddit(subreddits):
    """Saare subreddits ki NAYI posts - 10 subreddits ek request mein (Reddit ka rate limit bachane ko)."""
    wanted = {s.lower(): s for s in subreddits}
    posts, errors = [], []
    names = list(wanted.values())
    for i in range(0, len(names), REDDIT_CHUNK):
        chunk = names[i:i + REDDIT_CHUNK]
        got = parse_reddit(get(f"https://www.reddit.com/r/{'+'.join(chunk)}/new.rss?limit=100"), wanted)
        if got is None:
            errors.append("Reddit: " + ", ".join("r/" + c for c in chunk))
        else:
            posts += got
    return posts, errors


def search_reddit(subreddits, words):
    """User ke subreddits ke ANDAR uske keywords se search (nayi posts pehle).
    Sirf "nayi posts" mein bade subreddits (r/forhire, r/SaaS) chhoti-si field ki posts ko dabaa dete hain -
    search se seedha "laravel OR php OR vue" wali posts milti hain."""
    if not subreddits or not words:
        return [], []
    wanted = {s.lower(): s for s in subreddits}
    terms = sorted(words, key=len, reverse=True)[:8]          # Reddit lambi query pasand nahi karta
    query = " OR ".join(f'"{w}"' if " " in w else w for w in terms)
    url = (f"https://www.reddit.com/r/{'+'.join(list(wanted.values())[:REDDIT_CHUNK])}/search.rss"
           f"?q={quote(query)}&restrict_sr=1&sort=new&t=week&limit=100")
    got = parse_reddit(get(url), wanted)
    return (got, []) if got is not None else ([], ["Reddit search"])


def parse_reddit(content, wanted):
    """Reddit ki Atom feed -> posts (sirf wanted subreddits, sirf taazi). Padh na sake to None."""
    if content is None:
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:               # kabhi XML ki jagah block page aata hai
        return None
    posts = []
    for e in root.findall("atom:entry", ATOM):
        cat = e.find("atom:category", ATOM)
        sub = wanted.get((cat.attrib.get("term", "") if cat is not None else "").lower())
        link_el = e.find("atom:link", ATOM)
        if not sub or link_el is None:
            continue
        when = parse_iso((e.findtext("atom:published", "", ATOM) or e.findtext("atom:updated", "", ATOM)))
        if too_old(when):
            continue
        posts.append({
            "link": link_el.attrib.get("href", ""),
            "source": "r/" + sub,
            "title": (e.findtext("atom:title", "", ATOM) or "").strip(),
            "text": clean(e.findtext("atom:content", "", ATOM))[:3000],
            "is_job": 0,
            "posted_at": iso(when),
        })
    return posts


# ---------------- RSS job boards ----------------

def fetch_rss(key):
    content = get(FEEDS[key]["url"])
    if content is None:
        return [], [FEEDS[key]["label"]]
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return [], [FEEDS[key]["label"]]
    posts = []
    for it in root.findall(".//item"):
        try:
            when = parsedate_to_datetime(it.findtext("pubDate", ""))
        except (TypeError, ValueError):
            when = None
        if too_old(when, hours=JOB_MAX_AGE_HOURS):
            continue
        link = (it.findtext("link", "") or "").strip()
        if link:
            posts.append({"link": link, "source": key, "title": (it.findtext("title", "") or "").strip(),
                          "text": clean(it.findtext("description", ""))[:3000], "is_job": 1, "posted_at": iso(when)})
    return posts, []


# ---------------- Hacker News: Who is hiring? ----------------

def fetch_hn():
    found = get("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10", as_json=True)
    story = next((h for h in (found or {}).get("hits", [])
                  if h.get("title", "").startswith("Ask HN: Who is hiring?")), None)
    if story is None:
        return [], ["Hacker News"]
    thread = get(f"https://hn.algolia.com/api/v1/items/{story['objectID']}", as_json=True)
    if thread is None:
        return [], ["Hacker News"]
    posts = []
    for c in thread.get("children", []):          # sirf seedhe comments = har ek ek job
        text = clean(c.get("text"))
        when = parse_iso(c.get("created_at"))
        # thread mahine ki 1 tareekh ko banta hai - sirf us mein nayi daali gayi jobs lo
        if not text or too_old(when, hours=JOB_MAX_AGE_HOURS):
            continue
        first = re.split(r"(?<=[.!?])\s|\n", text, maxsplit=1)[0]
        posts.append({"link": f"https://news.ycombinator.com/item?id={c['id']}", "source": "hn_hiring",
                      "title": first[:140], "text": text[:3000], "is_job": 1, "posted_at": iso(when)})
    return posts, []


# ---------------- Remote OK ----------------

def fetch_remoteok():
    data = get("https://remoteok.com/api", as_json=True)
    if not isinstance(data, list):
        return [], ["Remote OK"]
    posts = []
    for j in data[1:]:                            # pehla item legal notice hai
        when = parse_iso(j.get("date"))
        if too_old(when, hours=JOB_MAX_AGE_HOURS) or not j.get("url"):
            continue
        extra = " · ".join(x for x in [j.get("location") or "", ", ".join(j.get("tags") or [])] if x)
        posts.append({"link": j["url"], "source": "remoteok",
                      "title": f"{j.get('company', '').strip()}: {j.get('position', '').strip()}".strip(": "),
                      "text": (clean(j.get("description")) + (f" [{extra}]" if extra else ""))[:3000],
                      "is_job": 1, "posted_at": iso(when)})
    return posts, []


def fetch_feed(key):
    kind = FEEDS[key]["type"]
    if kind == "rss":
        return fetch_rss(key)
    if kind == "hn":
        return fetch_hn()
    if kind == "remoteok":
        return fetch_remoteok()
    return [], []
