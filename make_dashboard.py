# make_dashboard.py
# Maqsad: history.json (har run ka hisaab + saari emailed leads) se FOXLEAD
# dashboard banao: dashboard/index.html. GitHub Actions ise har ghante GitHub
# Pages par daal deta hai; laptop par double-click karke bhi khol sakte ho.
#
# Screens (left menu): Leads, Sources, Replies, Won, Reports.
# Lead par click = detail panel (post, AI ka reason, comment check, status).
# Status (New / Replied / Applied / Won / Skipped) TUMHARE BROWSER mein yaad
# rehta hai (localStorage) - GitHub par nahi jaata.
#
# ZAROORI: lead ke title/text Reddit se aate hain (koi bhi kuch bhi likh sakta hai),
# isliye page unhe sirf text ki tarah dikhata hai (textContent) - HTML ki tarah nahi.

import os
import ast
import json
from datetime import datetime, timezone

HISTORY_FILE = "history.json"
OUT_DIR = "dashboard"
OUT_FILE = os.path.join(OUT_DIR, "index.html")

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Foxlead Dashboard</title>
<style>
  :root {
    --bg: #0b0e15; --bg-2: #0e1219; --rail: #0f141d; --panel: #141a26;
    --panel-2: #0f1522; --over: #121926; --line: #202a3a; --line-2: #1a2230;
    --ink: #eef2f8; --soft: #9aa7bd; --faint: #5f6c82;
    --accent: #3d82f6; --accent-2: #7db0ff; --accent-dim: #1d3a66; --accent-soft: #112542;
    --glow: rgba(61,130,246,0.16); --grid: #18202e;
    --apply: #35c08a; --apply-bg: #0f2a20; --apply-dim: #1c5a3f;
    --reply: #4aa3f2; --reply-bg: #112339;
    --skip: #e07a74; --skip-bg: #2a1614;
    --maybe: #d9a94e; --maybe-bg: #2a2311;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    --mono: "SFMono-Regular", "Consolas", Menlo, monospace;
    color-scheme: dark;
  }
  * { box-sizing: border-box; }
  html { background: var(--bg); }
  body { background: var(--bg); color: var(--ink); font: 14px/1.5 var(--sans); margin: 0; -webkit-font-smoothing: antialiased; }
  button, input, select { font: inherit; color: inherit; }
  :focus-visible { outline: 2px solid var(--accent-2); outline-offset: 2px; }
  [hidden] { display: none !important; }

  .app { max-width: 1160px; margin: 14px auto; padding: 0 14px 30px; }
  .frame { position: relative; display: flex; background: var(--bg-2); border: 1px solid var(--line);
           border-radius: 16px; overflow: hidden; min-height: 700px; box-shadow: 0 30px 70px -24px rgba(0,0,0,0.65); }

  /* rail */
  .rail { width: 210px; flex: 0 0 210px; background: var(--rail); border-right: 1px solid var(--line); padding: 18px 14px; display: flex; flex-direction: column; }
  .brand { display: flex; align-items: center; gap: 10px; padding: 4px 8px 20px; }
  .logo { width: 32px; height: 32px; border-radius: 9px; flex: 0 0 auto; background: linear-gradient(140deg, var(--accent), var(--accent-2));
          display: flex; align-items: center; justify-content: center; box-shadow: 0 0 0 1px rgba(61,130,246,0.4), 0 6px 16px var(--glow); }
  .logo svg { width: 18px; height: 18px; }
  .brand-name { font-weight: 700; font-size: 1.06rem; letter-spacing: -0.01em; }
  .brand-name span { color: var(--accent); }
  .nav-label { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--faint); padding: 0 11px; margin: 6px 0 7px; }
  .nav { display: flex; flex-direction: column; gap: 2px; }
  .nav button { display: flex; align-items: center; gap: 11px; width: 100%; padding: 9px 11px; border: 0; border-radius: 8px; background: none;
                color: var(--soft); text-align: left; font-size: 0.88rem; font-weight: 500; cursor: pointer; }
  .nav button svg { width: 16px; height: 16px; flex: 0 0 auto; opacity: 0.85; }
  .nav .count { margin-left: auto; font-family: var(--mono); font-size: 0.7rem; font-weight: 600; color: var(--faint); background: var(--panel); padding: 1px 7px; border-radius: 10px; }
  .nav button.on { background: var(--accent-soft); color: var(--ink); }
  .nav button.on svg { color: var(--accent); opacity: 1; }
  .nav button.on .count { background: var(--accent); color: #fff; }
  .nav button:hover:not(.on) { background: var(--panel); color: var(--ink); }
  .rail-card { margin-top: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 11px; padding: 13px 14px; }
  .rail-card .k { font-size: 0.64rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--faint); display: flex; align-items: center; gap: 6px; }
  .rail-card .big { font-family: var(--mono); font-size: 1.5rem; font-weight: 700; margin-top: 7px; letter-spacing: -0.02em; }
  .rail-card .sub { font-size: 0.72rem; color: var(--faint); }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--apply); box-shadow: 0 0 0 3px rgba(53,192,138,0.18); flex: 0 0 auto; display: inline-block; }
  .dot.bad { background: var(--skip); box-shadow: 0 0 0 3px rgba(224,122,116,0.18); }
  .dot.idle { background: var(--faint); box-shadow: 0 0 0 3px rgba(95,108,130,0.18); }

  /* main + topbar */
  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .topbar { display: flex; align-items: center; gap: 12px; padding: 14px 22px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
  .search { flex: 1; min-width: 150px; display: flex; align-items: center; gap: 9px; background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 0 13px; color: var(--faint); font-size: 0.86rem; }
  .search svg { width: 15px; height: 15px; flex: 0 0 auto; }
  .search input { flex: 1; min-width: 0; background: transparent; border: 0; outline: none; color: var(--ink); padding: 9px 0; }
  .search input::placeholder { color: var(--faint); }
  .search:focus-within { border-color: var(--accent-dim); }
  .daterange { display: inline-flex; align-items: center; gap: 8px; font-size: 0.8rem; color: var(--soft); background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 0 0 0 13px; white-space: nowrap; }
  .daterange svg { width: 15px; height: 15px; }
  .daterange select { background: transparent; border: 0; color: var(--soft); padding: 8px 13px 8px 0; cursor: pointer; outline: none; }
  .daterange select option { background: var(--panel); color: var(--ink); }
  .iconbtn { position: relative; width: 38px; height: 38px; border-radius: 9px; background: var(--panel); border: 1px solid var(--line); display: flex; align-items: center; justify-content: center; color: var(--soft); cursor: pointer; padding: 0; }
  .iconbtn svg { width: 17px; height: 17px; }
  .iconbtn .badge { position: absolute; top: -5px; right: -5px; background: var(--skip); color: #fff; font-family: var(--mono); font-size: 0.6rem; font-weight: 700; min-width: 16px; height: 16px; border-radius: 8px; display: flex; align-items: center; justify-content: center; padding: 0 4px; border: 2px solid var(--bg-2); }
  .avatar-me { width: 38px; height: 38px; border-radius: 50%; flex: 0 0 auto; background: linear-gradient(140deg,#2e5bc0,#7db0ff); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.82rem; }

  .titlerow { padding: 18px 22px 2px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .titlerow h1 { font-size: 1.4rem; font-weight: 700; margin: 0; letter-spacing: -0.02em; }
  .titlerow .sub { margin: 3px 0 0; font-size: 0.84rem; color: var(--soft); }
  .titlerow .grow { flex: 1; min-width: 0; }
  .live { display: inline-flex; align-items: center; gap: 7px; font-size: 0.74rem; color: var(--soft); background: var(--panel); border: 1px solid var(--line); padding: 6px 12px; border-radius: 20px; white-space: nowrap; }

  .screen { display: none; }
  .screen.on { display: block; }

  /* cards + charts */
  .grid { display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 13px; padding: 16px 22px 6px; }
  .grid.three { grid-template-columns: repeat(3, 1fr); }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 13px; padding: 15px 16px; min-width: 0; }
  .card-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 3px; }
  .card-head h3 { font-size: 0.78rem; font-weight: 600; margin: 0; color: var(--soft); }
  .trend { font-family: var(--mono); font-size: 0.72rem; font-weight: 600; color: var(--apply); }
  .trend.down { color: var(--skip); }
  .bignum { font-family: var(--mono); font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
  .note { font-size: 0.74rem; color: var(--soft); margin-top: 2px; }
  .chart-box { margin-top: 4px; }
  .chart-box svg { display: block; overflow: visible; }
  .xaxis { display: flex; justify-content: space-between; margin-top: 5px; font-family: var(--mono); font-size: 0.62rem; color: var(--faint); }
  .bars { display: flex; flex-direction: column; gap: 9px; margin-top: 10px; }
  .bar-row { display: grid; grid-template-columns: 84px 1fr 26px; align-items: center; gap: 9px; }
  .bar-row .lab { font-size: 0.74rem; color: var(--soft); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bar-track { height: 8px; background: var(--line-2); border-radius: 5px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 5px; }
  .bar-row .num { font-family: var(--mono); font-size: 0.72rem; color: var(--faint); text-align: right; }
  .spread { display: flex; align-items: flex-end; gap: 6px; height: 72px; margin-top: 12px; }
  .spread .col { flex: 1; height: 100%; display: flex; flex-direction: column; align-items: center; gap: 5px; justify-content: flex-end; }
  .spread .b { width: 100%; min-height: 2px; background: var(--accent-dim); border-radius: 4px 4px 0 0; }
  .spread .col.hot .b { background: var(--accent); }
  .spread .cl { font-family: var(--mono); font-size: 0.6rem; color: var(--faint); }

  /* filters */
  .filters { display: flex; align-items: center; gap: 8px; padding: 14px 22px 10px; flex-wrap: wrap; }
  .chip { font-size: 0.78rem; font-weight: 600; padding: 6px 13px; border-radius: 20px; border: 1px solid var(--line); background: var(--panel); color: var(--soft); cursor: pointer; user-select: none; white-space: nowrap; }
  .chip:hover { border-color: var(--accent-dim); color: var(--ink); }
  .chip.on { background: var(--accent); border-color: var(--accent); color: #fff; }
  .filters .spacer { flex: 1; }
  .filters .result { font-size: 0.76rem; color: var(--faint); font-family: var(--mono); }

  /* tables */
  .table-wrap { padding: 0 22px 18px; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; min-width: 740px; }
  thead th { text-align: left; font-size: 0.64rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--faint); font-weight: 600; padding: 9px 14px; border-bottom: 1px solid var(--line); white-space: nowrap; }
  tbody td { padding: 11px 14px; border-bottom: 1px solid var(--line-2); font-size: 0.88rem; vertical-align: middle; }
  tbody tr.click { cursor: pointer; }
  tbody tr.click:hover { background: var(--panel-2); }
  tbody tr.sel { background: var(--accent-soft); }
  tbody tr.done .lead-title { color: var(--soft); }
  .lead-cell { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .avatar { width: 34px; height: 34px; border-radius: 9px; flex: 0 0 auto; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.78rem; color: #fff; }
  .lead-title { color: var(--ink); font-weight: 600; }
  .lead-sub { color: var(--faint); font-size: 0.75rem; margin-top: 2px; }
  .score { font-family: var(--mono); font-weight: 700; font-size: 0.82rem; padding: 3px 9px; border-radius: 7px; background: var(--accent-soft); color: #9cc4ff; border: 1px solid var(--accent-dim); white-space: nowrap; }
  .score.hi { background: var(--apply-bg); color: #6fe0b0; border-color: var(--apply-dim); }
  .srcbadge { display: inline-flex; align-items: center; gap: 7px; font-size: 0.8rem; color: var(--soft); white-space: nowrap; }
  .srcbadge .sq { width: 18px; height: 18px; border-radius: 5px; flex: 0 0 auto; display: flex; align-items: center; justify-content: center; font-size: 0.58rem; font-weight: 800; color: #fff; }
  .comp, .mono { font-family: var(--mono); font-size: 0.78rem; }
  .comp.low { color: var(--apply); } .comp.medium { color: var(--maybe); } .comp.high { color: var(--skip); } .comp.na { color: var(--faint); }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 0.72rem; font-weight: 700; padding: 4px 11px; border-radius: 20px; white-space: nowrap; }
  .pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .pill.apply { background: var(--apply-bg); color: var(--apply); }
  .pill.reply { background: var(--reply-bg); color: var(--reply); }
  .pill.maybe { background: var(--maybe-bg); color: var(--maybe); }
  .pill.skip { background: var(--skip-bg); color: var(--skip); }
  .pill.muted { background: var(--panel-2); color: var(--soft); }
  .foot-row { display: flex; align-items: center; justify-content: space-between; padding: 0 22px 20px; font-size: 0.76rem; color: var(--faint); flex-wrap: wrap; gap: 8px; }
  .foot-row .auto { display: inline-flex; align-items: center; gap: 7px; }

  .pad { padding: 18px 22px 24px; }
  .empty { text-align: center; padding: 46px 20px; color: var(--soft); }
  .empty svg { width: 42px; height: 42px; color: var(--faint); margin-bottom: 14px; }
  .empty h3 { color: var(--ink); font-size: 1.05rem; margin: 0 0 6px; }
  .empty p { margin: 0 auto; max-width: 42ch; font-size: 0.9rem; }

  /* sources */
  .srcgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 13px; }
  .srccard { background: var(--panel); border: 1px solid var(--line); border-radius: 13px; padding: 16px; display: flex; flex-direction: column; }
  .srccard .top { display: flex; align-items: center; gap: 11px; margin-bottom: 12px; }
  .srccard .ic { width: 38px; height: 38px; border-radius: 10px; flex: 0 0 auto; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.78rem; color: #fff; }
  .srccard .nm { font-weight: 700; font-size: 0.96rem; }
  .srccard .st { font-size: 0.74rem; color: var(--soft); margin-top: 1px; display: flex; align-items: center; gap: 6px; }
  .srccard .meta { font-size: 0.78rem; color: var(--faint); border-top: 1px solid var(--line-2); padding-top: 10px; margin-top: auto; display: flex; justify-content: space-between; }
  .srccard .meta b { color: var(--ink); font-family: var(--mono); }
  .kwrow { display: flex; flex-wrap: wrap; gap: 7px; margin: 0 0 12px; }
  .kw { font-size: 0.74rem; color: var(--soft); background: var(--panel-2); border: 1px solid var(--line); border-radius: 7px; padding: 4px 10px; }
  .card p.body { font-size: 0.84rem; color: var(--soft); margin: 4px 0 10px; }
  .card .table-wrap { padding: 0; }
  .card table { min-width: 560px; }

  /* reports */
  .legend { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 10px; font-size: 0.8rem; color: var(--soft); }
  .legend span { display: inline-flex; align-items: center; gap: 7px; }
  .legend i { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }

  /* detail panel */
  .scrim { position: fixed; inset: 0; background: rgba(5,8,13,0.55); opacity: 0; pointer-events: none; transition: opacity 0.2s; z-index: 5; }
  .scrim.show { opacity: 1; pointer-events: auto; }
  .panel { position: fixed; top: 0; right: 0; bottom: 0; width: 420px; max-width: 92vw; background: var(--over); border-left: 1px solid var(--line);
           transform: translateX(100%); transition: transform 0.24s cubic-bezier(.4,0,.2,1); z-index: 6; display: flex; flex-direction: column;
           box-shadow: -20px 0 50px -20px rgba(0,0,0,0.7); visibility: hidden; }
  .panel.show { transform: translateX(0); visibility: visible; }
  .panel-head { padding: 18px 20px 14px; border-bottom: 1px solid var(--line); }
  .panel-head .row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .panel-close { margin-left: auto; width: 32px; height: 32px; border-radius: 8px; background: var(--panel); border: 1px solid var(--line); color: var(--soft); display: flex; align-items: center; justify-content: center; cursor: pointer; padding: 0; }
  .panel-close svg { width: 15px; height: 15px; }
  .panel-head h2 { font-size: 1.08rem; font-weight: 700; margin: 0; line-height: 1.3; overflow-wrap: anywhere; }
  .panel-meta { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
  .panel-body { padding: 18px 20px; overflow-y: auto; flex: 1; }
  .sec-label { font-size: 0.66rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--faint); font-weight: 700; margin: 0 0 7px; }
  .sec { margin-bottom: 20px; }
  .posttext { font-size: 0.86rem; color: var(--soft); background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 13px 15px; line-height: 1.55; overflow-wrap: anywhere; }
  .reason { font-size: 0.88rem; color: var(--ink); background: var(--accent-soft); border-left: 3px solid var(--accent); border-radius: 0 10px 10px 0; padding: 12px 14px; }
  .check { font-size: 0.86rem; color: var(--ink); background: var(--panel); border: 1px dashed var(--accent-dim); border-radius: 10px; padding: 13px 15px; line-height: 1.55; }
  .check .meta { font-family: var(--mono); font-size: 0.72rem; color: var(--soft); margin-bottom: 6px; }
  .status-chips { display: flex; flex-wrap: wrap; gap: 7px; }
  .hint { font-size: 0.72rem; color: var(--faint); margin-top: 8px; }
  .panel-foot { padding: 14px 20px; border-top: 1px solid var(--line); display: flex; gap: 10px; }
  .pbtn { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 7px; font-size: 0.82rem; font-weight: 650; border-radius: 9px; padding: 11px; border: 1px solid var(--line); background: var(--panel); color: var(--soft); cursor: pointer; text-decoration: none; }
  .pbtn svg { width: 15px; height: 15px; }
  .pbtn.primary { background: var(--accent); border-color: var(--accent); color: #fff; box-shadow: 0 4px 14px var(--glow); }
  .pbtn.primary:hover { filter: brightness(1.06); }

  @media (max-width: 900px) { .grid { grid-template-columns: 1fr 1fr; } .grid:not(.three) .card:first-child { grid-column: 1 / -1; } }
  @media (max-width: 720px) {
    .app { margin-top: 0; }
    .frame { flex-direction: column; min-height: 0; }
    .rail { width: auto; flex: none; flex-direction: row; align-items: center; gap: 8px; padding: 10px 12px; border-right: 0; border-bottom: 1px solid var(--line); overflow-x: auto; }
    .brand { padding: 0 4px 0 0; }
    .brand-name, .nav-label, .rail-card { display: none; }
    .nav { flex-direction: row; }
    .nav button { white-space: nowrap; padding: 8px 10px; }
    .topbar, .titlerow, .grid, .filters, .table-wrap, .foot-row, .pad { padding-left: 14px; padding-right: 14px; }
  }
  @media (max-width: 560px) {
    .app { padding: 0; }
    .frame { border-radius: 0; border-left: 0; border-right: 0; }
    .grid, .grid.three { grid-template-columns: 1fr; }
    .avatar-me { display: none; }
  }
</style>
</head>
<body>
<div class="app">
  <div class="frame">

    <aside class="rail">
      <div class="brand">
        <div class="logo"><svg viewBox="0 0 24 24" fill="#fff" stroke="none" aria-hidden="true"><path d="M3.2 3.4l3 4.6A9 9 0 0 1 12 5.9a9 9 0 0 1 5.8 2.1l3-4.6 1 6.3c.1.7.2 1.5.2 2.2 0 4.6-4.5 8.2-10 8.2S2 16.5 2 11.9c0-.7.1-1.5.2-2.2l1-6.3z"/><circle cx="9" cy="12.3" r="1.25" fill="#1b2a4a"/><circle cx="15" cy="12.3" r="1.25" fill="#1b2a4a"/><path d="M10.6 15.4h2.8L12 17.1z" fill="#1b2a4a"/></svg></div>
        <div class="brand-name">Fox<span>lead</span></div>
      </div>
      <div class="nav-label">Workspace</div>
      <nav class="nav" id="nav">
        <button type="button" class="on" data-s="leads"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-6"/></svg>Leads<span class="count" id="c-leads"></span></button>
        <button type="button" data-s="sources"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7z"/><circle cx="12" cy="9" r="2.5"/></svg>Sources<span class="count">3</span></button>
        <button type="button" data-s="replies"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16v12H5.2L4 18z"/></svg>Replies<span class="count" id="c-replies"></span></button>
        <button type="button" data-s="won"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3 8-8"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>Won<span class="count" id="c-won"></span></button>
        <button type="button" data-s="reports"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9h10M7 13h6"/></svg>Reports</button>
      </nav>
      <div class="rail-card">
        <div class="k"><span class="dot" id="engine-dot"></span>Engine status</div>
        <div class="big" id="engine-big">—</div>
        <div class="sub" id="engine-sub">waiting for the first run</div>
      </div>
    </aside>

    <div class="main">
      <div class="topbar">
        <label class="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg><input type="search" id="q" placeholder="Search leads…" aria-label="Search leads"></label>
        <span class="daterange"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
          <select id="range" aria-label="Date range"><option value="7">Last 7 days</option><option value="30" selected>Last 30 days</option><option value="90">Last 90 days</option><option value="0">All time</option></select></span>
        <button type="button" class="iconbtn" id="bell" aria-label="Leads to act on"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg><span class="badge" id="bell-badge" hidden></span></button>
        <div class="avatar-me" aria-hidden="true">U</div>
      </div>

      <div class="screen on" id="s-leads">
        <div class="titlerow">
          <div class="grow"><h1>Leads</h1><p class="sub">Scored and ranked for your stack — best on top.</p></div>
          <span class="live"><span class="dot" id="live-dot"></span><span id="live-text">Checks every hour</span></span>
        </div>
        <div class="grid">
          <div class="card">
            <div class="card-head"><h3 id="found-title">Leads found</h3><span class="trend" id="found-trend"></span></div>
            <div class="bignum" id="found-num">0</div>
            <div class="chart-box" id="found-chart"></div>
            <div class="xaxis" id="found-axis"></div>
          </div>
          <div class="card">
            <div class="card-head"><h3>By source</h3></div>
            <div class="bars" id="by-source"></div>
            <div class="card-head" style="margin-top:16px;"><h3>Hit rate</h3></div>
            <div style="display:flex;align-items:center;gap:12px;margin-top:6px;" id="hit-rate"></div>
          </div>
          <div class="card">
            <div class="card-head"><h3>Score spread</h3></div>
            <div class="spread" id="spread"></div>
            <div style="font-size:0.74rem;color:var(--faint);margin-top:12px;line-height:1.5;" id="spread-note"></div>
          </div>
        </div>
        <div class="filters" id="filters">
          <button type="button" class="chip" data-f="all">All</button>
          <button type="button" class="chip" data-f="todo">To do</button>
          <button type="button" class="chip on" data-f="apply">Apply</button>
          <button type="button" class="chip" data-f="reply">Reply</button>
          <button type="button" class="chip" data-f="maybe">Maybe</button>
          <button type="button" class="chip" data-f="skip">Skip</button>
          <button type="button" class="chip" data-f="reddit">Reddit only</button>
          <button type="button" class="chip" data-f="jobs">Jobs only</button>
          <span class="spacer"></span>
          <span class="result" id="result"></span>
        </div>
        <div class="table-wrap"><table><thead><tr><th>Lead</th><th>Score</th><th>Source</th><th>Competition</th><th>Verdict</th></tr></thead><tbody id="tbody"></tbody></table></div>
        <div class="foot-row"><span id="showing"></span><span class="auto"><span class="dot" id="foot-dot"></span><span id="foot-text"></span></span></div>
      </div>

      <div class="screen" id="s-sources">
        <div class="titlerow"><div class="grow"><h1>Sources</h1><p class="sub">Where Foxlead looks, and what it searches for.</p></div></div>
        <div class="pad">
          <div class="srcgrid" id="srcgrid"></div>
          <div class="card" style="margin-top:16px;">
            <div class="card-head"><h3>Reddit search phrases</h3></div>
            <p class="body">Each subreddit is searched for these phrases (newest posts, last month).</p>
            <div class="kwrow" id="queries"></div>
          </div>
          <div class="card" style="margin-top:13px;">
            <div class="card-head"><h3>How leads are picked</h3></div>
            <p class="body" id="rules"></p>
          </div>
        </div>
      </div>

      <div class="screen" id="s-replies">
        <div class="titlerow"><div class="grow"><h1>Replies</h1><p class="sub">Leads you've replied to or applied for — track what's in motion.</p></div></div>
        <div class="table-wrap" style="padding-top:14px;"><table><thead><tr><th>Lead</th><th>Marked</th><th>Source</th><th>Status</th></tr></thead><tbody id="replies-body"></tbody></table></div>
      </div>

      <div class="screen" id="s-won">
        <div class="titlerow"><div class="grow"><h1>Won</h1><p class="sub">Leads that turned into real clients.</p></div></div>
        <div class="grid three" id="won-cards"></div>
        <div class="table-wrap" style="padding-top:14px;"><table><thead><tr><th>Client</th><th>Won</th><th>Source</th><th>Status</th></tr></thead><tbody id="won-body"></tbody></table></div>
      </div>

      <div class="screen" id="s-reports">
        <div class="titlerow"><div class="grow"><h1>Reports</h1><p class="sub">How Foxlead is performing over time.</p></div>
          <span class="live">Last 30 days</span></div>
        <div class="pad">
          <div class="card">
            <div class="card-head"><h3>Leads &amp; replies · last 30 days</h3><span class="trend" id="rep-trend"></span></div>
            <div class="chart-box" id="rep-chart"></div>
            <div class="xaxis" id="rep-axis"></div>
            <div class="legend"><span><i style="background:#3d82f6"></i>Leads found</span><span><i style="background:#35c08a"></i>Replied, applied or won</span></div>
          </div>
          <div class="grid three" style="padding:16px 0 0;" id="rep-cards"></div>
          <div class="card" style="margin-top:13px;">
            <div class="card-head"><h3>Recent runs</h3></div>
            <div class="table-wrap"><table><thead><tr><th>When</th><th>Result</th><th>Fetched</th><th>New</th><th>Scored</th><th>Leads</th></tr></thead><tbody id="runs-body"></tbody></table></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="scrim" id="scrim"></div>
<aside class="panel" id="panel" role="dialog" aria-modal="true" aria-labelledby="p-title">
  <div class="panel-head">
    <div class="row">
      <span class="avatar" id="p-ava" style="width:40px;height:40px;border-radius:10px;font-size:0.9rem;"></span>
      <span class="pill" id="p-verdict"></span>
      <button type="button" class="panel-close" id="p-close" aria-label="Close"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <h2 id="p-title"></h2>
    <div class="panel-meta" id="p-meta"></div>
  </div>
  <div class="panel-body" id="p-body"></div>
  <div class="panel-foot">
    <button type="button" class="pbtn" id="p-mark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg><span></span></button>
    <a class="pbtn primary" id="p-open" target="_blank" rel="noopener noreferrer"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg><span></span></a>
  </div>
</aside>

<script>
const DATA = __DATA__;
const CONFIG = DATA.config || {};
const DAY = 86400000;

const SRC = {
  reddit:   { name: "Reddit",           short: "R",  c1: "#e8803a", c2: "#f5a85f" },
  larajobs: { name: "LaraJobs",         short: "LJ", c1: "#38b2a8", c2: "#5fd3c8" },
  wwr:      { name: "We Work Remotely", short: "W",  c1: "#9a7cf0", c2: "#b9a3f7" },
};
const SRC_ORDER = ["larajobs", "wwr", "reddit"];
const VCLASS = { Apply: "apply", Reply: "reply", Maybe: "maybe", Review: "maybe", Skip: "skip" };
const STATUS_LIST = [["new", "New"], ["replied", "Replied"], ["applied", "Applied"], ["won", "Won"], ["skipped", "Skipped"]];
const STATUS_PILL = { replied: ["reply", "Replied"], applied: ["apply", "Applied"], won: ["apply", "Won"], skipped: ["skip", "Skipped"] };
const RUN_STATUS = {
  emailed: ["apply", "Emailed leads"], no_leads: ["muted", "No strong leads"], no_new: ["muted", "Nothing new"],
  fetch_failed: ["skip", "Fetch failed"], classify_failed: ["skip", "Scoring failed"], email_failed: ["skip", "Email failed"],
};
const RUN_OK = new Set(["emailed", "no_leads", "no_new"]);
const EMPTY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>';

// ---------- helpers (text goes in as text nodes - never as HTML) ----------
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
  const link = (l.link || "").toLowerCase(), src = (l.source || "").toLowerCase();
  if (link.includes("reddit.com") || src.startsWith("r/")) return "reddit";
  if (link.includes("larajobs") || src.includes("larajobs")) return "larajobs";
  return "wwr";
}
function initials(t) {
  const w = (t || "").replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean);
  return ((w[0] || "?")[0] + (w[1] ? w[1][0] : "")).toUpperCase();
}
function ago(ms) {
  const m = Math.round((Date.now() - ms) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return m + " min ago";
  const h = Math.round(m / 60);
  if (h < 48) return h + "h ago";
  return Math.round(h / 24) + " days ago";
}
const fmtDay = d => d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
function startOfDay(offsetDays) { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - offsetDays); return d.getTime(); }

// ---------- lead status (saved in this browser only) ----------
const STORE_KEY = "foxlead-status";
let statusMap = {};
try { statusMap = JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch (e) { statusMap = {}; }
function statusRec(l) { const r = statusMap[l.link]; return typeof r === "string" ? { s: r, t: 0 } : (r || { s: "new", t: 0 }); }
const statusOf = l => statusRec(l).s;
function setStatus(l, s) {
  if (s === "new") delete statusMap[l.link]; else statusMap[l.link] = { s, t: Date.now() };
  try { localStorage.setItem(STORE_KEY, JSON.stringify(statusMap)); } catch (e) { /* private window */ }
  renderAll();
}

// ---------- data ----------
const leads = (DATA.leads || []).map(l => ({ ...l, ms: new Date(l.found_at).getTime(), src: sourceKey(l) }))
  .sort((a, b) => b.ms - a.ms || (b.score || 0) - (a.score || 0));
const runs = (DATA.runs || []).map(r => ({ ...r, ms: new Date(r.time).getTime() })).sort((a, b) => b.ms - a.ms);
const state = { screen: "leads", range: 30, chip: "apply", q: "", open: null };   // default: Apply leads pehle

const rangeStart = () => state.range ? startOfDay(state.range - 1) : 0;
const inRange = l => l.ms >= rangeStart();
const isTodo = l => statusOf(l) === "new" && (l.verdict === "Apply" || l.verdict === "Reply");

// ---------- small building blocks ----------
function avatar(l, big) {
  const c = l.verdict === "Skip" ? ["#5a6472", "#7a8699"] : [SRC[l.src].c1, SRC[l.src].c2];
  return el("span", { class: "avatar", style: `background:linear-gradient(140deg,${c[0]},${c[1]})` + (big ? ";width:40px;height:40px;border-radius:10px;font-size:0.9rem" : "") }, initials(l.title));
}
function srcBadge(l) {
  const s = SRC[l.src];
  return el("span", { class: "srcbadge" }, el("span", { class: "sq", style: "background:" + s.c1 }, s.short), s.name);
}
function scoreBadge(l) { return el("span", { class: "score" + ((l.score || 0) >= 9 ? " hi" : "") }, (l.score ?? "?") + "/10"); }
function verdictPill(l) { return el("span", { class: "pill " + (VCLASS[l.verdict] || "muted") }, l.verdict || "Review"); }
function compCell(l) {
  const c = (l.competition || "").toLowerCase();
  const cls = ["low", "medium", "high"].includes(c) ? c : "na";
  return el("span", { class: "comp " + cls }, cls === "na" ? "n/a" : c);
}
function subLine(l) {
  const parts = [l.src === "reddit" ? (l.source || "Reddit") : SRC[l.src].name];
  if (!l.is_job) parts.push((l.comment_count || 0) + " comments");
  parts.push(ago(l.ms));
  const st = statusOf(l);
  if (st !== "new") parts.push(STATUS_PILL[st][1]);
  return parts.join(" · ");
}
function leadCell(l, sub) {
  return el("div", { class: "lead-cell" }, avatar(l),
    el("div", { style: "min-width:0" }, el("div", { class: "lead-title" }, l.title || "(no title)"), el("div", { class: "lead-sub" }, sub)));
}
function clickRow(l, cells) {
  const tr = el("tr", { class: "click" + (statusOf(l) !== "new" ? " done" : "") + (state.open === l.link ? " sel" : ""), tabindex: "0" },
    ...cells.map(c => el("td", {}, c)));
  tr.addEventListener("click", () => openLead(l));
  tr.addEventListener("keydown", e => { if (e.key === "Enter") openLead(l); });
  return tr;
}
function emptyRow(cols, title, text) {
  const box = el("div", { class: "empty" });
  box.innerHTML = EMPTY_ICON;   // fixed icon only - no data
  box.append(el("h3", {}, title), el("p", {}, text));
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
  node.title = "vs the previous period";
}

// time buckets for the line charts (days, or weeks for long ranges)
function makeBuckets(rangeDays) {
  const oldest = leads.length ? leads[leads.length - 1].ms : Date.now();
  const days = rangeDays || Math.max(28, Math.ceil((Date.now() - oldest) / DAY) + 1);
  const size = days <= 31 ? 1 : 7;
  const n = Math.min(Math.ceil(days / size), 52);
  const list = [];
  for (let i = n - 1; i >= 0; i--) {
    const start = startOfDay(i * size + size - 1);
    list.push({ start, end: startOfDay(i * size - 1) });
  }
  return { list, size };
}
function countIn(buckets, times) { return buckets.list.map(b => times.filter(t => t >= b.start && t < b.end).length); }
function axisLabels(node, buckets) {
  const n = buckets.list.length;
  const idx = n <= 7 ? [...Array(n).keys()] : [0, Math.round((n - 1) / 3), Math.round(2 * (n - 1) / 3), n - 1];
  node.replaceChildren(...idx.map(i => {
    const d = new Date(buckets.list[i].start);
    return el("span", {}, buckets.size === 1 && n <= 7 ? d.toLocaleDateString(undefined, { weekday: "short" }) : fmtDay(d));
  }));
}
let gradId = 0;
function lineChart(box, buckets, series, H) {
  const W = Math.max(box.clientWidth, 240), n = buckets.list.length;
  const max = Math.max(1, ...series.flatMap(s => s.values));
  const top = 12, bottom = H - 4;
  const x = i => n === 1 ? W / 2 : 5 + i * (W - 10) / (n - 1);
  const y = v => bottom - (v / max) * (bottom - top);
  const root = svg("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": series.map(s => s.name).join(" and ") + " over time" });
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
  // hover: native tooltip per point
  buckets.list.forEach((b, i) => {
    const w = n === 1 ? W : W / (n - 1);
    const hit = svg("rect", { x: x(i) - w / 2, y: 0, width: w, height: H, fill: "transparent" });
    const t = svg("title", {});
    const label = buckets.size === 1 ? fmtDay(new Date(b.start)) : "Week of " + fmtDay(new Date(b.start));
    t.textContent = label + "\n" + series.map(s => s.name + ": " + s.values[i]).join("\n");
    hit.append(t); root.append(hit);
  });
  box.replaceChildren(root);
}

// ---------- rail + topbar ----------
function renderChrome() {
  const last = runs[0];
  const ok = last && RUN_OK.has(last.status);
  const dotCls = !last ? "dot idle" : ok ? "dot" : "dot bad";
  $("engine-dot").className = dotCls;
  $("engine-big").textContent = last ? String(last.fetched ?? 0) : "—";
  $("engine-sub").textContent = last ? "fetched last run · " + ago(last.ms) : "waiting for the first run";
  $("c-leads").textContent = leads.filter(inRange).length;
  $("c-replies").textContent = leads.filter(l => ["replied", "applied"].includes(statusOf(l))).length;
  $("c-won").textContent = leads.filter(l => statusOf(l) === "won").length;
  const todo = leads.filter(isTodo).length;
  $("bell-badge").hidden = !todo;
  $("bell-badge").textContent = todo > 99 ? "99+" : todo;
  $("bell").title = todo + " lead" + (todo === 1 ? "" : "s") + " to act on";
  const mins = 60 - new Date().getMinutes();
  $("live-dot").className = dotCls;
  $("live-text").textContent = last && !ok ? "Last run: " + (RUN_STATUS[last.status] || ["", last.status || "unknown"])[1] : "Next scan in ~" + mins + " min";
  $("foot-dot").className = dotCls;
  $("foot-text").textContent = last ? (ok ? "Engine live" : "Engine needs a look") + " · last run " + ago(last.ms) : "Waiting for the first run";
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("on", b.dataset.s === state.screen));
  document.querySelectorAll(".screen").forEach(s => s.classList.toggle("on", s.id === "s-" + state.screen));
}

// ---------- leads screen ----------
function chipOk(l) {
  switch (state.chip) {
    case "all": return true;
    case "todo": return isTodo(l);
    case "reddit": return l.src === "reddit";
    case "jobs": return l.src !== "reddit";
    default: return VCLASS[l.verdict] === state.chip;
  }
}
function renderLeads() {
  const ranged = leads.filter(inRange);
  const label = state.range ? state.range + " days" : "all time";
  $("found-title").textContent = "Leads found · " + label;
  $("found-num").textContent = ranged.length;
  const prev = state.range ? leads.filter(l => l.ms >= startOfDay(2 * state.range - 1) && l.ms < rangeStart()).length : 0;
  trendEl($("found-trend"), ranged.length, prev);
  const b = makeBuckets(state.range);
  lineChart($("found-chart"), b, [{ name: "Leads", color: "#3d82f6", area: true, values: countIn(b, leads.map(l => l.ms)) }], 96);
  axisLabels($("found-axis"), b);

  const counts = Object.fromEntries(SRC_ORDER.map(k => [k, ranged.filter(l => l.src === k).length]));
  const maxC = Math.max(1, ...Object.values(counts));
  $("by-source").replaceChildren(...SRC_ORDER.map(k => el("div", { class: "bar-row" },
    el("span", { class: "lab", title: SRC[k].name }, k === "wwr" ? "We Work Rem." : SRC[k].name),
    el("div", { class: "bar-track" }, el("div", { class: "bar-fill", style: `width:${counts[k] / maxC * 100}%;background:${SRC[k].c1}` })),
    el("span", { class: "num" }, String(counts[k])))));

  const worth = ranged.filter(l => l.verdict === "Apply" || l.verdict === "Reply").length;
  const p = pct(worth, ranged.length);
  const ring = svg("svg", { width: 54, height: 54, viewBox: "0 0 36 36", role: "img", "aria-label": p + " percent worth acting on", style: "flex:0 0 auto" });
  ring.append(svg("circle", { cx: 18, cy: 18, r: 15.5, fill: "none", stroke: "#1a2230", "stroke-width": 4 }));
  if (p > 0) ring.append(svg("circle", { cx: 18, cy: 18, r: 15.5, fill: "none", stroke: "#35c08a", "stroke-width": 4, "stroke-linecap": "round", "stroke-dasharray": `${(p / 100 * 97.4).toFixed(1)} 97.4`, transform: "rotate(-90 18 18)" }));
  const txt = svg("text", { x: 18, y: 21, "text-anchor": "middle", fill: "#eef2f8", "font-size": 9, "font-weight": 700, "font-family": "monospace" });
  txt.textContent = p + "%"; ring.append(txt);
  $("hit-rate").replaceChildren(ring, el("div", {},
    el("div", { class: "bignum", style: "color:var(--apply);font-size:1.3rem" }, worth + "/" + ranged.length),
    el("div", { style: "font-size:0.74rem;color:var(--soft)" }, "worth applying or replying")));

  const scores = [7, 8, 9, 10], sc = scores.map(s => ranged.filter(l => (l.score || 0) === s).length);
  const maxS = Math.max(1, ...sc), top = Math.max(...sc);
  $("spread").replaceChildren(...scores.map((s, i) => el("div", { class: "col" + (sc[i] && sc[i] === top ? " hot" : ""), title: sc[i] + " leads scored " + s },
    el("div", { class: "b", style: `height:${sc[i] / maxS * 82}%` }), el("span", { class: "cl" }, String(s)))));
  const note = $("spread-note");
  if (ranged.length) {
    const best = scores[sc.indexOf(top)];
    note.replaceChildren("Most leads land ", el("strong", { style: "color:var(--ink)" }, best + "/10"), " in this period.");
  } else note.textContent = "No leads in this period yet.";

  const q = state.q.trim().toLowerCase();
  // sabse zyada score upar; barabar score ho to nayi lead pehle
  const list = ranged.filter(l => chipOk(l) && (!q || [l.title, l.note, l.source, l.reason].join(" ").toLowerCase().includes(q)))
    .sort((a, b) => (b.score || 0) - (a.score || 0) || b.ms - a.ms);
  document.querySelectorAll("#filters .chip").forEach(c => c.classList.toggle("on", c.dataset.f === state.chip));
  $("result").textContent = list.length + (list.length === 1 ? " lead" : " leads");
  $("showing").textContent = `Showing ${list.length} of ${ranged.length} leads · ${state.range ? "last " + label : label}`;
  const body = $("tbody");
  if (!leads.length) body.replaceChildren(emptyRow(5, "No leads yet", "Leads show up here after the first hourly run that emails some."));
  else if (!list.length) body.replaceChildren(emptyRow(5, "Nothing matches", "Try another filter, a longer date range, or clear the search."));
  else body.replaceChildren(...list.map(l => clickRow(l, [leadCell(l, subLine(l)), scoreBadge(l), srcBadge(l), compCell(l), verdictPill(l)])));
}

// ---------- sources screen ----------
function renderSources() {
  const since = startOfDay(29);
  const n30 = k => leads.filter(l => l.src === k && l.ms >= since).length;
  const subs = CONFIG.reddit_subs || [], wwr = CONFIG.wwr_feeds || [];
  const card = (k, status, kws) => el("div", { class: "srccard" },
    el("div", { class: "top" }, el("span", { class: "ic", style: "background:" + SRC[k].c1 }, SRC[k].short),
      el("div", {}, el("div", { class: "nm" }, SRC[k].name), el("div", { class: "st" }, el("span", { class: "dot" }), status))),
    el("div", { class: "kwrow" }, ...kws.map(w => el("span", { class: "kw" }, w))),
    el("div", { class: "meta" }, el("span", {}, "Leads · last 30 days"), el("b", {}, String(n30(k)))));
  $("srcgrid").replaceChildren(
    card("reddit", "Active · " + subs.length + " subreddits", subs.map(s => "r/" + s)),
    card("larajobs", "Active · RSS feed", ["all Laravel jobs"]),
    card("wwr", "Active · " + wwr.length + " feeds", wwr));
  $("queries").replaceChildren(...(CONFIG.reddit_queries || []).map(w => el("span", { class: "kw" }, w)));
  $("rules").textContent = `Every post is scored 1–10 by AI for buying intent and fit with Laravel / PHP / Vue. ` +
    `Only posts scoring ${CONFIG.threshold ?? 7}+ become leads, and jobs locked to one country are capped low. ` +
    `Foxlead checks every hour and scores up to ${CONFIG.max_new ?? 80} new posts per run.`;
}

// ---------- replies + won ----------
function marked(l) { const t = statusRec(l).t; return t ? ago(t) : "—"; }
function statusPill(l) { const [cls, label] = STATUS_PILL[statusOf(l)] || ["muted", "New"]; return el("span", { class: "pill " + cls }, label); }
function renderReplies() {
  const list = leads.filter(l => ["replied", "applied"].includes(statusOf(l))).sort((a, b) => statusRec(b).t - statusRec(a).t);
  $("replies-body").replaceChildren(...(list.length ? list.map(l => clickRow(l, [leadCell(l, subLine(l)), el("span", { class: "mono" }, marked(l)), srcBadge(l), statusPill(l)]))
    : [emptyRow(4, "No replies yet", "Open a lead and mark it Replied or Applied — it will be tracked here.")]));
}
function renderWon() {
  const won = leads.filter(l => statusOf(l) === "won").sort((a, b) => statusRec(b).t - statusRec(a).t);
  const tried = leads.filter(l => ["replied", "applied", "won"].includes(statusOf(l))).length;
  const avg = won.length ? (won.reduce((s, l) => s + (l.score || 0), 0) / won.length).toFixed(1) : "—";
  $("won-cards").replaceChildren(
    statCard("Clients won", String(won.length), "all time", "var(--apply)"),
    statCard("Reply → win", tried ? pct(won.length, tried) + "%" : "—", tried + " replied or applied · " + won.length + " won"),
    statCard("Avg. score won", avg, "out of 10"));
  $("won-body").replaceChildren(...(won.length ? won.map(l => clickRow(l, [leadCell(l, subLine(l)), el("span", { class: "mono" }, marked(l)), srcBadge(l), el("span", { class: "pill apply" }, "Client")]))
    : [emptyRow(4, "No wins yet", "When a lead turns into a client, open it and mark it Won.")]));
}

// ---------- reports ----------
function renderReports() {
  const b = makeBuckets(30);
  const acted = leads.filter(l => ["replied", "applied", "won"].includes(statusOf(l)) && statusRec(l).t).map(l => statusRec(l).t);
  lineChart($("rep-chart"), b, [
    { name: "Leads found", color: "#3d82f6", area: true, values: countIn(b, leads.map(l => l.ms)) },
    { name: "Replied, applied or won", color: "#35c08a", values: countIn(b, acted) }], 200);
  axisLabels($("rep-axis"), b);
  const since = startOfDay(29), cur = leads.filter(l => l.ms >= since);
  const prev = leads.filter(l => l.ms >= startOfDay(59) && l.ms < since).length;
  trendEl($("rep-trend"), cur.length, prev);
  const actedCur = cur.filter(l => ["replied", "applied", "won"].includes(statusOf(l))).length;
  const bySrc = SRC_ORDER.map(k => [k, cur.filter(l => l.src === k).length]).sort((a, b) => b[1] - a[1])[0];
  const trendNote = prev ? (cur.length >= prev ? "▲ " : "▼ ") + Math.abs(Math.round((cur.length - prev) / prev * 100)) + "% vs previous 30 days" : "last 30 days";
  $("rep-cards").replaceChildren(
    statCard("Total leads", String(cur.length), trendNote),
    statCard("Acted on", String(actedCur), pct(actedCur, cur.length) + "% of leads replied, applied or won"),
    statCard("Best source", bySrc && bySrc[1] ? SRC[bySrc[0]].name : "—", bySrc && bySrc[1] ? bySrc[1] + " leads" : "no leads yet", bySrc && bySrc[1] ? "#6fe0b0" : ""));
  $("rep-cards").lastChild.querySelector(".bignum").style.fontSize = "1.1rem";
  $("runs-body").replaceChildren(...(runs.length ? runs.slice(0, 12).map(r => {
    const [cls, label] = RUN_STATUS[r.status] || ["muted", r.status || "Unknown"];
    const d = new Date(r.ms);
    return el("tr", {}, el("td", { class: "mono" }, fmtDay(d) + ", " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })),
      el("td", {}, el("span", { class: "pill " + cls }, label)),
      ...[r.fetched, r.new, r.scored, r.leads].map(v => el("td", { class: "mono" }, String(v ?? 0))));
  }) : [emptyRow(6, "No runs yet", "Each hourly run is logged here.")]));
}

// ---------- detail panel ----------
const panel = $("panel"), scrim = $("scrim");
let lastFocus = null;
function openLead(l) { lastFocus = document.activeElement; state.open = l.link; renderAll(); panel.classList.add("show"); scrim.classList.add("show"); $("p-close").focus(); }
function closeLead() {
  if (!state.open) return;
  state.open = null; panel.classList.remove("show"); scrim.classList.remove("show"); renderAll();
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus();
}
function renderPanel() {
  const l = leads.find(x => x.link === state.open);
  if (!l) return;
  $("p-ava").replaceWith(Object.assign(avatar(l, true), { id: "p-ava" }));
  const v = $("p-verdict"); v.className = "pill " + (VCLASS[l.verdict] || "muted"); v.textContent = l.verdict || "Review";
  $("p-title").textContent = l.title || "(no title)";
  $("p-meta").replaceChildren(scoreBadge(l), srcBadge(l), el("span", { class: "lead-sub", style: "margin:0" }, "found " + ago(l.ms)));
  const st = statusOf(l);
  const chips = STATUS_LIST.map(([s, label]) => {
    const c = el("button", { type: "button", class: "chip" + (s === st ? " on" : "") }, label);
    c.addEventListener("click", () => setStatus(l, s));
    return c;
  });
  const checkMeta = l.is_job ? "Job listing" : (l.comment_count || 0) + " comments · " + (l.competition || "unknown") + " competition";
  $("p-body").replaceChildren(
    el("div", { class: "sec" }, el("p", { class: "sec-label" }, l.is_job ? "The job" : "The post"),
      el("div", { class: "posttext" }, l.text || "The text wasn't saved for this lead — open it to read the full post.")),
    el("div", { class: "sec" }, el("p", { class: "sec-label" }, "Why Foxlead flagged it"),
      el("div", { class: "reason" }, l.reason || `Scored ${l.score}/10 for your Laravel / PHP / Vue stack.`)),
    el("div", { class: "sec" }, el("p", { class: "sec-label" }, l.is_job ? "Before you apply" : "Thread check"),
      el("div", { class: "check" }, el("div", { class: "meta" }, checkMeta), l.note || "No extra notes.")),
    el("div", { class: "sec" }, el("p", { class: "sec-label" }, "Your status"), el("div", { class: "status-chips" }, ...chips),
      el("div", { class: "hint" }, "Saved in this browser only.")));
  const target = l.is_job ? "applied" : "replied";
  const mark = $("p-mark");
  mark.querySelector("span").textContent = st === target ? "Marked " + target : "Mark " + target;
  mark.onclick = () => setStatus(l, st === target ? "new" : target);
  const open = $("p-open");
  open.href = safeUrl(l.link);
  open.querySelector("span").textContent = l.is_job ? "Open job" : "Open post";
}

// ---------- wiring ----------
function renderAll() {
  renderChrome();
  if (state.screen === "leads") renderLeads();
  if (state.screen === "sources") renderSources();
  if (state.screen === "replies") renderReplies();
  if (state.screen === "won") renderWon();
  if (state.screen === "reports") renderReports();
  if (state.open) renderPanel();
}
$("nav").addEventListener("click", e => { const b = e.target.closest("button"); if (b) { state.screen = b.dataset.s; renderAll(); } });
$("filters").addEventListener("click", e => { const c = e.target.closest(".chip"); if (c) { state.chip = c.dataset.f; renderLeads(); } });
$("q").addEventListener("input", e => { state.q = e.target.value; state.screen = "leads"; renderAll(); });
$("range").addEventListener("change", e => { state.range = Number(e.target.value); renderAll(); });
$("bell").addEventListener("click", () => { state.screen = "leads"; state.chip = "todo"; renderAll(); });
$("p-close").addEventListener("click", closeLead);
scrim.addEventListener("click", closeLead);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeLead(); });
let resizeTimer;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 120); });
renderAll();
</script>
</body>
</html>
"""


def read_constants(path, names):
    """Doosri file ko CHALAYE baghair (sirf padh kar) uske simple constants nikaalo.
    Is tarah Sources screen hamesha fetch_posts.py / classify_posts.py se match karta hai."""
    found = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return found
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id in names):
            try:
                found[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return found


# -------- history.json padho (na ho to khaali dashboard) --------
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
else:
    history = {"runs": [], "leads": []}

print(f"history.json: {len(history.get('leads', []))} leads, {len(history.get('runs', []))} runs.")

fetch_cfg = read_constants("fetch_posts.py", {"reddit_subs", "reddit_queries", "wwr_feeds"})
classify_cfg = read_constants("classify_posts.py", {"THRESHOLD"})
run_cfg = read_constants("run_all.py", {"MAX_NEW_PER_RUN"})

data = {
    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "runs": history.get("runs", [])[-200:],   # page halka rahe - aakhri 200 runs kaafi hain
    "leads": history.get("leads", []),
    "config": {
        "reddit_subs": fetch_cfg.get("reddit_subs", []),
        "reddit_queries": fetch_cfg.get("reddit_queries", []),
        "wwr_feeds": [k.replace("WWR-", "") for k in fetch_cfg.get("wwr_feeds", {})],
        "threshold": classify_cfg.get("THRESHOLD", 7),
        "max_new": run_cfg.get("MAX_NEW_PER_RUN", 80),
    },
}
# JSON <script> ke andar jaata hai - har "<" ko < bana do taake koi title
# (jaise "</script>") script ko band na kar sake. JS ke liye matlab wahi rehta hai.
data_json = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

os.makedirs(OUT_DIR, exist_ok=True)
with open(OUT_FILE, "w", encoding="utf-8") as f:
    f.write(PAGE.replace("__DATA__", data_json))

print(f"Dashboard ban gaya: {OUT_FILE} (double-click karke browser mein kholo).")
