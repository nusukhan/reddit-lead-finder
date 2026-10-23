// dashboard.js - Foxlead dashboard. Data server se aata hai (/api/data), sirf
// logged-in user ka. Lead ka status (Replied / Won...) server par save hota hai.
//
// ZAROORI: lead ke title/text Reddit se aate hain (koi bhi kuch bhi likh sakta hai),
// isliye sab kuch textContent se dikhaya jata hai - HTML ki tarah kabhi nahi.

const DAY = 86400000;
// tarjume: t("English jumla", {naam: value}) -> user ki zubaan mein (Urdu na mile to English)
const I18N = JSON.parse(document.getElementById("i18n")?.textContent || "{}");
function t(s, vars) { let out = I18N[s] || s; for (const k in vars || {}) out = out.split("{" + k + "}").join(vars[k]); return out; }
const CSRF = document.querySelector('meta[name="csrf-token"]').content;

const SRC = {
  reddit:   { name: "Reddit",           short: "R",  c1: "#e8803a", c2: "#f5a85f" },
  larajobs: { name: "LaraJobs",         short: "LJ", c1: "#38b2a8", c2: "#5fd3c8" },
  wwr:      { name: "We Work Remotely", short: "W",  c1: "#9a7cf0", c2: "#b9a3f7" },
  other:    { name: "Job board",        short: "J",  c1: "#5a6472", c2: "#7a8699" },
};
const SRC_ORDER = ["larajobs", "wwr", "reddit", "other"];
const VCLASS = { Apply: "apply", Reply: "reply", Maybe: "maybe", Review: "maybe", Skip: "skip" };
const STATUS_LIST = [["new", "New"], ["replied", "Replied"], ["applied", "Applied"], ["talking", "Talking"],
                     ["won", "Won"], ["lost", "Lost"], ["skipped", "Skipped"]];
const STATUS_PILL = { replied: ["reply", "Replied"], applied: ["apply", "Applied"], talking: ["maybe", "Talking"],
                      won: ["apply", "Won"], lost: ["skip", "Lost"], skipped: ["skip", "Skipped"] };
const IN_MOTION = ["replied", "applied", "talking"];          // jin par kaam chal raha hai
// pipeline board ke columns (drop karne par lead ka naya status = target)
const BOARD = [
  { key: "new", label: "New", has: ["new"], target: () => "new", dot: "var(--faint)" },
  { key: "contacted", label: "Contacted", has: ["replied", "applied"], target: l => l.is_job ? "applied" : "replied", dot: "var(--reply)" },
  { key: "talking", label: "Talking", has: ["talking"], target: () => "talking", dot: "var(--maybe)" },
  { key: "won", label: "Won", has: ["won"], target: () => "won", dot: "var(--apply)" },
  { key: "lost", label: "Lost", has: ["lost", "skipped"], target: () => "lost", dot: "var(--skip)" },
];
const money = n => "$" + Math.round(n || 0).toLocaleString();
const RUN_STATUS = {
  emailed: ["apply", "Emailed leads"], found: ["apply", "Found leads"], no_leads: ["muted", "No strong leads"],
  no_new: ["muted", "Nothing new"], fetch_failed: ["skip", "Fetch failed"], score_failed: ["skip", "Scoring failed"],
  email_failed: ["skip", "Email failed"],
};
const RUN_OK = new Set(["emailed", "found", "no_leads", "no_new"]);
const EMPTY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';

// ---------- helpers (text hamesha text node banta hai, HTML kabhi nahi) ----------
function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else n.setAttribute(k, v);
  }
  for (const k of kids) if (k != null && k !== false) n.append(k);
  return n;
}
function svg(tag, attrs) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  return n;
}
const $ = id => document.getElementById(id);
function safeUrl(u) { return /^https?:\/\//i.test(u || "") ? u : "#"; }
function sourceKey(l) {
  const s = (l.source || "").toLowerCase();
  if (s.startsWith("r/")) return "reddit";
  if (s === "larajobs") return "larajobs";
  if (s.startsWith("wwr")) return "wwr";
  return "other";
}
function initials(t) {
  const w = (t || "").replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean);
  return ((w[0] || "?")[0] + (w[1] ? w[1][0] : "")).toUpperCase();
}
function ago(ms) {
  const m = Math.round((Date.now() - ms) / 60000);
  if (m < 1) return t("just now");
  if (m < 60) return t("{n} min ago", { n: m });
  const h = Math.round(m / 60);
  if (h < 48) return t("{n}h ago", { n: h });
  return t("{n} days ago", { n: Math.round(h / 24) });
}
const LOCALE = document.documentElement.lang === "ur" ? "ur-PK" : undefined;   // Urdu mein tareekh bhi Urdu mein
const fmtDay = d => d.toLocaleDateString(LOCALE, { month: "short", day: "numeric" });
const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
function startOfDay(offsetDays) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - offsetDays); return d.getTime(); }
async function api(path, body) {
  const res = await fetch(path, body === undefined ? { credentials: "same-origin" } : {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF }, body: JSON.stringify(body),
  });
  if (res.status === 401) { location.href = "/login"; throw new Error("logged out"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || t("Something went wrong ({code})", { code: res.status }));
  return data;
}
// kind: "ok" = hara (kamyabi), "err" = laal (ghalti), "info" = neela
function toast(msg, actionLabel, onAction, kind = "info") {
  const t = $("toast"), btn = $("toast-action");
  $("toast-text").textContent = msg || "";
  t.className = "toast " + kind;
  t.setAttribute("role", kind === "err" ? "alert" : "status");
  t.hidden = !msg;
  btn.hidden = !actionLabel;
  btn.textContent = actionLabel || "";
  btn.onclick = actionLabel ? () => { t.hidden = true; onAction(); } : null;
  clearTimeout(toast.timer);
  if (msg) toast.timer = setTimeout(() => { t.hidden = true; }, actionLabel ? 9000 : 6000);
}

// ---------- state ----------
let PROFILE = null, WINDOW = null, leads = [], runs = [], scanning = false, DRAFTS = { used: 0, limit: 30 };
let ME = { id: null }, TEAM = [];   // team ke log (lead assign karne ke liye)
const state = { screen: "leads", range: 30, chip: "apply", sort: "new", q: "", open: null };   // default: Apply leads, nayi pehle

