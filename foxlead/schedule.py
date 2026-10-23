# foxlead/schedule.py
# Auto-scan ka waqt. Har user khud chunta hai: har 1 / 3 / 6 / 12 / 24 ghante, ya band.
# 24 ghante par "kis baje" bhi (user ke apne time zone mein, jaise subah 9 baje).
# Plan se tez nahi: Free plan par sab se tez din mein ek baar.

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import plans

GRACE = timedelta(minutes=2)      # scheduler har minute dekhta hai - thoda pehle bhi chala do


def user_tz(user):
    try:
        return ZoneInfo(user["timezone"]) if user["timezone"] else timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def valid_tz(name):
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def every_hours(user, profile):
    """Kitne ghante baad auto-scan. 0 = band. Kuch na chuna ho to plan ka default."""
    floor = plans.limits(user)["scan_every_hours"]
    chosen = profile["scan_every"]
    if chosen is None:
        return floor
    return 0 if chosen == 0 else max(chosen, floor)


def _parse(iso):
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def next_scan(user, profile, last_run, now=None):
    """Agla auto-scan kab (UTC). None = auto-scan band. Waqt guzar chuka ho to wahi purana waqt (yani abhi)."""
    now = now or datetime.now(timezone.utc)
    every = every_hours(user, profile)
    if not every:
        return None
    last = _parse(last_run)
    hour = profile["scan_hour"]
    if every >= 24 and hour is not None:
        tz = user_tz(user)
        local = now.astimezone(tz)
        slot = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        if slot > local:
            slot -= timedelta(days=1)                       # aaj ka waqt abhi nahi aaya - pichhla (kal ka) slot
        if last is None or last < slot.astimezone(timezone.utc):
            return slot.astimezone(timezone.utc)            # ye slot abhi chala nahi
        return (slot + timedelta(days=1)).astimezone(timezone.utc)
    return now if last is None else last + timedelta(hours=every)


def is_due(user, profile, last_run, now=None):
    now = now or datetime.now(timezone.utc)
    nxt = next_scan(user, profile, last_run, now)
    return nxt is not None and nxt <= now + GRACE
