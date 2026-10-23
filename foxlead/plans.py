# foxlead/plans.py
# Kis user ka kaunsa plan hai, aur us plan ki hadein kya hain.
# Pro: Stripe se pay kiya, ya admin ne diya, ya kisi Pro agency team ka member hai.

from . import config, db


def plan_of(user):
    """'free' ya 'pro'. Admin hamesha pro; team member ko owner ka plan milta hai."""
    if user["email"].lower() in config.ADMIN_EMAILS:
        return "pro"
    if user["plan"] == "pro":
        return "pro"
    if user["team_id"]:
        with db.connect() as conn:
            owner = conn.execute("SELECT u.plan, u.email FROM teams t JOIN users u ON u.id = t.owner_id WHERE t.id = ?",
                                 (user["team_id"],)).fetchone()
        if owner and (owner["plan"] == "pro" or owner["email"].lower() in config.ADMIN_EMAILS):
            return "pro"
    return "free"


def limits(user):
    return config.PLANS[plan_of(user)]


def stripe_ready():
    return bool(config.STRIPE_SECRET_KEY and config.STRIPE_PRICE_PRO)