const statusOf = l => l.status || "new";
const statusTime = l => l.status_at ? new Date(l.status_at).getTime() : 0;
const rangeStart = () => state.range ? startOfDay(state.range - 1) : 0;
const inRange = l => l.ms >= rangeStart();
const isTodo = l => statusOf(l) === "new" && (l.verdict === "Apply" || l.verdict === "Reply");
function localISO(d) { return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
const todayISO = () => localISO(new Date());
const isDue = l => !!l.remind_at && l.remind_at <= todayISO();           // follow-up ka din aa gaya (ya guzar gaya)
const fmtISODay = iso => fmtDay(new Date(iso + "T00:00:00"));

async function load() {
  const d = await api("/api/data");
  PROFILE = d.profile;
  WINDOW = d.window;
  DRAFTS = d.drafts;
  ME = d.user; TEAM = d.team || [];
  // ms = Foxlead ne kab dhoondi (date range/charts); posted = post asal mein kab hui (dikhane + sort ke liye)
  leads = d.leads.map(l => ({ ...l, ms: new Date(l.found_at).getTime(), posted: new Date(l.posted_at || l.found_at).getTime(), src: sourceKey(l) }))
    .sort((a, b) => b.ms - a.ms || (b.score || 0) - (a.score || 0));
  runs = d.runs.map(r => ({ ...r, ms: new Date(r.time).getTime() })).sort((a, b) => b.ms - a.ms);
  const wasScanning = scanning;
  scanning = d.scan.running;
  if (wasScanning && !scanning) toast(t("Scan finished."), null, null, "ok");
  renderAll();
  if (scanning) setTimeout(() => load().catch(e => toast(e.message, null, null, "err")), 8000);   // scan chal raha hai - thodi der mein dobara dekho
}
// lead badlo: pehle screen par (foran), phir server par; server mana kare to wapas
async function updateLead(l, local, body) {
  const before = Object.fromEntries(Object.keys(local).map(k => [k, l[k]]));
  Object.assign(l, local);
  renderAll();
  try { await api("/api/lead", { id: l.id, ...body }); return true; }
  catch (e) { Object.assign(l, before); renderAll(); toast(t("Could not save: {e}", { e: e.message }), null, null, "err"); return false; }
}
function setStatus(l, s) {
  return updateLead(l, { status: s, status_at: s === "new" ? null : new Date().toISOString() }, { status: s });
}
async function hideLead(l) {
  closeLead();
  const idx = leads.indexOf(l);
  leads.splice(idx, 1);
  renderAll();
  try { await api("/api/lead", { id: l.id, feedback: "not_relevant" }); }
  catch (e) { leads.splice(idx, 0, l); renderAll(); toast(t("Could not hide: {e}", { e: e.message }), null, null, "err"); return; }
  toast(t("Hidden. Foxlead will show fewer posts like this."), t("Undo"), async () => {
    try { await api("/api/lead", { id: l.id, feedback: "" }); leads.splice(idx, 0, l); renderAll(); }
    catch (e) { toast(t("Could not undo: {e}", { e: e.message }), null, null, "err"); }
  }, "ok");
}

// ---------- building blocks ----------
function avatar(l, big) {
  const c = l.verdict === "Skip" ? ["#5a6472", "#7a8699"] : [SRC[l.src].c1, SRC[l.src].c2];
  return el("span", { class: "avatar", style: `background:linear-gradient(140deg,${c[0]},${c[1]})` + (big ? ";width:40px;height:40px;border-radius:10px;font-size:0.9rem" : "") }, initials(l.title));
}
function feedLabel(key) { return (PROFILE?.feeds.find(f => f.key === key) || {}).label; }
function srcName(l) {
  if (l.src === "reddit") return l.source;
  return feedLabel(l.source) || SRC[l.src].name;
}
function srcBadge(l) {
  const s = SRC[l.src];
  return el("span", { class: "srcbadge" }, el("span", { class: "sq", style: "background:" + s.c1 }, s.short), l.src === "wwr" ? s.name : t(srcName(l)));
}
function scoreBadge(l) { return el("span", { class: "score" + ((l.score || 0) >= 9 ? " hi" : "") }, (l.score ?? "?") + "/10"); }
// NEW: pichhle scan ke baad mili lead (jo abhi tak kholi/chhui nahi)
const isNew = l => statusOf(l) === "new" && runs.length > 0 && l.ms > (runs[1] ? runs[1].ms : 0);
function verdictPill(l) {
  const v = el("span", { class: "pill " + (VCLASS[l.verdict] || "muted") }, t(l.verdict || "Review"));
  const extra = [];
  // HOT: bilkul nayi post, abhi koi reply nahi - sabse pehle jawab do
  if (l.hot) extra.push(el("span", { class: "pill skip", title: t("Brand-new post with almost no replies yet — reply first") }, t("HOT")));
  if (isNew(l)) extra.push(el("span", { class: "pill reply", title: t("Found in the latest scan") }, t("NEW")));
  return extra.length ? el("span", { style: "display:inline-flex;gap:6px;align-items:center" }, v, ...extra) : v;
}
function compCell(l) {
  const c = (l.competition || "").toLowerCase();
  const cls = ["low", "medium", "high"].includes(c) ? c : "na";
  return el("span", { class: "comp " + cls }, t(cls === "na" ? "n/a" : c));
}
function subLine(l) {
  const parts = [srcName(l)];
  if (!l.is_job) parts.push(t("{n} comments", { n: l.comment_count || 0 }));
  parts.push(t("posted {ago}", { ago: ago(l.posted) }));
  const st = statusOf(l);
  if (st !== "new") parts.push(t(STATUS_PILL[st][1]));
  if (l.assigned_to && TEAM.length > 1) {
    const who = TEAM.find(m => m.id === l.assigned_to);
    if (who) parts.push("→ " + (who.id === ME.id ? t("you") : who.name));
  }
  const text = parts.join(" · ");
  if (!l.remind_at) return text;
  // follow-up: aaj/guzar gaya to peela, warna sirf tareekh
  return isDue(l) ? [text + " · ", el("span", { class: "due" }, t(l.remind_at < todayISO() ? "Follow up overdue" : "Follow up today"))]
                  : text + " · " + t("follow-up {date}", { date: fmtISODay(l.remind_at) });
}
function leadCell(l, sub) {
  return el("div", { class: "lead-cell" }, avatar(l),
    el("div", { style: "min-width:0" }, el("div", { class: "lead-title", dir: "auto" }, l.title || t("(no title)")),
      el("div", { class: "lead-sub" }, ...[].concat(sub))));
}
function clickRow(l, cells) {
  const tr = el("tr", { class: "click" + (statusOf(l) !== "new" ? " done" : "") + (state.open === l.id ? " sel" : ""), tabindex: "0" },
    ...cells.map(c => el("td", {}, c)));
  tr.addEventListener("click", () => openLead(l));
  tr.addEventListener("keydown", e => { if (e.key === "Enter") openLead(l); });
  return tr;
}
function emptyRow(cols, title, text, extra) {
  const box = el("div", { class: "empty" });
  box.innerHTML = EMPTY_ICON;   // sirf fixed icon - koi data nahi
  box.append(el("h3", {}, title), el("p", {}, text));
  if (extra) box.append(extra);
  return el("tr", {}, el("td", { colspan: cols, style: "border:0" }, box));
}
function statCard(title, value, note, color) {
  return el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", {}, title)),
    el("div", { class: "bignum", style: color ? "color:" + color : "" }, value), el("div", { class: "note" }, note));
}
function trendEl(node, cur, prev) {
  if (!prev) { node.textContent = ""; return; }
  const p = Math.round((cur - prev) / prev * 100);
  node.textContent = (p >= 0 ? "▲ " : "▼ ") + Math.abs(p) + "%";
  node.className = "trend" + (p < 0 ? " down" : "");
  node.title = t("vs the previous period");
}

