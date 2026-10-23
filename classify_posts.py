# classify_posts.py
# Maqsad: HAR post/job ko 1-10 SCORE do - Brevlox jo BECHTA hai uske hisaab se:
# live Laravel/PHP/Vue app jo phasa/toota/developer gaya = sabse acha lead.
 
import os
import re
import json
import time
import anthropic   # Claude ka official package
 
# .env file se keys padho (laptop pe). GitHub pe .env nahi hota -
# wahan keys seedhi environment (Secrets) se aati hain, to agar
# dotenv na mile ya .env na ho to bhi code chalta rahe.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
 
api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("ERROR: ANTHROPIC_API_KEY nahi mili! .env check karo.")
    exit(1)

# max_retries: 429 / server error par SDK khud itni baar dobara try karta hai
client = anthropic.Anthropic(api_key=api_key, max_retries=4)
# Claude Haiku 5.5 - sabse sasta aur tez Claude model, scoring ke liye kaafi.
MODEL_NAME = "claude-haiku-5-5"
 
THRESHOLD = 7   # 7+ = lead (strong leads hi; 6 wale borderline the)
 
with open("posts.json", "r", encoding="utf-8") as f:
    all_posts = json.load(f)
 
print(f"posts.json se {len(all_posts)} posts load hueen.\n")
 
 
def score_post(post):
    text_short = post["text"][:1200]
 
    prompt = f"""You screen posts/jobs to find clients for Brevlox, an agency that builds and
takes over Laravel / PHP / Vue web apps and SaaS.
 
Brevlox's BEST buyer = someone who already has a LIVE Laravel/PHP/Vue app that is
stuck, slow, broken, or lost its developer (they need a takeover, audit, or fix).
 
Score 1-10. Judge by BUYING INTENT + whether it matches our stack (Laravel / PHP / Vue).
 
Score 8-10 ONLY if:
  - A company/person with a LIVE Laravel, PHP, or Vue app that is stuck, slow,
    broken, or lost its developer (takeover / audit / fix / ongoing dev), OR
  - A clear job hiring a Laravel / PHP / full-stack(PHP) / Vue developer for a real product.
 
Score 6-7 if:
  - A non-technical founder who needs a Laravel/Vue app or SaaS BUILT or FIXED for pay
    (real intent to pay, even if the app isn't built yet).
 
Score 1-4 (LOW) for:
  - Idea-only posts with NO app built yet ("how do I validate my idea", "thinking of building").
  - Free code/debug questions a dev answers for free.
  - Other developers or agencies ADVERTISING their services ([For Hire], portfolios).
  - "Equity only" / co-founder with no pay.
  - WRONG STACK: React-only, Python, Ruby, WordPress, mobile-only, data/ML, DevOps,
    Salesforce, blockchain, etc. If it's clearly not PHP/Laravel/Vue, score 1-2.
  - General business/marketing/funding talk.
  - SUCCESS / REVENUE BRAG with no ask: a founder celebrating a milestone
    ("I hit $11k MRR!", "finished Product of the Day", "generated $1600 in revenue")
    who is NOT asking for a developer, a fix, or help. A live app alone is NOT enough -
    there must be a PROBLEM to fix or clear intent to HIRE. No ask = score 3-4.
 
IMPORTANT:
  - Favour CLEAR buying intent + our stack (Laravel/PHP/Vue). When both are present, score high.
  - LOCATION: We apply from PAKISTAN and can only take REMOTE / worldwide work.
    If a job is LOCKED to one country or region and that country is NOT Pakistan
    (e.g. "US only", "US-based only", "UK only", "must be based in the UK",
    "must reside in Germany", "EU residents only", "authorized to work in the US",
    "GMT/Berlin time zone only", on-site in a specific city), then it is useless to us
    -> score 4 MAX, even if the stack is a perfect Laravel/PHP/Vue match.
    A job that is REMOTE / worldwide / "work from anywhere" / no location requirement
    is GOOD - score it normally on stack + intent.
    If unsure whether location is restricted, treat it as REMOTE (do not punish it).
  - A generic "how do I validate my idea" with no app = LOW.
  - Wrong stack = LOW even if it's a real paid job.
  - DO NOT GUESS THE STACK. If a job does NOT clearly say Laravel, PHP, or Vue, you may
    NOT assume "it could be" our stack. "Full-stack" or "software engineer" alone is NOT
    PHP/Laravel/Vue. If the stack is not explicitly PHP/Laravel/Vue, score 4 MAX.
    Only score 8-10 when PHP, Laravel, or Vue is ACTUALLY named in the post.
  - A live app with ONLY a success story and no problem/hiring = score 3-4, not a lead.
  - NON-DEVELOPER ROLES are always LOW (score 1-2), even at a tech company:
    "Care Coach", "Marketing Operations", "Sales", "Talent Acquisition", "Client Success",
    "Data Scientist/Engineer", "ML Engineer", "Security Engineer", "Product Manager".
    We only want jobs that build/fix the Laravel/PHP/Vue WEB APP itself.
 
Give ONE whole number from 1 to 10. Do NOT write a range like "8-10" or "3-4".
 
Post/Job:
Title: {post['title']}
Source: {post.get('subreddit','')}
Text: {text_short}
 
Answer in EXACTLY this format, nothing else:
SCORE: a number 1-10
REASON: one short sentence"""
 
    return ask_llm(prompt)
 
 
