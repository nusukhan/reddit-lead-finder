# test_jobfeeds.py
# Maqsad: LaraJobs aur We Work Remotely ki RSS try karo - chalti hai ya nahi?
# Agar chaleen, to inhe system mein job sources ki tarah jod denge.
 
import requests
import xml.etree.ElementTree as ET
 
headers = {"User-Agent": "lead-finder by Nusu"}
 
# RSS feeds jo test karni hain
feeds = {
    "LaraJobs": "https://larajobs.com/feed",
    "WeWorkRemotely (Programming)": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "WeWorkRemotely (Full-Stack)": "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
}
 
for name, url in feeds.items():
    print(f"\n{'='*55}")
    print(f"{name}")
    print(f"{url}")
    try:
        r = requests.get(url, headers=headers, timeout=20)
        print(f"status code: {r.status_code}")
        if r.status_code != 200:
            print("  -> nahi chali")
            continue
 
        root = ET.fromstring(r.content)
 
        # Yeh feeds "RSS" format mein hoti hain (Reddit se thoda alag).
        # RSS mein posts <item> ke andar hoti hain (Reddit mein <entry> thi).
        items = root.findall(".//item")
        print(f"  -> {len(items)} jobs mile. Pehle 5:")
        for item in items[:5]:
            title_el = item.find("title")
            link_el = item.find("link")
            title = title_el.text if title_el is not None else "(no title)"
            link = link_el.text if link_el is not None else ""
            print(f"     - {title}")
            print(f"       {link}")
    except Exception as e:
        print(f"  -> ERROR: {e}")
 