// line charts ke liye din (ya lambi range ke liye hafte)
function makeBuckets(rangeDays) {
  const oldest = leads.length ? Math.min(...leads.map(l => l.ms)) : Date.now();
  const days = rangeDays || Math.max(28, Math.ceil((Date.now() - oldest) / DAY) + 1);
  const size = days <= 31 ? 1 : 7;
  const n = Math.min(Math.ceil(days / size), 52);
  const list = [];
  for (let i = n - 1; i >= 0; i--) list.push({ start: startOfDay(i * size + size - 1), end: startOfDay(i * size - 1) });
  return { list, size };
}
function countIn(buckets, times) { return buckets.list.map(b => times.filter(t => t >= b.start && t < b.end).length); }
function axisLabels(node, buckets) {
  const n = buckets.list.length;
  const idx = n <= 7 ? [...Array(n).keys()] : [0, Math.round((n - 1) / 3), Math.round(2 * (n - 1) / 3), n - 1];
  node.replaceChildren(...idx.map(i => {
    const d = new Date(buckets.list[i].start);
    return el("span", {}, buckets.size === 1 && n <= 7 ? d.toLocaleDateString(LOCALE, { weekday: "short" }) : fmtDay(d));
  }));
}
let gradId = 0;
function lineChart(box, buckets, series, H) {
  const W = Math.max(box.clientWidth, 240), n = buckets.list.length;
  const max = Math.max(1, ...series.flatMap(s => s.values));
  const top = 12, bottom = H - 4;
  const x = i => n === 1 ? W / 2 : 5 + i * (W - 10) / (n - 1);
  const y = v => bottom - (v / max) * (bottom - top);
  const root = svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": t("{names} over time", { names: series.map(s => s.name).join(t(" and ")) }) });
  [0.25, 0.55, 0.85].forEach(f => root.append(svg("line", { x1: 0, x2: W, y1: H * f, y2: H * f, stroke: "#18202e" })));
  series.forEach(s => {
    const pts = s.values.map((v, i) => [x(i), y(v)]);
    const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
    if (s.area) {
      const id = "g" + (++gradId);
      const defs = svg("defs", {}), lg = svg("linearGradient", { id, x1: 0, y1: 0, x2: 0, y2: 1 });
      lg.append(svg("stop", { offset: "0%", "stop-color": s.color, "stop-opacity": 0.34 }), svg("stop", { offset: "100%", "stop-color": s.color, "stop-opacity": 0 }));
      defs.append(lg); root.append(defs);
      root.append(svg("path", { d: `${line} L${x(n - 1)},${H} L${x(0)},${H} Z`, fill: `url(#${id})` }));
    }
    root.append(svg("path", { d: line, fill: "none", stroke: s.color, "stroke-width": 2.4, "stroke-linecap": "round", "stroke-linejoin": "round" }));
    const last = pts[pts.length - 1];
    root.append(svg("circle", { cx: last[0], cy: last[1], r: 4.5, fill: s.color, stroke: "#141a26", "stroke-width": 2.5 }));
  });
  buckets.list.forEach((b, i) => {
    const w = n === 1 ? W : W / (n - 1);
    const hit = svg("rect", { x: x(i) - w / 2, y: 0, width: w, height: H, fill: "transparent" });
    const t = svg("title", {});
    const label = buckets.size === 1 ? fmtDay(new Date(b.start)) : t("Week of {date}", { date: fmtDay(new Date(b.start)) });
    t.textContent = label + "\n" + series.map(s => s.name + ": " + s.values[i]).join("\n");
    hit.append(t); root.append(hit);
  });
  box.replaceChildren(root);
}