def ask_llm(prompt):
    """
    Claude (Haiku) se jawab lo.
    SDK 429/server error par khud dobara try karta hai; phir bhi limit lage to ruk ke dobara.
    """
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model=MODEL_NAME,
                max_tokens=2000,                     # thinking + chhota jawab dono isi mein
                output_config={"effort": "low"},    # simple scoring - kam soch, kam kharcha
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError:
            # key galat hai - har post par yahi hoga, is liye poora script rok do
            print("\n   [ERROR: ANTHROPIC_API_KEY galat hai - platform.claude.com par check karo]")
            exit(1)
        except anthropic.BadRequestError as e:
            # jaise "credit balance too low" - dobara try ka faida nahi
            print(f"\n   [ASLI ERROR: {e.message[:160]}]")
            break
        except anthropic.RateLimitError:
            print("(limit, ruk...)", end=" ")
            time.sleep(30)
            continue
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            if attempt == 0:
                print(f"\n   [ASLI ERROR: {str(e)[:160]}]")
            time.sleep(5)
            continue
        if resp.stop_reason == "refusal":
            break
        # jawab mein thinking + text blocks hote hain - sirf text chahiye
        return "".join(b.text for b in resp.content if b.type == "text")
    return "SCORE: 0\nREASON: Claude se jawab nahi aaya"
 
 
def get_score(answer):
    # "SCORE:" wali line dhoondo, usme se PEHLA number nikalo.
    # (Agar galti se "8-10" aaye to sirf 8 lega, 81 nahi.)
    for line in answer.splitlines():
        if "score" in line.lower():
            m = re.search(r"\d+", line)
            if m:
                n = int(m.group())
                return 10 if n > 10 else n   # 10 se upar kabhi nahi
    # agar "SCORE:" line hi na mile, poore jawab se pehla number
    m = re.search(r"\d+", answer)
    if m:
        n = int(m.group())
        return 10 if n > 10 else n
    return 0
 
 
# Hum PAKISTAN se apply karte hain -> sirf REMOTE/worldwide kaam.
# Ye phrases matlab job kisi EK mulk mein band hai (Pakistan nahi) -> bekaar.
# LLM kabhi miss kar de to ye code-level safety score ko 4 pe cap kar deti hai.
COUNTRY_LOCK_PHRASES = [
    "us only", "u.s. only", "usa only", "us-based only", "based in the us",
    "must be based in the us", "must reside in the us",
    "authorized to work in the us", "us work authorization",
    "us citizen", "green card",
    "uk only", "based in the uk", "must be based in the uk", "uk residents",
    "eu only", "eu residents", "based in europe only", "europe only",
    "germany only", "based in germany", "canada only", "australia only",
    "india only", "philippines only",
]
# Ye phrases matlab job remote hai -> chhodo (lock mat samjho).
REMOTE_OK_PHRASES = [
    "worldwide", "work from anywhere", "anywhere in the world",
    "fully remote", "remote - global", "remote (global)", "global remote",
    "any location", "any timezone", "any time zone", "no location",
]
 
 
def location_capped(post, score):
    """Agar job kisi ek mulk mein band hai (Pakistan nahi) -> score max 4."""
    blob = (post.get("title", "") + " " + post.get("text", "")).lower()
    # pehle dekho kahin saaf 'remote/worldwide' to nahi - to lock mat lagao
    if any(p in blob for p in REMOTE_OK_PHRASES):
        return score
    # Pakistan ka zikr ho to bhi theek (hamara apna mulk)
    if "pakistan" in blob:
        return score
    # ab dekho kisi mulk ki paabandi to nahi
    if any(p in blob for p in COUNTRY_LOCK_PHRASES):
        return min(score, 4)
    return score
 
 
scored = []
for i, post in enumerate(all_posts, start=1):
    print(f"[{i}/{len(all_posts)}] {post['title'][:45]}...", end=" ")
    try:
        answer = score_post(post)
    except Exception as e:
        print(f"ERROR ({e})")
        time.sleep(3)
        continue
    score = get_score(answer)
    # location safety: ek-mulk-wali (Pakistan nahi) job -> score max 4
    capped = location_capped(post, score)
    if capped < score:
        print(f"(location-lock, {score}->{capped})", end=" ")
        score = capped
    post["score"] = score
    post["llm_answer"] = answer
    scored.append(post)
    print(f"score: {score}")
    time.sleep(1)
 
 
scored.sort(key=lambda p: p["score"], reverse=True)
leads = [p for p in scored if p["score"] >= THRESHOLD]
 
print(f"\n{'='*50}")
print(f"==> {len(leads)} leads mileen (score {THRESHOLD}+), sabse achi upar:\n")
for post in leads:
    print(f"[{post['score']}/10] [{post['subreddit']}] {post['title']}")
    for line in post["llm_answer"].splitlines():
        if "reason:" in line.lower():
            print(f"     {line.strip()}")
    print(f"     {post['link']}\n")
 
with open("leads.json", "w", encoding="utf-8") as f:
    json.dump(leads, f, ensure_ascii=False, indent=2)

# saari scored posts (link + score) bhi save karo - run_all.py inse seen.json
# update karta hai, taake agle ghante yehi posts dobara LLM ko na jayein.
with open("scored.json", "w", encoding="utf-8") as f:
    json.dump([{"link": p["link"], "score": p["score"]} for p in scored],
              f, ensure_ascii=False, indent=2)
 
print(f"{'='*50}")
print(f"\n{len(leads)} leads 'leads.json' mein save ho gayeen (score {THRESHOLD}+).")
 
