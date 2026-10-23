// sw.js - Foxlead ko phone par "app" banane wala service worker.
// Sirf design ki files (CSS/JS/icons) phone par rakhta hai - leads/data KABHI nahi
// (wo private hain, aur hamesha server se taaza aane chahiye).
const CACHE = "foxlead-shell-v1";
const SHELL = [
  "/offline",
  "/static/foxlead.css", "/static/dashboard.css",
  "/static/dashboard.js", "/static/chat.js", "/static/profile.js",
  "/static/icons/icon-192.png", "/static/icons/icon-512.png",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  // design files: pehle server se (taaza), na mile to phone wali copy
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(req, copy));
      return res;
    }).catch(() => caches.match(req)));
    return;
  }
  // pages: internet na ho to "offline" page (data kabhi cache nahi hota)
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("/offline")));
  }
});