// ---------- rail + topbar ----------
function renderChrome() {
  const last = runs[0];
  const ok = last && RUN_OK.has(last.status);
  const dotCls = scanning ? "dot busy" : !last ? "dot idle" : ok ? "dot" : "dot bad";
  $("engine-dot").className = dotCls;
  $("engine-big").textContent = last ? String(last.fetched ?? 0) : "—";
  $("engine-sub").textContent = scanning ? t("scanning now…") : last ? t("posts checked last scan · {ago}", { ago: ago(last.ms) }) : t("waiting for the first scan");
  $("c-leads").textContent = leads.filter(inRange).length;
  $("c-sources").textContent = PROFILE ? (PROFILE.subreddits.length ? 1 : 0) + PROFILE.feeds.length : "";
  $("c-replies").textContent = leads.filter(l => IN_MOTION.includes(statusOf(l))).length;
  $("c-pipeline").textContent = leads.filter(l => statusOf(l) === "talking").length || "";
  $("c-won").textContent = leads.filter(l => statusOf(l) === "won").length;
  const todo = leads.filter(isTodo).length, due = leads.filter(isDue).length;
  const bell = todo + due;
  $("bell-badge").hidden = !bell;
  $("bell-badge").textContent = bell > 99 ? "99+" : bell;
  $("bell").title = t("{todo} to act on · {due} follow-ups due", { todo, due });
  $("live-dot").className = dotCls;
  $("live-text").textContent = scanning ? t("Scanning…") : last && !ok ? t("Last scan: {s}", { s: t((RUN_STATUS[last.status] || ["", last.status])[1]) })
    : t("Next scan in ~{n} min", { n: 60 - new Date().getMinutes() });
  $("foot-dot").className = dotCls;
  $("foot-text").textContent = scanning ? t("Scanning for new leads…") : last ? t(ok ? "Engine live · last scan {ago}" : "Engine needs a look · last scan {ago}", { ago: ago(last.ms) }) : t("No scans yet");
  const scanBtn = $("scan");
  scanBtn.disabled = scanning;
  scanBtn.querySelector("span").textContent = t(scanning ? "Scanning…" : "Scan now");
  if (PROFILE) $("leads-sub").replaceChildren(t("Fresh posts scored for you as a {title} — newest on top.", { title: t(PROFILE.title) }),
    ...(ME.member ? [] : [" ", el("a", { href: "/profile", class: "field-link" }, t("Change field"))]));
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("on", b.dataset.s === state.screen));
  document.querySelectorAll(".screen").forEach(s => s.classList.toggle("on", s.id === "s-" + state.screen));
}

// ---------- leads ----------
function chipOk(l) {
  switch (state.chip) {
    case "all": return true;
    case "todo": return isTodo(l);
    case "due": return isDue(l);
    case "mine": return l.assigned_to === ME.id;
    case "reddit": return l.src === "reddit";
    case "jobs": return l.src !== "reddit";
    default: return VCLASS[l.verdict] === state.chip;
  }
}
function renderLeads() {
  const ranged = leads.filter(inRange);
  const label = state.range ? t("{n} days", { n: state.range }) : t("all time");
  $("found-title").textContent = t("Leads found · {label}", { label });
  $("found-num").textContent = ranged.length;
  const prev = state.range ? leads.filter(l => l.ms >= startOfDay(2 * state.range - 1) && l.ms < rangeStart()).length : 0;
  trendEl($("found-trend"), ranged.length, prev);
  const b = makeBuckets(state.range);
  lineChart($("found-chart"), b, [{ name: t("Leads"), color: "#3d82f6", area: true, values: countIn(b, leads.map(l => l.ms)) }], 96);
  axisLabels($("found-axis"), b);

  const counts = Object.fromEntries(SRC_ORDER.map(k => [k, ranged.filter(l => l.src === k).length]));
  // sirf user ke apne sources (profile mein) ya jin se leads aayi hon
  const mine = new Set((PROFILE?.subreddits.length ? ["reddit"] : []).concat(
    (PROFILE?.feeds || []).map(f => f.key === "larajobs" ? "larajobs" : f.key.startsWith("wwr") ? "wwr" : "other")));
  const shown = SRC_ORDER.filter(k => mine.has(k) || counts[k]);
  const maxC = Math.max(1, ...Object.values(counts));
  $("by-source").replaceChildren(...shown.map(k => el("div", { class: "bar-row" },
    el("span", { class: "lab", title: t(SRC[k].name) }, k === "wwr" ? "We Work Rem." : t(SRC[k].name)),
    el("div", { class: "bar-track" }, el("div", { class: "bar-fill", style: `width:${counts[k] / maxC * 100}%;background:${SRC[k].c1}` })),
    el("span", { class: "num" }, String(counts[k])))));

  const worth = ranged.filter(l => l.verdict === "Apply" || l.verdict === "Reply").length;
  const p = pct(worth, ranged.length);
  const ring = svg("svg", { width: 54, height: 54, viewBox: "0 0 36 36", role: "img", "aria-label": t("{p} percent worth acting on", { p }), style: "flex:0 0 auto" });
  ring.append(svg("circle", { cx: 18, cy: 18, r: 15.5, fill: "none", stroke: "#1a2230", "stroke-width": 4 }));
  if (p > 0) ring.append(svg("circle", { cx: 18, cy: 18, r: 15.5, fill: "none", stroke: "#35c08a", "stroke-width": 4, "stroke-linecap": "round", "stroke-dasharray": `${(p / 100 * 97.4).toFixed(1)} 97.4`, transform: "rotate(-90 18 18)" }));
  const txt = svg("text", { x: 18, y: 21, "text-anchor": "middle", fill: "#eef2f8", "font-size": 9, "font-weight": 700, "font-family": "monospace" });
  txt.textContent = p + "%"; ring.append(txt);
  $("hit-rate").replaceChildren(ring, el("div", {},
    el("div", { class: "bignum", style: "color:var(--apply);font-size:1.3rem" }, worth + "/" + ranged.length),
    el("div", { style: "font-size:0.74rem;color:var(--soft)" }, t("worth applying or replying"))));

  const scores = [6, 7, 8, 9, 10].filter(s => s >= (PROFILE?.threshold ?? 7) || ranged.some(l => l.score === s));
  const sc = scores.map(s => ranged.filter(l => (l.score || 0) === s).length);
  const maxS = Math.max(1, ...sc), top = Math.max(...sc);
  $("spread").replaceChildren(...scores.map((s, i) => el("div", { class: "col" + (sc[i] && sc[i] === top ? " hot" : ""), title: t("{n} leads scored {s}", { n: sc[i], s }) },
    el("div", { class: "b", style: `height:${sc[i] / maxS * 82}%` }), el("span", { class: "cl" }, String(s)))));
  const note = $("spread-note");
  if (ranged.length) {
    const [before, after] = t("Most leads land {score} in this period.").split("{score}");
    note.replaceChildren(before, el("strong", { style: "color:var(--ink)" }, scores[sc.indexOf(top)] + "/10"), after);
  } else note.textContent = t("No leads in this period yet.");

  // "Newest": jo post sab se nayi hui wo upar · "Top score": sabse zyada score upar (barabar ho to nayi pehle)
  const q = state.q.trim().toLowerCase();
  // follow-ups purani leads ke bhi ho sakte hain - un par date range nahi lagti
  const pool = state.chip === "due" ? leads : ranged;
  const list = pool.filter(l => chipOk(l) && (!q || [l.title, l.note, l.source, l.reason, l.user_note].join(" ").toLowerCase().includes(q)))
    .sort(state.sort === "new" ? (a, b) => b.posted - a.posted || (b.score || 0) - (a.score || 0)
                                 : (a, b) => (b.score || 0) - (a.score || 0) || b.posted - a.posted);
  document.querySelectorAll("#filters .chip").forEach(c => c.classList.toggle("on", c.dataset.f === state.chip));
  $("result").textContent = t(list.length === 1 ? "{n} lead" : "{n} leads", { n: list.length });
  $("showing").textContent = state.chip === "due" ? t("Showing {n} follow-ups due", { n: list.length })
    : t("Showing {n} of {total} leads · {range}", { n: list.length, total: ranged.length, range: state.range ? t("last {label}", { label }) : label });
  const body = $("tbody");
  if (!leads.length && !scanning && WINDOW && WINDOW.checked) {
    // scan hua par koi lead nahi - saaf batao kyun, aur zyada din ka rasta dikhao
    const more = WINDOW.days < 7 && !ME.member
      ? el("p", { style: "margin-top:10px" }, el("a", { href: "/profile", class: "field-link" }, t("Look back 7 days instead (Field & profile → Step 4)"))) : null;
    body.replaceChildren(emptyRow(5, t("No leads in the last {days} days", { days: WINDOW.days }),
      t("Foxlead checked {n} posts that match your field. The best scored {best}/10 — a lead needs {bar}/10. Every scan checks the newest posts.",
        { n: WINDOW.checked, best: WINDOW.best, bar: PROFILE.threshold }), more));
  } else if (!leads.length) body.replaceChildren(emptyRow(5, t(scanning ? "Scanning…" : "No leads yet"),
    t(scanning ? "Foxlead is checking Reddit and job boards for you right now." : "Press “Scan now”, or wait for the hourly scan. Leads that fit your profile show up here.")));
  else if (!list.length) body.replaceChildren(emptyRow(5, t("Nothing matches"), t("Try another filter, a longer date range, or clear the search.")));
  else body.replaceChildren(...list.map(l => clickRow(l, [leadCell(l, subLine(l)), scoreBadge(l), srcBadge(l), compCell(l), verdictPill(l)])));
}

