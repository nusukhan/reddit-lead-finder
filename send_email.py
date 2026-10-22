# send_email.py
# Maqsad: leads.json ko ek PROFESSIONAL HTML email banakar Umar bhai ko bhejo.
#
# ZAROORI: Email clients (Gmail waghera) modern CSS (gradient, shadow, flexbox,
# ::before) theek se support NAHI karte. Isliye yeh email "email-safe" tareeke se
# banta hai: HTML TABLES + INLINE styles. Design wahi (design #3) rehta hai -
# gradient header, stat strip, cards, badges, button - bas HTML purane andaz mein.
 
import os
import json
import html
import smtplib
from email.message import EmailMessage
from datetime import datetime
 
# .env se keys (laptop). GitHub pe .env nahi hota - keys environment
# (Secrets) se aati hain, to dotenv na ho to bhi code chale.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
 
gmail_address = os.getenv("GMAIL_ADDRESS")
app_password = os.getenv("GMAIL_APP_PASSWORD")
to_email = os.getenv("TO_EMAIL")
 
if not gmail_address or not app_password or not to_email:
    print("ERROR: .env mein GMAIL_ADDRESS / GMAIL_APP_PASSWORD / TO_EMAIL check karo.")
    exit(1)
 
with open("leads.json", "r", encoding="utf-8") as f:
    leads = json.load(f)
 
