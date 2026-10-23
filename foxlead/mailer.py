# foxlead/mailer.py
# Emails: naye leads + follow-up reminders (aur aage: password reset, weekly report).
# Email clients modern CSS nahi samajhte - is liye HTML TABLES + inline styles.

import html
import smtplib
from email.message import EmailMessage

from . import config

NAVY, BLUE, INK, SOFT, FAINT, LINE, PAGE = "#1b2a4a", "#2e5bc0", "#14161c", "#5a6472", "#9aa3b2", "#e9edf3", "#eef1f6"
YES, YES_BG, WARN, WARN_BG, NO, NO_BG = "#12875a", "#e4f5ec", "#b7791f", "#fdf3e2", "#c4453c", "#fbe9e7"
KIND = {"Apply": (YES, YES_BG), "Reply": (YES, YES_BG), "Maybe": (WARN, WARN_BG), "Review": (WARN, WARN_BG), "Skip": (NO, NO_BG)}


class MailError(Exception):
    pass


def configured():
    return bool(config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD)


def send(to, subject, html_body, text_body):
    """Gmail se email bhejo. Fail ho to MailError."""
    if not configured():
        raise MailError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD are not set")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Foxlead <{config.GMAIL_ADDRESS}>"
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(str(e)) from e


def esc(s):
    return html.escape(s or "")


def safe_link(url):
    """Sirf http(s) links - feed mein 'javascript:' jaisa kuch aaye to email mein na jaye."""
    return url if (url or "").lower().startswith(("http://", "https://")) else "#"


def layout(title, subtitle, body_html, button_text=None, button_url=None):
    """Sab emails ka ek hi dhaancha: navy header, safed body, neeche button."""
    button = ""
    if button_text:
        button = (f'<div style="text-align:center;margin:22px 0 6px;"><a href="{esc(button_url)}" style="display:inline-block;'
                  f'font-size:14px;font-weight:700;color:#fff;background:{NAVY};border-radius:8px;padding:11px 22px;'
                  f'text-decoration:none;">{esc(button_text)}</a></div>')
    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:{PAGE};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{PAGE};"><tr><td align="center" style="padding:20px 12px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="width:640px;max-width:100%;font-family:Arial,Helvetica,sans-serif;">
<tr><td style="background:{NAVY};background:linear-gradient(135deg,{NAVY} 0%,{BLUE} 135%);border-radius:16px 16px 0 0;padding:24px 28px;">
  <div style="color:#fff;font-weight:700;font-size:15px;">Foxlead</div>
  <div style="color:#fff;font-size:22px;font-weight:700;margin-top:12px;">{esc(title)}</div>
  <div style="color:rgba(255,255,255,0.8);font-size:13px;margin-top:6px;">{esc(subtitle)}</div>
</td></tr>
<tr><td style="background:#fff;border:1px solid {LINE};border-top:none;border-radius:0 0 16px 16px;padding:20px;">
  {body_html}{button}
  <div style="text-align:center;font-size:12px;color:{FAINT};margin-top:16px;line-height:1.6;">
    You get this because you use Foxlead. Turn emails off in your profile: <a href="{esc(config.APP_URL)}/profile" style="color:{SOFT};">{esc(config.APP_URL)}/profile</a>
  </div>
</td></tr></table></td></tr></table></body></html>"""


def lead_card(lead):
    fg, bg = KIND.get(lead["verdict"], (SOFT, "#f1f2f5"))
    note = lead.get("note") or lead.get("reason") or ""
    meta = esc(lead["source_label"])
    if not lead["is_job"]:
        meta += f" &middot; {lead.get('comment_count', 0)} comments"
    hot = (f'<span style="font-size:11px;font-weight:700;color:{NO};background:{NO_BG};border-radius:20px;padding:3px 10px;'
           f'margin-left:6px;">HOT</span>') if lead.get("hot") else ""
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid {LINE};border-radius:12px;margin-bottom:12px;">
<tr><td style="padding:14px 16px;">
  <span style="font-family:Consolas,monospace;font-size:12px;font-weight:700;color:#fff;background:{NAVY};border-radius:6px;padding:3px 9px;">{lead["score"]}/10</span>
  <span style="font-size:11px;font-weight:700;text-transform:uppercase;color:{fg};background:{bg};border-radius:20px;padding:3px 11px;margin-left:6px;">{esc(lead["verdict"])}</span>{hot}
  <span style="font-size:12px;color:{FAINT};margin-left:8px;">{meta}</span>
  <a href="{esc(safe_link(lead["link"]))}" style="display:block;font-size:16px;font-weight:700;color:{INK};text-decoration:none;line-height:1.3;margin:10px 0 6px;">{esc(lead["title"])}</a>
  <div style="font-size:14px;color:{SOFT};line-height:1.5;">{esc(note)}</div>
</td></tr></table>"""