// ---------- sources ----------
function renderSources() {
  if (!PROFILE) return;
  const since = startOfDay(29);
  const n30 = test => leads.filter(l => test(l) && l.ms >= since).length;
  const card = (k, name, status, kws, count) => el("div", { class: "srccard" },
    el("div", { class: "top" }, el("span", { class: "ic", style: "background:" + SRC[k].c1 }, SRC[k].short),
      el("div", {}, el("div", { class: "nm" }, name), el("div", { class: "st" }, el("span", { class: "dot" }), status))),
    el("div", { class: "kwrow" }, ...kws.map(w => el("span", { class: "kw" }, w))),
    el("div", { class: "meta" }, el("span", {}, t("Leads · last 30 days")), el("b", {}, String(count))));
  const cards = [];
  if (PROFILE.subreddits.length)
    cards.push(card("reddit", "Reddit", t("Active · {n} subreddits", { n: PROFILE.subreddits.length }), PROFILE.subreddits.map(s => "r/" + s), n30(l => l.src === "reddit")));
  for (const f of PROFILE.feeds) {
    const k = f.key === "larajobs" ? "larajobs" : f.key.startsWith("wwr") ? "wwr" : "other";
    const [name, cat] = f.label.split(" · ");
    cards.push(card(k, name, t("Active · RSS feed"), [cat || t("all jobs")], n30(l => l.source === f.key)));
  }
  $("srcgrid").replaceChildren(...cards);
  $("keywords").replaceChildren(...PROFILE.keywords.map(w => el("span", { class: "kw" }, w)));
  $("rules").textContent = t("Every post is scored 1–10 by AI for buying intent and fit with your skills ({skills}). Posts scoring {n}+ become leads{remote}. Reddit leads also get a comment check: how crowded the thread is, and whether a reply is still worth it.",
    { skills: PROFILE.skills, n: PROFILE.threshold, remote: PROFILE.remote_only ? t(", and jobs locked to a country you can't work from are scored low") : "" });
}

// ---------- replies + won ----------
function marked(l) { const t = statusTime(l); return t ? ago(t) : "—"; }
function statusPill(l) { const [cls, label] = STATUS_PILL[statusOf(l)] || ["muted", "New"]; return el("span", { class: "pill " + cls }, t(label)); }
function renderReplies() {
  const list = leads.filter(l => IN_MOTION.includes(statusOf(l))).sort((a, b) => statusTime(b) - statusTime(a));
  $("replies-body").replaceChildren(...(list.length ? list.map(l => clickRow(l, [leadCell(l, subLine(l)), el("span", { class: "mono" }, marked(l)), srcBadge(l), statusPill(l)]))
    : [emptyRow(4, t("No replies yet"), t("Open a lead and mark it Replied or Applied — it will be tracked here."))]));
}
function renderWon() {
  const won = leads.filter(l => statusOf(l) === "won").sort((a, b) => statusTime(b) - statusTime(a));
  const tried = leads.filter(l => [...IN_MOTION, "won", "lost"].includes(statusOf(l))).length;
  const monthStart = new Date(); monthStart.setDate(1); monthStart.setHours(0, 0, 0, 0);
  const earnedMonth = won.filter(l => statusTime(l) >= monthStart.getTime()).reduce((s, l) => s + (l.deal_value || 0), 0);
  const earnedAll = won.reduce((s, l) => s + (l.deal_value || 0), 0);
  const priced = won.filter(l => l.deal_value);
  $("won-cards").replaceChildren(
    statCard(t("Earned this month"), money(earnedMonth), t("{n} clients won all time", { n: won.length }), "var(--apply)"),
    statCard(t("Earned all time"), money(earnedAll), priced.length ? t("avg. deal {m}", { m: money(earnedAll / priced.length) }) : t("add deal values in the lead panel")),
    statCard(t("Reply → win"), tried ? pct(won.length, tried) + "%" : "—", t("{n} contacted · {w} won", { n: tried, w: won.length })));
  $("won-body").replaceChildren(...(won.length ? won.map(l => clickRow(l, [leadCell(l, subLine(l)), el("span", { class: "mono" }, marked(l)), srcBadge(l),
      el("span", { style: "display:inline-flex;gap:8px;align-items:center" }, el("span", { class: "pill apply" }, t("Client")),
        l.deal_value ? el("span", { class: "mono", style: "color:var(--apply)" }, money(l.deal_value)) : null)]))
    : [emptyRow(4, t("No wins yet"), t("When a lead turns into a client, open it and mark it Won."))]));
}

