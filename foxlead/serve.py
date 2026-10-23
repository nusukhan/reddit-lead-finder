# foxlead/serve.py
# Dosto/users ke liye app chalana (internet par link ke peeche): waitress server + auto-scan scheduler.
#   python -m foxlead.serve                (port 5000)
# Link ke peeche (Cloudflare Tunnel / hosting) ho to .env ya environment mein:
#   FOXLEAD_BEHIND_PROXY=1   APP_URL=https://aapka-link     (emails mein sahi link jaye)

import os

from waitress import serve

from .web import app, start_scheduler

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    start_scheduler()
    print(f"Foxlead running on http://127.0.0.1:{port}  (auto-scan on)", flush=True)
    serve(app, host="127.0.0.1", port=port, threads=8)