def send_digest(user, leads, followups):
    """Naye leads + aaj ke follow-ups ek email mein."""
    parts, text = [], []
    if leads:
        parts.append(f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:{FAINT};font-weight:700;margin:2px 2px 12px;">New leads &mdash; best first</div>')
        parts += [lead_card(l) for l in leads]
        text += [f"[{l['score']}/10] {l['verdict']} - {l['title']}\n{l['link']}" for l in leads]
    if followups:
        parts.append(f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:{FAINT};font-weight:700;margin:18px 2px 10px;">Follow-ups due today</div>')
        for f in followups:
            note = f'<div style="font-size:13px;color:{SOFT};margin-top:4px;">{esc(f["user_note"])}</div>' if f["user_note"] else ""
            parts.append(f'<div style="border-left:3px solid {WARN};padding:8px 12px;margin-bottom:10px;"><a href="{esc(safe_link(f["link"]))}" '
                         f'style="font-size:15px;font-weight:700;color:{INK};text-decoration:none;">{esc(f["title"])}</a>{note}</div>')
            text.append(f"Follow up: {f['title']}\n{f['link']}")
    if leads and followups:
        subject = f"{len(leads)} new lead{'s' if len(leads) != 1 else ''} + {len(followups)} follow-up{'s' if len(followups) != 1 else ''} — Foxlead"
    elif leads:
        subject = f"{len(leads)} new lead{'s' if len(leads) != 1 else ''} for you — Foxlead"
    else:
        subject = f"{len(followups)} follow-up{'s' if len(followups) != 1 else ''} due today — Foxlead"
    body = layout("Your Foxlead update", f"Picked for you as a {user['title']}", "".join(parts),
                  "Open your dashboard", config.APP_URL + "/dashboard")
    send(user["email"], subject, body, "Your Foxlead update\n\n" + "\n\n".join(text) + f"\n\nDashboard: {config.APP_URL}/dashboard")


def send_scan_summary(user, checked, best, threshold):
    """User ne "har scan ke baad email" chuna ho aur is scan mein koi lead na mile - chhota sa hisaab."""
    if checked:
        line = (f"Foxlead checked {checked} new post{'s' if checked != 1 else ''} for you. None was a strong enough "
                f"fit this time &mdash; the best scored {best}/10, and a lead needs {threshold}/10.")
    else:
        line = "No new posts matched your field since the last scan."
    body = (f'<p style="font-size:15px;color:{SOFT};line-height:1.6;margin:4px 2px;">{line}</p>'
            f'<p style="font-size:15px;color:{SOFT};line-height:1.6;margin:10px 2px;">Foxlead keeps scanning on your '
            f'schedule and emails you as soon as a lead turns up.</p>')
    send(user["email"], "No new leads this scan — Foxlead",
         layout("Scan finished", f"Searching for you as a {user['title']}", body, "Open your dashboard", config.APP_URL + "/dashboard"),
         f"Scan finished - no new leads.\n\n{line.replace('&mdash;', '-')}\n\nDashboard: {config.APP_URL}/dashboard")


def code_box(code):
    return (f'<div style="text-align:center;margin:18px 0 8px;"><span style="display:inline-block;font-family:Consolas,Menlo,monospace;'
            f'font-size:34px;font-weight:700;letter-spacing:10px;color:{INK};background:#f1f5fb;border:1px solid {LINE};'
            f'border-radius:12px;padding:12px 22px 12px 32px;">{esc(code)}</span></div>')


def send_verify_code(email, name, code):
    body = (f'<p style="font-size:15px;color:{INK};line-height:1.6;margin:4px 2px;">Hi {esc(name) or "there"},</p>'
            f'<p style="font-size:15px;color:{SOFT};line-height:1.6;margin:10px 2px;">Enter this code in Foxlead to confirm your email. '
            f'It works for 30 minutes.</p>' + code_box(code) +
            f'<p style="font-size:13px;color:{FAINT};line-height:1.6;margin:12px 2px;text-align:center;">If you didn\'t sign up, you can ignore this email.</p>')
    send(email, f"{code} is your Foxlead code",
         layout("Confirm your email", "Your 6-digit code", body),
         f"Hi {name or 'there'},\n\nYour Foxlead code is: {code}\n\nEnter it in Foxlead to confirm your email. It works for 30 minutes.\n\n"
         "If you didn't sign up, you can ignore this email.")


def send_reset_code(email, name, code):
    body = (f'<p style="font-size:15px;color:{INK};line-height:1.6;margin:4px 2px;">Hi {esc(name) or "there"},</p>'
            f'<p style="font-size:15px;color:{SOFT};line-height:1.6;margin:10px 2px;">Someone asked to reset the password for your Foxlead '
            f'account. Enter this code to choose a new password. It works for 15 minutes.</p>' + code_box(code) +
            f'<p style="font-size:13px;color:{FAINT};line-height:1.6;margin:12px 2px;text-align:center;">If it wasn\'t you, ignore this email — your password stays the same.</p>')
    send(email, f"{code} is your Foxlead password reset code",
         layout("Reset your password", "Your 6-digit code", body),
         f"Hi {name or 'there'},\n\nYour Foxlead password reset code is: {code}\n\nIt works for 15 minutes. "
         "If you didn't ask for this, ignore this email.")


def send_verify(email, name, url):
    body = (f'<p style="font-size:15px;color:{INK};line-height:1.6;margin:4px 2px;">Hi {esc(name) or "there"},</p>'
            f'<p style="font-size:15px;color:{SOFT};line-height:1.6;margin:10px 2px;">Please confirm this is your email so '
            f'Foxlead can send you lead alerts. The link works for 3 days.</p>')
    send(email, "Confirm your email — Foxlead",
         layout("Confirm your email", "One click and your lead alerts are on", body, "Confirm my email", url),
         f"Hi {name or 'there'},\n\nConfirm your email for Foxlead (link works for 3 days):\n{url}\n\n"
         "If you didn't sign up, you can ignore this email.")


def send_reset(email, name, url):
    body = (f'<p style="font-size:15px;color:{INK};line-height:1.6;margin:4px 2px;">Hi {esc(name) or "there"},</p>'
            f'<p style="font-size:15px;color:{SOFT};line-height:1.6;margin:10px 2px;">Someone asked to reset the password '
            f'for your Foxlead account. The link works for 1 hour. If it wasn\'t you, ignore this email — '
            f'your password stays the same.</p>')
    send(email, "Reset your password — Foxlead",
         layout("Reset your password", "This link works for 1 hour", body, "Choose a new password", url),
         f"Hi {name or 'there'},\n\nReset your Foxlead password (link works for 1 hour):\n{url}\n\n"
         "If you didn't ask for this, ignore this email.")


def send_weekly(user, title, stats, top_leads):
    """Har Monday: pichhle 7 din ka hisaab + abhi tak jin par kaam baaki hai."""
    def stat(n, label, color=INK):
        return (f'<td align="center" style="padding:14px 6px;border:1px solid {LINE};border-radius:10px;">'
                f'<div style="font-family:Consolas,monospace;font-size:22px;font-weight:700;color:{color};">{esc(str(n))}</div>'
                f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:0.6px;color:{FAINT};margin-top:3px;">{esc(label)}</div></td>')
    grid = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="6" border="0"><tr>'
            f'{stat(stats["leads"], "New leads")}{stat(stats["contacted"], "Contacted")}'
            f'{stat(stats["won"], "Won", YES)}{stat("$" + format(round(stats["earned"]), ","), "Earned", YES)}</tr></table>')
    body = grid
    if stats["followups"]:
        body += f'<p style="font-size:14px;color:{WARN};margin:14px 4px 0;"><b>{stats["followups"]} follow-up{"s" if stats["followups"] != 1 else ""} due this week.</b></p>'
    if top_leads:
        body += (f'<div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:{FAINT};font-weight:700;'
                 f'margin:18px 2px 12px;">Still waiting for you &mdash; best first</div>') + "".join(lead_card(l) for l in top_leads)
    else:
        body += f'<p style="font-size:14px;color:{SOFT};margin:16px 4px;">No open leads waiting — nice work.</p>'
    text = (f"Your Foxlead week: {stats['leads']} new leads, {stats['contacted']} contacted, {stats['won']} won, "
            f"${round(stats['earned'])} earned.\n\n" + "\n\n".join(f"[{l['score']}/10] {l['title']}\n{l['link']}" for l in top_leads)
            + f"\n\nDashboard: {config.APP_URL}/dashboard")
    n = stats["leads"]
    send(user["email"], f"Your week on Foxlead: {n} new lead{'s' if n != 1 else ''}, {stats['won']} won",
         layout("Your week on Foxlead", f"The last 7 days, as a {title}", body, "Open your dashboard", config.APP_URL + "/dashboard"),
         text)


def send_invite(email, inviter, team_name, url):
    body = (f'<p style="font-size:15px;color:{INK};line-height:1.6;margin:4px 2px;">{esc(inviter)} invited you to join '
            f'<b>{esc(team_name)}</b> on Foxlead.</p>'
            f'<p style="font-size:15px;color:{SOFT};line-height:1.6;margin:10px 2px;">You\'ll share the team\'s leads, '
            f'pipeline and notes. Log in (or sign up) with this email address, then open the link. It works for 14 days.</p>')
    send(email, f"{inviter} invited you to {team_name} on Foxlead",
         layout(f"Join {team_name}", "Your team uses Foxlead to find and win clients", body, "Join the team", url),
         f"{inviter} invited you to join {team_name} on Foxlead.\n\nOpen this link (works for 14 days):\n{url}")