// ---------- pipeline board ----------
let dragged = null;
function renderPipeline() {
  const active = leads.filter(l => statusOf(l) === "talking");
  const won = leads.filter(l => statusOf(l) === "won");
  const contacted = leads.filter(l => ["replied", "applied", "talking", "won", "lost"].includes(statusOf(l)));
  $("pipe-cards").replaceChildren(
    statCard(t("In talks"), String(active.length), t("{m} possible", { m: money(active.reduce((s, l) => s + (l.deal_value || 0), 0)) })),
    statCard(t("Won"), String(won.length), t("{m} earned", { m: money(won.reduce((s, l) => s + (l.deal_value || 0), 0)) }), "var(--apply)"),
    statCard(t("Contacted"), String(contacted.length), t("replied, applied or further")),
    statCard(t("Win rate"), contacted.length ? pct(won.length, contacted.length) + "%" : "—", t("of contacted leads")));

  $("board").replaceChildren(...BOARD.map(col => {
    let items = leads.filter(l => col.has.includes(statusOf(l)));
    let more = 0;
    if (col.key === "new") {            // "New" mein sirf kaam ke leads (Apply/Reply), behtareen pehle
      items = items.filter(l => l.verdict === "Apply" || l.verdict === "Reply").sort((a, b) => b.score - a.score || b.ms - a.ms);
      more = Math.max(0, items.length - 15);
      items = items.slice(0, 15);
    } else items.sort((a, b) => statusTime(b) - statusTime(a));
    const sum = items.reduce((s, l) => s + (l.deal_value || 0), 0);
    const box = el("div", { class: "kcol", "data-col": col.key },
      el("div", { class: "kcol-head" }, el("span", { class: "dot", style: `background:${col.dot};box-shadow:none` }), t(col.label),
        sum ? el("span", { class: "sum" }, money(sum)) : null, el("span", { class: "n" }, String(items.length + more))),
      ...items.map(kanbanCard), more ? el("div", { class: "more" }, t("+{n} more in Leads", { n: more })) : null);
    box.addEventListener("dragover", e => { e.preventDefault(); box.classList.add("drop"); });
    box.addEventListener("dragleave", () => box.classList.remove("drop"));
    box.addEventListener("drop", e => {
      e.preventDefault(); box.classList.remove("drop");
      if (dragged && !col.has.includes(statusOf(dragged))) setStatus(dragged, col.target(dragged));
    });
    return box;
  }));
}
function kanbanCard(l) {
  const move = el("select", { "aria-label": t("Move to stage") }, el("option", { value: "" }, t("Move to…")),
    ...BOARD.filter(c => !c.has.includes(statusOf(l))).map(c => el("option", { value: c.key }, t(c.label))));
  move.addEventListener("click", e => e.stopPropagation());
  move.addEventListener("change", () => { const c = BOARD.find(x => x.key === move.value); if (c) setStatus(l, c.target(l)); });
  const card = el("div", { class: "kcard", draggable: "true", tabindex: "0" },
    el("div", { class: "t", dir: "auto" }, l.title || t("(no title)")),
    el("div", { class: "m" }, el("span", { class: "score" + (l.score >= 9 ? " hi" : ""), style: "padding:1px 6px;font-size:0.7rem" }, l.score + "/10"),
      SRC[l.src].short === "R" ? l.source : SRC[l.src].name, l.deal_value ? el("span", { class: "money" }, money(l.deal_value)) : null),
    move);
  card.addEventListener("dragstart", () => { dragged = l; card.classList.add("dragging"); });
  card.addEventListener("dragend", () => { dragged = null; card.classList.remove("dragging"); });
  card.addEventListener("click", () => openLead(l));
  card.addEventListener("keydown", e => { if (e.key === "Enter") openLead(l); });
  return card;
}

