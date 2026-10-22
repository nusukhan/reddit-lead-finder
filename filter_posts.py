# filter_posts.py
# Maqsad: posts.json se posts parho aur SIRF woh rakho jinmein Umar bhai ke
# kaam ke keywords hain. Yeh "sasta filter" hai (LLM se pehle).

import json

# --- Umar bhai ke kaam ke keywords (sab chhote letters mein) ---
# Add/remove karna aasaan hai.
keywords = [
    "multi-tenant", "multi tenant", "tenant isolation", "saas boilerplate",
    "white-label", "white label",
    "stripe", "subscription", "recurring billing", "installment",
    "refund", "failed payment", "proration",
    "laravel", "spatie", "inertia", "queue", "livewire",
    "pusher", "firebase", "websocket", "real-time", "realtime",
    "multi-tenancy", "scaling", "scale",
    "hire a developer", "technical co-founder", "technical cofounder",
    "need a developer", "looking for a developer", "build my saas",
    "mvp", "saas architecture",
]

# --- posts.json file se saari posts load karo ---
with open("posts.json", "r", encoding="utf-8") as f:
    all_posts = json.load(f)

print(f"posts.json se {len(all_posts)} posts load hueen.\n")

# --- Yahan chuni hui posts jama hongi ---
matched_posts = []

# --- Har post ko check karo ---
for post in all_posts:
    # title aur text ko jod kar ek bada text banao, sab chhote letters mein
    # (taake "Stripe" aur "stripe" dono match ho jayein)
    haystack = (post["title"] + " " + post["text"]).lower()

    # dekho is post mein kaunse keywords mile
    found = []
    for kw in keywords:
        if kw in haystack:
            found.append(kw)

    # agar koi bhi keyword mila -> yeh post rakho
    if found:
        post["matched_keywords"] = found   # post mein likh do kaunse mile
        matched_posts.append(post)

# --- Nateeja dikhao ---
print(f"==> {len(matched_posts)} posts match hueen (keywords mile)\n")
print("=" * 50)

for post in matched_posts:
    print(f"\n[r/{post['subreddit']}] {post['title']}")
    print(f"  Keywords mile: {', '.join(post['matched_keywords'])}")
    print(f"  {post['link']}")

# --- Chuni hui posts ek nayi file mein save karo (agle hisse ke liye) ---
with open("matched_posts.json", "w", encoding="utf-8") as f:
    json.dump(matched_posts, f, ensure_ascii=False, indent=2)

print("\n" + "=" * 50)
print(f"\nChuni hui {len(matched_posts)} posts 'matched_posts.json' mein save ho gayeen.")