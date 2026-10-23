// chat.js - "Ask Foxlead" chatbot. Jawab hamesha textContent se dikhaye jaate hain
// (HTML kabhi nahi), kyunki un mein Reddit ke titles bhi ho sakte hain.
(() => {
  const fab = document.getElementById("chat-fab"), box = document.getElementById("chat");
  const log = document.getElementById("chat-log"), form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input"), send = document.getElementById("chat-send");
  const limitEl = document.getElementById("chat-limit"), suggest = document.getElementById("chat-suggest");
  let loaded = false, busy = false;

  function bubble(role, text) {
    const b = document.createElement("div");
    b.className = "msg " + role;
    b.textContent = text;
    b.dir = "auto";                      // Urdu ho ya English - sahi taraf se
    if (role === "assistant") {
      const c = document.createElement("button");
      c.type = "button"; c.className = "copy"; c.textContent = t("Copy");
      c.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(text); c.textContent = t("Copied ✓"); } catch { c.textContent = t("Select and copy"); }
        setTimeout(() => { c.textContent = t("Copy"); }, 2000);
      });
      b.append(c);
    }
    log.append(b);
    log.scrollTop = log.scrollHeight;
    return b;
  }
  function hello() {
    const h = document.createElement("div");
    h.className = "chat-hello";
    h.textContent = t("Hi! I know your profile and your leads. Ask me which lead to act on, to write a proposal or follow-up, how to price a job, or how to get better leads. You can write in English, Urdu or Roman Urdu.");
    log.append(h);
  }
  function setLimit(used, limit) { limitEl.textContent = t("{left} of {limit} messages left today", { left: Math.max(0, limit - used), limit }); }

  async function load() {
    try {
      const d = await api("/api/chat");
      log.replaceChildren();
      hello();
      d.messages.forEach(m => bubble(m.role, m.content));
      suggest.hidden = d.messages.length > 0;
      setLimit(d.used, d.limit);
      loaded = true;
    } catch (e) { toast(e.message, null, null, "err"); }
  }
  function open(show) {
    box.hidden = !show; fab.hidden = show;
    fab.setAttribute("aria-expanded", String(show));
    if (show) { if (!loaded) load(); input.focus(); }
  }
  async function ask(text) {
    text = text.trim();
    if (!text || busy) return;
    busy = true; send.disabled = true; suggest.hidden = true;
    bubble("user", text);
    input.value = ""; input.style.height = "";
    const wait = bubble("thinking", t("Thinking…"));
    try {
      const r = await api("/api/chat", { message: text });
      wait.remove();
      bubble("assistant", r.answer);
      setLimit(r.used, r.limit);
    } catch (e) {
      wait.remove();
      bubble("assistant", t("Sorry — {e}", { e: e.message })).classList.add("error");
    } finally { busy = false; send.disabled = false; input.focus(); }
  }

  fab.addEventListener("click", () => open(true));
  document.getElementById("chat-close").addEventListener("click", () => { open(false); fab.focus(); });
  document.getElementById("chat-clear").addEventListener("click", async () => {
    try { await api("/api/chat/clear", {}); log.replaceChildren(); hello(); suggest.hidden = false; } catch (e) { toast(e.message, null, null, "err"); }
  });
  form.addEventListener("submit", e => { e.preventDefault(); ask(input.value); });
  input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input.value); } });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 120) + "px"; });
  suggest.addEventListener("click", e => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !box.hidden) open(false); });
})();