// ---------- reports ----------
function renderReports() {
  const b = makeBuckets(30);
  const acted = leads.filter(l => [...IN_MOTION, "won"].includes(statusOf(l)) && statusTime(l)).map(statusTime);
  lineChart($("rep-chart"), b, [
    { name: t("Leads found"), color: "#3d82f6", area: true, values: countIn(b, leads.map(l => l.ms)) },
    { name: t("Replied, applied or won"), color: "#35c08a", values: countIn(b, acted) }], 200);
  axisLabels($("rep-axis"), b);
  const since = startOfDay(29), cur = leads.filter(l => l.ms >= since);
  const prev = leads.filter(l => l.ms >= startOfDay(59) && l.ms < since).length;
  trendEl($("rep-trend"), cur.length, prev);
  const actedCur = cur.filter(l => [...IN_MOTION, "won"].includes(statusOf(l))).length;
  const best = SRC_ORDER.map(k => [k, cur.filter(l => l.src === k).length]).sort((a, b) => b[1] - a[1])[0];
  const trendNote = prev ? t("{arrow} {p}% vs previous 30 days", { arrow: cur.length >= prev ? "▲" : "▼", p: Math.abs(Math.round((cur.length - prev) / prev * 100)) }) : t("last 30 days");
  $("rep-cards").replaceChildren(
    statCard(t("Total leads"), String(cur.length), trendNote),
    statCard(t("Acted on"), String(actedCur), t("{p}% of leads replied, applied or won", { p: pct(actedCur, cur.length) })),
    statCard(t("Best source"), best && best[1] ? t(SRC[best[0]].name) : "—", best && best[1] ? t("{n} leads", { n: best[1] }) : t("no leads yet"), best && best[1] ? "#6fe0b0" : ""));
  $("rep-cards").lastChild.querySelector(".bignum").style.fontSize = "1.1rem";
  $("runs-body").replaceChildren(...(runs.length ? runs.slice(0, 12).map(r => {
    const [cls, label] = RUN_STATUS[r.status] || ["muted", r.status || "Unknown"];  // label ka tarjuma neeche
    const d = new Date(r.ms);
    return el("tr", {}, el("td", { class: "mono" }, fmtDay(d) + ", " + d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" })),
      el("td", {}, el("span", { class: "pill " + cls }, t(label))),
      ...[r.fetched, r.new, r.scored, r.leads].map(v => el("td", { class: "mono" }, String(v ?? 0))));
  }) : [emptyRow(6, t("No scans yet"), t("Each scan is logged here."))]));
}

// ---------- detail panel ----------
const panel = $("panel"), scrim = $("scrim");
let lastFocus = null, panelFor = null;   // panelFor: kis lead ka panel bana hua hai (likhte waqt dobara na bane)
function openLead(l) {
  lastFocus = document.activeElement; state.open = l.id; panelFor = null;
  renderAll(); panel.classList.add("show"); scrim.classList.add("show"); $("p-close").focus();
}
function closeLead() {
  if (state.open == null) return;
  state.open = null; panelFor = null; panel.classList.remove("show"); scrim.classList.remove("show"); renderAll();
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
}
const sec = (label, ...kids) => el("div", { class: "sec" }, el("p", { class: "sec-label" }, label), ...kids);

function draftSection(l) {
  const left = Math.max(0, DRAFTS.limit - DRAFTS.used);
  const box = el("div", {});
  async function generate(btn) {
    btn.disabled = true; btn.textContent = t("Writing…");
    try {
      const r = await api("/api/draft", { id: l.id });
      l.draft = r.draft; l.draft_at = new Date().toISOString();
      DRAFTS = { used: r.used, limit: r.limit };
      panelFor = null; renderAll();
    } catch (e) { btn.disabled = false; btn.textContent = t(l.draft ? "Write a new one" : "Write a draft with AI"); toast(e.message, null, null, "err"); }
  }
  if (!l.draft) {
    const btn = el("button", { type: "button", class: "sbtn primary", disabled: left ? null : "" }, t("Write a draft with AI"));
    btn.addEventListener("click", () => generate(btn));
    box.append(el("div", { class: "row-btns", style: "margin-top:0" }, btn,
      el("span", { class: "small-hint" }, left ? t("{left} of {limit} left today", { left, limit: DRAFTS.limit }) : t("Daily limit reached — more tomorrow"))));
    return sec(t(l.is_job ? "Application draft" : "Reply draft"), box);
  }
  const area = el("textarea", { "aria-label": t("Draft text"), dir: "auto" });
  area.value = l.draft;
  const copy = el("button", { type: "button", class: "sbtn primary" }, t("Copy"));
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(area.value); copy.textContent = t("Copied ✓"); }
    catch { area.select(); copy.textContent = t("Press Ctrl+C"); }
    setTimeout(() => { copy.textContent = t("Copy"); }, 2000);
  });
  const again = el("button", { type: "button", class: "sbtn", disabled: left ? null : "" }, t("Write a new one"));
  again.addEventListener("click", () => generate(again));
  box.append(el("div", { class: "draft-box" }, el("span", { class: "tag" }, t("AI DRAFT · EDIT BEFORE SENDING")), area),
    el("div", { class: "row-btns" }, copy, again, el("span", { class: "small-hint" }, t("{left} of {limit} left today", { left, limit: DRAFTS.limit }))));
  return sec(t(l.is_job ? "Application draft" : "Reply draft"), box);
}

function notesSection(l) {
  const area = el("textarea", { class: "notes", placeholder: t("e.g. Asked for $30/hr, they reply on weekdays…"), "aria-label": t("Your notes"), dir: "auto" });
  area.value = l.user_note || "";
  const status = el("span", { class: "small-hint" }, "");
  const save = async () => {
    if (area.value === (l.user_note || "")) return;
    status.textContent = t("Saving…"); status.className = "small-hint";
    const ok = await updateLead(l, { user_note: area.value }, { note: area.value });
    status.textContent = ok ? t("Saved ✓") : ""; status.className = "small-hint" + (ok ? " ok" : "");
  };
  area.addEventListener("blur", save);   // bahar click karte hi save
  const btn = el("button", { type: "button", class: "sbtn" }, t("Save note"));
  btn.addEventListener("click", save);
  return sec(t("Your notes"), area, el("div", { class: "row-btns" }, btn, status));
}

function reminderSection(l) {
  const plus = n => { const d = new Date(); d.setDate(d.getDate() + n); return localISO(d); };
  const sel = el("select", { "aria-label": t("Follow-up reminder") },
    el("option", { value: "" }, t(l.remind_at ? "Change reminder…" : "No reminder")),
    el("option", { value: plus(1) }, t("Tomorrow")), el("option", { value: plus(3) }, t("In 3 days")),
    el("option", { value: plus(7) }, t("In a week")), el("option", { value: "pick" }, t("Pick a date…")));
  const picker = el("input", { type: "date", min: todayISO(), hidden: "" });
  const set = iso => updateLead(l, { remind_at: iso }, { remind_at: iso }).then(() => { panelFor = null; renderAll(); });
  sel.addEventListener("change", () => {
    if (sel.value === "pick") { picker.hidden = false; picker.focus(); return; }
    if (sel.value) set(sel.value);
  });
  picker.addEventListener("change", () => { if (picker.value) set(picker.value); });
  const row = el("div", { class: "remind-row" }, sel, picker);
  if (l.remind_at) {
    const clear = el("button", { type: "button", class: "sbtn" }, t("Clear"));
    clear.addEventListener("click", () => set(null));
    row.prepend(el("span", { class: isDue(l) ? "due" : "small-hint", style: "font-size:0.84rem" },
      t(isDue(l) ? "Due {date}" : "Reminder: {date}", { date: fmtISODay(l.remind_at) })), clear);
  }
  return sec(t("Follow-up reminder"), row, el("div", { class: "small-hint", style: "margin-top:6px" }, t("It shows under “Follow-ups” and the bell on that day.")));
}

function assignSection(l) {
  const sel = el("select", { "aria-label": t("Assigned to"), class: "assign" },
    el("option", { value: "" }, t("Nobody yet")),
    ...TEAM.map(m => { const o = el("option", { value: String(m.id) }, m.id === ME.id ? t("{name} (me)", { name: m.name }) : m.name);
                       if (m.id === l.assigned_to) o.selected = true; return o; }));
  sel.addEventListener("change", () => {
    const who = sel.value ? Number(sel.value) : null;
    updateLead(l, { assigned_to: who }, { assigned_to: who });
  });
  return sec(t("Assigned to"), el("div", { class: "remind-row" }, sel));
}

