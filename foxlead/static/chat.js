// chat.js - "Ask Foxlead" chatbot. Jawab hamesha textContent se dikhaye jaate hain
// (HTML kabhi nahi), kyunki un mein Reddit ke titles bhi ho sakte hain.
// Saath mein: nayi leads ka number + salaam, lead ke baare mein poochna, ek-click sawal,
// awaaz se poochna / jawab sunna, "Put in draft", aur profile ke mashwaray.
(() => {
  const $c = id => document.getElementById(id);
  const fab = $c("chat-fab"), box = $c("chat"), log = $c("chat-log"), form = $c("chat-form");
  const input = $c("chat-input"), send = $c("chat-send"), limitEl = $c("chat-limit"), suggest = $c("chat-suggest");
  const badge = $c("fab-badge"), greet = $c("chat-greet"), about = $c("chat-about"), mic = $c("chat-mic");
  let loaded = false, busy = false;
  let lead = null;            // lead panel se "Ask Foxlead" - abhi jis lead ke baare mein baat ho rahi hai

  // localStorage private window mein band ho sakta hai - tab bhi kuch na toote
  const store = {
    get: k => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* koi baat nahi */ } },
  };
  const SEEN = "foxlead-chat-seen";
  if (!store.get(SEEN)) fab.classList.add("attn");     // pehli baar tak button blink kare

  // ---------- awaazein: bhejne par "pop", jawab par "ding", nayi leads par chime ----------
  // Browser khud banata hai (Web Audio) - koi file nahi. User ne 🔔 band kiya ho to chup.
  const soundBtn = $c("chat-sound"), speakBtn = $c("chat-speak");
  let soundOn = store.get("foxlead-chat-sound") !== "0";      // pehle se on
  let speakAll = store.get("foxlead-chat-speak") === "1";     // har jawab khud bolo (pehle se off)
  let audio = null;
  function play(notes) {
    if (!soundOn) return;
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      let at = audio.currentTime + 0.01;
      for (const [freq, len, type = "sine", slideTo] of notes) {      // slideTo: aawaz upar/neeche phisle (robot jaisi)
        const osc = audio.createOscillator(), gain = audio.createGain();
        osc.type = type; osc.frequency.setValueAtTime(freq, at);
        if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, at + len);
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(type === "sine" ? 0.3 : 0.12, at + 0.015);   // square/saw tez hoti hain - kam rakho
        gain.gain.exponentialRampToValueAtTime(0.0001, at + len);
        osc.connect(gain).connect(audio.destination);
        osc.start(at); osc.stop(at + len + 0.02);
        at += len * 0.75;
      }
    } catch { /* purana browser ya awaaz band - koi baat nahi */ }
  }
  const SOUND = {
    send: [[660, 0.07]],
    reply: [[880, 0.12], [1320, 0.2]],
    greet: [[784, 0.12], [988, 0.12], [1175, 0.22]],
    // robot ki "beep-boop" - dashboard khulne par
    robot: [[220, 0.12, "square", 440], [660, 0.09, "square"], [440, 0.09, "square"], [880, 0.14, "sawtooth", 1320], [1320, 0.28, "sine", 990]],
    error: [[330, 0.14], [247, 0.22]],
  };
  function showToggles() {
    soundBtn.setAttribute("aria-pressed", String(soundOn));
    soundBtn.title = t(soundOn ? "Sounds on" : "Sounds off");
    speakBtn.setAttribute("aria-pressed", String(speakAll));
    speakBtn.title = t(speakAll ? "Reading answers aloud" : "Read answers aloud");
  }
  soundBtn.addEventListener("click", () => {
    soundOn = !soundOn; store.set("foxlead-chat-sound", soundOn ? "1" : "0"); showToggles(); play(SOUND.send);
    if (!soundOn) { stopSpeaking(); $c("voice-hint").hidden = true; }
  });
  speakBtn.addEventListener("click", () => {
    speakAll = !speakAll; store.set("foxlead-chat-speak", speakAll ? "1" : "0"); showToggles();
    if (!speakAll) stopSpeaking();
  });
  if (!window.speechSynthesis) speakBtn.hidden = true;
  let byVoice = false;            // sawal mic se aaya - to jawab bhi bol kar

  // ---------- awaaz: jawab sunna ----------
  const synth = window.speechSynthesis;
  let speakingBtn = null;
  function stopSpeaking() {
    if (synth) synth.cancel();
    if (speakingBtn) { speakingBtn.classList.remove("on"); speakingBtn.textContent = t("Listen"); speakingBtn = null; }
  }
  function speak(text, btn) {
    const same = speakingBtn === btn;
    stopSpeaking();
    if (same) return;                                  // dobara dabaya = band
    const u = new SpeechSynthesisUtterance(text);
    u.lang = /[؀-ۿ]/.test(text) ? "ur-PK" : "en-US";
    const voice = synth.getVoices().find(v => v.lang.replace("_", "-").toLowerCase().startsWith(u.lang.slice(0, 2)));
    if (voice) u.voice = voice;
    u.onend = u.onerror = () => { if (speakingBtn === btn) stopSpeaking(); };
    speakingBtn = btn; btn.classList.add("on"); btn.textContent = t("Stop");
    synth.speak(u);
  }

  // ---------- messages ----------
  function actBtn(label, onClick, primary) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = label;
    if (primary) b.className = "primary";
    b.addEventListener("click", () => onClick(b));
    return b;
  }
  function bubble(role, text, leadId) {
    const b = document.createElement("div");
    b.className = "msg " + role;
    b.textContent = text;
    b.dir = "auto";                      // Urdu ho ya English - sahi taraf se
    if (role === "assistant") {
      const acts = document.createElement("div");
      acts.className = "acts";
      if (leadId) acts.append(actBtn(t("Put in draft"), async btn => {
        btn.disabled = true;
        try {
          await api("/api/lead", { id: leadId, draft: text });
          window.dispatchEvent(new CustomEvent("foxlead:draft", { detail: { id: leadId, text } }));
          toast(t("Saved as this lead's draft."), null, null, "ok");
        } catch (e) { toast(t("Could not save: {e}", { e: e.message }), null, null, "err"); }
        finally { btn.disabled = false; }
      }, true));
      acts.append(actBtn(t("Copy"), async btn => {
        try { await navigator.clipboard.writeText(text); btn.textContent = t("Copied ✓"); } catch { btn.textContent = t("Select and copy"); }
        setTimeout(() => { btn.textContent = t("Copy"); }, 2000);
      }));
      if (synth) acts.append(actBtn(t("Listen"), btn => speak(text, btn)));
      b.append(acts);
    }
    log.append(b);
    log.scrollTop = log.scrollHeight;
    return b;
  }
  function typing() {
    const b = document.createElement("div");
    b.className = "msg typing";
    b.setAttribute("role", "status");
    b.setAttribute("aria-label", t("Thinking…"));
    b.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
    log.append(b);
    log.scrollTop = log.scrollHeight;
    return b;
  }
  function hello() {
    const h = document.createElement("div");
    h.className = "chat-hello";
    h.textContent = t("Hi! I know your profile and your leads. Ask me which lead to act on, to write a proposal or follow-up, how to price a job, or how to get better leads.");
    log.append(h);
  }
  // mashwaray (server se): "7 din kar dein", "hadd 6 kar dein" - ek click mein
  function tipCard(tip) {
    const key = "foxlead-tip-" + tip.id;
    if (store.get(key)) return;
    const c = document.createElement("div");
    c.className = "chat-tip";
    const p = document.createElement("div");
    p.textContent = tip.text;
    const acts = document.createElement("div");
    acts.className = "acts";
    acts.append(actBtn(tip.action, async btn => {
      if (tip.link) { location.href = tip.link; return; }
      btn.disabled = true;
      try {
        const r = await api("/api/profile/quick", tip.change);
        p.textContent = r.promoted ? t("Done — {n} more posts now count as leads.", { n: r.promoted })
          : r.scanning ? t("Done — Foxlead is scanning with the new setting.") : t("Done — saved.");
        acts.remove();
        store.set(key, "1");
        window.dispatchEvent(new CustomEvent("foxlead:refresh"));
      } catch (e) { btn.disabled = false; toast(e.message, null, null, "err"); }
    }, true), actBtn(t("Not now"), () => { store.set(key, "1"); c.remove(); }));
    c.append(p, acts);
    log.append(c);
  }
  function setLimit(used, limit) { limitEl.textContent = t("{left} of {limit} messages left today", { left: Math.max(0, limit - used), limit }); }

  // ek-click sawal - lead ke baare mein baat ho to us ke hisaab se
  function renderSuggest() {
    const qs = lead
      ? [t(lead.is_job ? "Write my application" : "Write my reply"), t("How much should I charge?"), t("Is this lead worth my time?")]
      : [t("What should I apply to today?"), t("Why am I getting few leads?"), t("Write a follow-up for my last application"), t("Give me today's summary in Urdu")];
    suggest.replaceChildren(...qs.map(q => { const b = document.createElement("button"); b.type = "button"; b.textContent = q; return b; }));
  }

  async function load() {
    try {
      const d = await api("/api/chat");
      log.replaceChildren();
      hello();
      (d.tips || []).forEach(tipCard);
      d.messages.forEach(m => bubble(m.role, m.content));
      setLimit(d.used, d.limit);
      loaded = true;
    } catch (e) { toast(e.message, null, null, "err"); }
  }
  function open(show) {
    box.hidden = !show; fab.hidden = show;
    fab.setAttribute("aria-expanded", String(show));
    if (show) {
      fab.classList.remove("attn");
      store.set(SEEN, "1");
      hideGreet();
      if (!loaded) load();
      input.focus();
    } else { stopSpeaking(); stopListening(); }
  }
  async function ask(text) {
    text = text.trim();
    if (!text || busy) return;
    busy = true; send.disabled = true;
    const leadId = lead ? lead.id : null;
    const voiced = byVoice; byVoice = false;
    stopSpeaking();
    play(SOUND.send);
    bubble("user", text);
    input.value = ""; input.style.height = "";
    const wait = typing();
    try {
      const r = await api("/api/chat", leadId ? { message: text, lead_id: leadId } : { message: text });
      wait.remove();
      const b = bubble("assistant", r.answer, leadId);
      setLimit(r.used, r.limit);
      play(SOUND.reply);
      const listen = [...b.querySelectorAll(".acts button")].find(x => x.textContent === t("Listen"));
      if ((speakAll || voiced) && listen) speak(r.answer, listen);      // awaaz mein sawal = awaaz mein jawab
    } catch (e) {
      wait.remove();
      play(SOUND.error);
      bubble("error", t("Sorry — {e}", { e: e.message })).className = "msg assistant error";
    } finally { busy = false; send.disabled = false; input.focus(); }
  }

  // ---------- lead ke baare mein (lead panel ka "Ask Foxlead" button) ----------
  function setLead(l) {
    lead = l ? { id: l.id, title: l.title, score: l.score, is_job: l.is_job } : null;
    about.hidden = !lead;
    if (lead) $c("chat-about-text").textContent = t("About: {title} · {score}/10", { title: lead.title, score: lead.score });
    input.placeholder = lead ? t("Ask about this lead…") : t("Ask about your leads…");
    renderSuggest();
  }
  window.chatAbout = l => { setLead(l); open(true); };
  $c("chat-about-x").addEventListener("click", () => { setLead(null); input.focus(); });

  // ---------- nayi leads: button par number + salaam ka bubble ----------
  function hideGreet() {
    if (!greet.hidden && greet.dataset.key) store.set(greet.dataset.key, "1");
    greet.hidden = true;
  }
  let firstData = true;
  window.chatNewLeads = (n, runTime) => {
    const first = firstData; firstData = false;
    badge.hidden = !n;
    badge.textContent = n > 9 ? "9+" : String(n);
    if (n && box.hidden) fab.classList.add("attn");
    const key = "foxlead-greet-" + (runTime || "");
    if (n && box.hidden && runTime && !store.get(key)) {
      greet.dataset.key = key;
      $c("chat-greet-text").textContent = n === 1 ? t("1 new lead from the latest scan — want to see it?")
        : t("{n} new leads from the latest scan — want the best one first?", { n });
      if (greet.hidden) play(SOUND.greet);       // browser pehli click se pehle awaaz rok sakta hai - tab chup
      greet.hidden = false;
    } else if (!n) greet.hidden = true;
    if (first) { helloLeads = n; maybeHello(); }     // dashboard khulte hi robot ki awaaz
  };

  // ---------- dashboard khulte hi: robot ki beep-boop + robot ki awaaz mein salaam ----------
  // Browser pehli click/tap se pehle awaaz nahi chalne deta. Tab button ke paas "Tap to hear" -
  // aur page par kahin bhi pehli click hote hi robot bolta hai.
  const hint = $c("voice-hint");
  let helloLeads = null, helloDone = false;
  function robotSay(text) {
    if (!synth) return;
    const u = new SpeechSynthesisUtterance(text);
    const urdu = /[\u0600-\u06FF]/.test(text);
    u.lang = urdu ? "ur-PK" : "en-US";
    u.pitch = 0.35; u.rate = 0.92;                     // neechi, thehri hui - robot jaisi
    const voices = synth.getVoices().filter(v => v.lang.replace("_", "-").toLowerCase().startsWith(urdu ? "ur" : "en"));
    const male = voices.find(v => /male|david|guy|daniel|fred|alex|google uk english male/i.test(v.name));
    if (male || voices[0]) u.voice = male || voices[0];
    synth.speak(u);
  }
  function robotHello() {
    if (helloDone || helloLeads === null || !soundOn) return;
    helloDone = true; hint.hidden = true;
    play(SOUND.robot);
    const name = (typeof ME !== "undefined" && ME.name ? ME.name.split(" ")[0] : "");
    const urduVoice = synth && synth.getVoices().some(v => v.lang.toLowerCase().startsWith("ur"));
    const ur = document.documentElement.lang === "ur" && urduVoice;    // Urdu awaaz na ho to English mein bolo (warna ajeeb lagta hai)
    const n = helloLeads;
    const text = ur
      ? `السلام علیکم ${name}۔ میں Foxlead ہوں۔ ` + (n ? `آپ کی ${n} نئی لیڈز ہیں۔` : "کچھ بھی پوچھیں۔")
      : `Hello ${name}. Foxlead here. ` + (n ? `You have ${n} new lead${n === 1 ? "" : "s"}.` : "I'm ready. Ask me anything.");
    setTimeout(() => robotSay(text), 900);             // pehle beep-boop, phir bolna
  }
  function maybeHello() {
    if (!soundOn || helloDone) return;
    const allowed = navigator.userActivation ? navigator.userActivation.hasBeenActive : false;
    if (allowed) robotHello(); else hint.hidden = false;
  }
  hint.addEventListener("click", robotHello);
  $c("chat-greet-go").addEventListener("click", () => { hideGreet(); setLead(null); open(true); ask(t("Which of my new leads should I look at first?")); });
  $c("chat-greet-x").addEventListener("click", hideGreet);

  // ---------- awaaz se poochna (mic) ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  function stopListening() { if (rec) rec.stop(); }
  if (SR) {
    mic.hidden = false;
    mic.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new SR();
      rec.lang = document.documentElement.lang === "ur" ? "ur-PK" : "en-US";
      rec.interimResults = true;
      const before = input.value.trim(), ph = input.placeholder;
      mic.classList.add("on"); mic.setAttribute("aria-label", t("Stop listening")); input.placeholder = t("Listening…");
      let heard = false;
      rec.onresult = e => {
        const said = [...e.results].map(r => r[0].transcript).join("");
        input.value = (before ? before + " " : "") + said;
        input.dispatchEvent(new Event("input"));
        heard = said.trim().length > 0;
      };
      rec.onerror = e => toast(e.error === "not-allowed" || e.error === "service-not-allowed"
        ? t("Allow microphone access to ask by voice.") : t("Couldn't hear that — try again."), null, null, "err");
      rec.onend = () => {
        rec = null;
        mic.classList.remove("on"); mic.setAttribute("aria-label", t("Speak your question")); input.placeholder = ph;
        if (heard && !before) { byVoice = true; ask(input.value); }      // sirf bol kar poocha - foran bhejo, jawab bhi bol kar
        else input.focus();
      };
      rec.start();
    });
  }

  fab.addEventListener("click", () => open(true));
  $c("chat-close").addEventListener("click", () => { open(false); fab.focus(); });
  $c("chat-clear").addEventListener("click", async () => {
    try { await api("/api/chat/clear", {}); log.replaceChildren(); hello(); } catch (e) { toast(e.message, null, null, "err"); }
  });
  form.addEventListener("submit", e => { e.preventDefault(); ask(input.value); });
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input.value); } });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 120) + "px"; });
  suggest.addEventListener("click", e => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !box.hidden) open(false); });
  renderSuggest();
  showToggles();

  // Browser pehli click/tap tak awaaz rok kar rakhta hai - pehli click par robot ka salaam
  const unlock = () => { if (audio && audio.state === "suspended") audio.resume(); robotHello(); };
  document.addEventListener("pointerdown", unlock, { once: true, capture: true });
  document.addEventListener("keydown", unlock, { once: true, capture: true });
  // nayi leads hain aur chat abhi tak nahi khola: har 3 minute baad yaad dilao (zyada se zyada 3 baar)
  let reminders = 0;
  setInterval(() => {
    if (reminders < 3 && box.hidden && !badge.hidden) { reminders++; play(SOUND.robot); }
  }, 3 * 60 * 1000);
})();