print(f"leads.json se {len(leads)} leads load hueen.")
 
 
# ---------- rang (design #3 jaise) ----------
NAVY = "#1b2a4a"
BLUE = "#2e5bc0"
INK = "#14161c"
SOFT = "#5a6472"
FAINT = "#9aa3b2"
LINE = "#e9edf3"
PAGE = "#eef1f6"
YES, YES_BG = "#12875a", "#e4f5ec"
WARN, WARN_BG = "#b7791f", "#fdf3e2"
NO, NO_BG = "#c4453c", "#fbe9e7"
 
 
# ---------- helpers ----------
def get_field(analysis, key):
    """comment_analysis se COMPETITION / WORTH / NOTE nikaalo."""
    for line in (analysis or "").splitlines():
        if line.lower().strip().startswith(key.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""
 
 
def is_job(lead):
    return bool(lead.get("is_job")) or "reddit.com" not in lead.get("link", "").lower()
 
 
def verdict_for(lead):
    """
    Har lead ka ek saaf verdict: Apply / Reply / Maybe / Skip + rang.
    - Jobs (LaraJobs/WWR): hamesha 'Apply' (apply directly).
    - Reddit: comment analysis ke WORTH par - yes=Reply, maybe=Maybe, no=Skip.
    """
    if is_job(lead):
        return ("Apply", "yes")
    worth = get_field(lead.get("comment_analysis", ""), "worth").lower()
    if worth == "yes":
        return ("Reply", "yes")
    if worth == "maybe":
        return ("Maybe", "warn")
    if worth == "no":
        return ("Skip", "no")
    return ("Review", "warn")
 
 
def kind_colors(kind):
    return {
        "yes": (YES, YES_BG),
        "warn": (WARN, WARN_BG),
        "no": (NO, NO_BG),
    }.get(kind, (SOFT, "#f1f2f5"))
 
 
def source_line(lead):
    """Card ke upar dayein taraf chhoti line: source + (Reddit ho to) comments/competition."""
    src = lead.get("subreddit", "") or "source"
    if is_job(lead):
        return html.escape(src)
    comp = get_field(lead.get("comment_analysis", ""), "competition") or "?"
    count = lead.get("comment_count", 0)
    return f"{html.escape(src)} &middot; {count} comments &middot; {html.escape(comp)} competition"
 
 
# ---------- sort: verdict rank, phir score zyada upar ----------
RANK = {"Apply": 0, "Reply": 1, "Maybe": 2, "Review": 3, "Skip": 4}
 
def sort_key(lead):
    label, _ = verdict_for(lead)
    return (RANK.get(label, 9), -int(lead.get("score", 0)))
 
leads.sort(key=sort_key)
 
 
# ---------- ek lead ka card (email-safe table) ----------
def card_html(lead):
    label, kind = verdict_for(lead)
    rail = {"yes": YES, "warn": WARN, "no": NO}.get(kind, BLUE)
    pill_fg, pill_bg = kind_colors(kind)
    faded = ' style="opacity:0.82;"' if label == "Skip" else ""
 
    title = html.escape(lead.get("title", ""))
    link = html.escape(lead.get("link", "#"))
    score = lead.get("score", "?")
    note = get_field(lead.get("comment_analysis", ""), "note")
    if not note:
        note = "Direct match for our stack." if is_job(lead) else "-"
    note = html.escape(note)
    btn_text = "View job &rarr;" if is_job(lead) else "Open post &rarr;"
 
    # Table-based card: left rail cell (4px) + content cell.
    return f"""
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
             style="background:#ffffff;border:1px solid {LINE};border-radius:12px;margin-bottom:12px;"{faded}>
        <tr>
          <td width="4" style="background:{rail};border-radius:12px 0 0 12px;font-size:0;line-height:0;">&nbsp;</td>
          <td style="padding:15px 18px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="font-size:0;">
                  <span style="display:inline-block;font-family:Consolas,monospace;font-size:12px;font-weight:700;color:#ffffff;background:{NAVY};border-radius:6px;padding:3px 9px;vertical-align:middle;">{score}/10</span>
                  <span style="display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:{pill_fg};background:{pill_bg};border-radius:20px;padding:3px 11px;margin-left:6px;vertical-align:middle;">{label}</span>
                </td>
                <td align="right" style="font-size:12px;color:{FAINT};">{source_line(lead)}</td>
              </tr>
            </table>
            <a href="{link}" style="display:block;font-size:17px;font-weight:700;color:{INK};text-decoration:none;line-height:1.3;margin:10px 0 6px;">{title}</a>
            <div style="font-size:14px;color:{SOFT};line-height:1.5;margin-bottom:12px;">{note}</div>
            <a href="{link}" style="display:inline-block;font-size:13px;font-weight:700;color:#ffffff;background:{NAVY};border-radius:8px;padding:8px 16px;text-decoration:none;">{btn_text}</a>
          </td>
        </tr>
      </table>"""
 
 
# ---------- counts for stat strip ----------
total_scanned = None
# posts.json ho to "scanned" ka asli number dikhao
if os.path.exists("posts.json"):
    try:
        with open("posts.json", "r", encoding="utf-8") as pf:
            total_scanned = len(json.load(pf))
    except Exception:
        total_scanned = None
 
worth_count = sum(1 for l in leads if verdict_for(l)[0] in ("Apply", "Reply"))
skip_count = sum(1 for l in leads if verdict_for(l)[0] == "Skip")
top_score = max((int(l.get("score", 0)) for l in leads), default=0)
scanned_txt = str(total_scanned) if total_scanned else str(len(leads))
 
cards = "".join(card_html(l) for l in leads)
today = datetime.now().strftime("%d %B %Y")
 
 
def stat_cell(num, label, green=False):
    color = YES if green else INK
    return f"""
        <td align="center" style="padding:15px 6px;border-right:1px solid {LINE};">
          <div style="font-family:Consolas,monospace;font-size:21px;font-weight:700;color:{color};">{num}</div>
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{FAINT};margin-top:3px;">{label}</div>
        </td>"""
 
 
# ---------- poora email ----------
body_html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:{PAGE};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAGE};">
    <tr>
      <td align="center" style="padding:20px 12px;">
        <table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="width:640px;max-width:100%;font-family:Arial,Helvetica,sans-serif;">
 
          <!-- masthead -->
          <tr>
            <td style="background:{NAVY};background:linear-gradient(135deg,{NAVY} 0%,{BLUE} 135%);border-radius:16px 16px 0 0;padding:26px 28px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-size:0;">
                    <span style="display:inline-block;width:26px;height:26px;background:#ffffff;color:{NAVY};font-weight:800;font-size:15px;text-align:center;line-height:26px;border-radius:7px;vertical-align:middle;">B</span>
                    <span style="color:#ffffff;font-weight:700;font-size:15px;margin-left:9px;vertical-align:middle;">Brevlox</span>
                  </td>
                </tr>
              </table>
              <div style="color:#ffffff;font-size:24px;font-weight:700;margin-top:16px;letter-spacing:-0.3px;">Today&rsquo;s lead shortlist</div>
              <div style="color:rgba(255,255,255,0.80);font-size:13px;margin-top:6px;">{today} &middot; Reddit &middot; LaraJobs &middot; We Work Remotely</div>
            </td>
          </tr>
 
          <!-- stat strip -->
          <tr>
            <td style="background:#ffffff;border-left:1px solid {LINE};border-right:1px solid {LINE};">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  {stat_cell(scanned_txt, "Scanned")}
                  {stat_cell(worth_count, "Worth it", green=True)}
                  {stat_cell(skip_count, "Skip")}
                  <td align="center" style="padding:15px 6px;">
                    <div style="font-family:Consolas,monospace;font-size:21px;font-weight:700;color:{INK};">{top_score}</div>
                    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{FAINT};margin-top:3px;">Top</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
 
          <!-- body -->
          <tr>
            <td style="background:#ffffff;border:1px solid {LINE};border-top:none;border-radius:0 0 16px 16px;padding:18px;">
              <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:{FAINT};font-weight:700;margin:2px 2px 12px;">Ranked &mdash; best on top</div>
              {cards}
              <div style="text-align:center;font-size:12px;color:{FAINT};margin-top:18px;line-height:1.6;">
                <b style="color:{SOFT};">Dark rail = reply or apply.</b><br>
                Generated automatically by your lead-finder. You send every reply yourself.
              </div>
            </td>
          </tr>
 
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
 
 
# ---------- Email banao aur bhejo ----------
msg = EmailMessage()
msg["Subject"] = f"{worth_count} leads worth replying today — Brevlox"
msg["From"] = gmail_address
msg["To"] = to_email
msg.set_content(
    "Aapke daily leads taiyyar hain. (Yeh email HTML mein best dikhta hai.)\n\n"
    + "\n".join(
        f"[{l.get('score','?')}/10] {verdict_for(l)[0]} - {l.get('title','')}\n{l.get('link','')}"
        for l in leads
    )
)
msg.add_alternative(body_html, subtype="html")
 
print("Email bhej rahe hain...")
 
try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.send_message(msg)
    print(f"\nEmail bhej diya {to_email} ko! Inbox check karo.")
except Exception as e:
    print(f"\nERROR: email nahi gaya.\n{e}")
    exit(1)   # 1 = fail - run_all.py phir leads ko seen.json mein nahi daalta
 