function dealSection(l) {
  const input = el("input", { type: "number", min: "0", step: "1", inputmode: "decimal", placeholder: t("e.g. 500"), "aria-label": t("Deal value in dollars") });
  input.value = l.deal_value ?? "";
  const status = el("span", { class: "small-hint" }, "");
  input.addEventListener("change", async () => {
    const raw = input.value.trim();
    const value = raw === "" ? null : Number(raw);
    if (value !== null && (!isFinite(value) || value < 0)) { status.textContent = t("Enter a positive number"); status.className = "small-hint err"; return; }
    const ok = await updateLead(l, { deal_value: value }, { deal_value: value });
    status.textContent = ok ? t("Saved ✓") : ""; status.className = "small-hint" + (ok ? " ok" : "");
  });
  return sec(t("Deal value"), el("div", { class: "deal-row" }, el("span", { class: "mono" }, "$"), input, status),
    el("div", { class: "small-hint", style: "margin-top:6px" }, t("What the job is worth. Won deals add up on the Won screen.")));
}

function renderPanel() {
  const l = leads.find(x => x.id === state.open);
  if (!l) return;
  panelFor = l.id;
  $("p-ava").replaceWith(Object.assign(avatar(l, true), { id: "p-ava" }));
  const v = $("p-verdict"); v.className = "pill " + (VCLASS[l.verdict] || "muted"); v.textContent = t(l.verdict || "Review");
  $("p-title").textContent = l.title || t("(no title)");
  $("p-meta").replaceChildren(scoreBadge(l), srcBadge(l), el("span", { class: "lead-sub", style: "margin:0" }, t("posted {ago}", { ago: ago(l.posted) }) + " · " + t("found {ago}", { ago: ago(l.ms) })));
  const checkMeta = l.is_job ? t("Job listing") : t("{n} comments · {c} competition", { n: l.comment_count || 0, c: t(l.competition || "unknown") });
  const notRel = el("button", { type: "button", class: "notrel" }, t("Not relevant — hide this lead"));
  notRel.addEventListener("click", () => hideLead(l));
  $("p-body").replaceChildren(
    sec(t(l.is_job ? "The job" : "The post"), el("div", { class: "posttext", dir: "auto" }, l.text || t("No text saved — open it to read the full post."))),
    sec(t("Why Foxlead flagged it"), el("div", { class: "reason", dir: "auto" }, l.reason || t("Scored {s}/10 for your profile.", { s: l.score }))),
    sec(t(l.is_job ? "Before you apply" : "Is a reply worth it?"),
      el("div", { class: "check-box", dir: "auto" }, el("div", { class: "meta" }, checkMeta), l.note || t("No extra notes."))),
    draftSection(l),
    ...(TEAM.length > 1 ? [assignSection(l)] : []),
    notesSection(l),
    reminderSection(l),
    dealSection(l),
    sec(t("Your status"), el("div", { class: "status-chips", id: "p-status" }), notRel));
  renderPanelStatus(l);
  const open = $("p-open");
  open.href = safeUrl(l.link);
  open.querySelector("span").textContent = t(l.is_job ? "Open job" : "Open post");
}
// sirf status wala hissa (chips + mark button) - baaqi panel (likha hua note/draft) waisa hi rahe
function renderPanelStatus(l) {
  const st = statusOf(l);
  $("p-status").replaceChildren(...STATUS_LIST.map(([s, label]) => {
    const c = el("button", { type: "button", class: "chip" + (s === st ? " on" : "") }, t(label));
    c.addEventListener("click", () => setStatus(l, s));
    return c;
  }));
  const target = l.is_job ? "applied" : "replied";
  const mark = $("p-mark");
  mark.querySelector("span").textContent = t(st === target ? "Marked " + target : "Mark " + target);
  mark.onclick = () => setStatus(l, st === target ? "new" : target);
}

// ---------- wiring ----------
function renderAll() {
  renderChrome();
  if (state.screen === "leads") renderLeads();
  if (state.screen === "pipeline") renderPipeline();
  if (state.screen === "sources") renderSources();
  if (state.screen === "replies") renderReplies();
  if (state.screen === "won") renderWon();
  if (state.screen === "reports") renderReports();
  if (state.open != null) {
    const l = leads.find(x => x.id === state.open);
    if (l && panelFor === l.id) renderPanelStatus(l);   // panel bana hua hai - sirf status taaza karo
    else renderPanel();
  }
}
$("nav").addEventListener("click", e => { const b = e.target.closest("button"); if (b) { state.screen = b.dataset.s; renderAll(); } });
$("filters").addEventListener("click", e => { const c = e.target.closest(".chip"); if (c) { state.chip = c.dataset.f; renderLeads(); } });
$("q").addEventListener("input", e => { state.q = e.target.value; state.screen = "leads"; renderAll(); });
$("range").addEventListener("change", e => { state.range = Number(e.target.value); renderAll(); });
$("sort").addEventListener("change", e => { state.sort = e.target.value; renderLeads(); });
$("bell").addEventListener("click", () => { state.screen = "leads"; state.chip = leads.some(isDue) ? "due" : "todo"; renderAll(); });
$("scan").addEventListener("click", async () => {
  try { await api("/api/scan", {}); scanning = true; renderAll(); toast(t("Scan started — this takes a few minutes."), null, null, "ok"); setTimeout(() => load().catch(e => toast(e.message, null, null, "err")), 8000); }
  catch (e) { toast(e.message, null, null, "err"); }
});
const resend = $("verify-resend");
if (resend) resend.addEventListener("click", async () => {
  resend.disabled = true;
  try { await api("/verify/resend", {}); resend.textContent = t("Sent ✓ — check your inbox"); resend.classList.add("ok"); }
  catch (e) { resend.disabled = false; toast(e.message, null, null, "err"); }
});
const meBtn = $("me-btn"), meMenu = $("me-menu");
meBtn.addEventListener("click", () => { meMenu.hidden = !meMenu.hidden; meBtn.setAttribute("aria-expanded", String(!meMenu.hidden)); });
document.addEventListener("click", e => { if (!e.target.closest(".me")) { meMenu.hidden = true; meBtn.setAttribute("aria-expanded", "false"); } });
$("p-close").addEventListener("click", closeLead);
scrim.addEventListener("click", closeLead);
document.addEventListener("keydown", e => { if (e.key === "Escape") { closeLead(); meMenu.hidden = true; } });
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 120); });
renderAll();
load().catch(e => toast(e.message, null, null, "err"));
