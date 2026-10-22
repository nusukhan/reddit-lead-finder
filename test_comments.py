 #test_comments.py
# Maqsad: ek lead (post) ke COMMENTS parho - RSS se.
# Agar yeh chala, to hum top leads ke comments bhi dekh sakenge.
 
import json
import requests
import xml.etree.ElementTree as ET
 
headers = {"User-Agent": "lead-finder by Nusu"}
ns = {"atom": "http://www.w3.org/2005/Atom"}
 
# --- leads.json se pehli lead uthao (test ke liye) ---
with open("leads.json", "r", encoding="utf-8") as f:
    leads = json.load(f)
 
if not leads:
    print("leads.json khaali hai. Pehle classify_posts.py chalao.")
    exit()
 
lead = leads[0]   # pehli (top) lead
print(f"Test lead: {lead['title']}")
print(f"Link: {lead['link']}\n")
 
# --- Post ke comments ka RSS address ---
# Post link ke aage ".rss" lagane se us post ke comments milte hain
comments_url = lead["link"].rstrip("/") + ".rss"
print(f"Comments maang rahe hain...\n")
 
response = requests.get(comments_url, headers=headers)
print(f"status code: {response.status_code}\n")
 
if response.status_code == 200:
    root = ET.fromstring(response.content)
    entries = root.findall("atom:entry", ns)
 
    # pehli entry khud post hoti hai, baaki comments
    print(f"Mili {len(entries)} entries (1 post + baaki comments):\n")
 
    for i, entry in enumerate(entries):
        content_el = entry.find("atom:content", ns)
        text = content_el.text if content_el is not None else ""
        # HTML tags hata kar sirf text (mota-mota)
        import re
        clean = re.sub("<[^>]+>", " ", text or "")
        clean = " ".join(clean.split())[:200]   # pehle 200 akshar
        label = "POST" if i == 0 else f"Comment {i}"
        print(f"[{label}] {clean}\n")
else:
    print("Comments nahi mile. Status code upar dekho.")
    print("429 = ruk kar try karo. 403 = Reddit ne mana kiya.")
 