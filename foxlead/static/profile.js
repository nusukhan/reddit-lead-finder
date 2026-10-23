// profile.js - field chuno to form us field ki ready-made values se bhar jaye
// (user phir apni marzi se badal sakta hai).
const PROFESSIONS = JSON.parse(document.getElementById("professions-data").textContent);
const form = document.getElementById("profile-form");
const field = name => form.elements.namedItem(name);   // form.title jaisa naam form ki apni property se takrata hai

form.querySelectorAll('input[name="profession"]').forEach(radio => {
  radio.addEventListener("change", () => {
    const p = PROFESSIONS.find(x => x.id === radio.value);
    if (!p) return;
    field("title").value = p.id === "custom" ? "" : p.label;
    field("skills").value = p.skills;
    field("ideal_client").value = p.ideal_client;
    field("subreddits").value = p.subreddits.join(", ");
    field("keywords").value = p.keywords.join(", ");
    form.querySelectorAll('input[name="feeds"]').forEach(cb => { cb.checked = p.feeds.includes(cb.value); });
    field(p.id === "custom" ? "title" : "skills").focus();
  });
});

// auto-scan: "kis baje" sirf "din mein ek baar" ke saath; browser ka time zone saath bhejo
const every = document.getElementById("scan_every"), hourField = document.getElementById("scan-hour-field");
const showHour = () => { hourField.hidden = every.value !== "24"; };
every.addEventListener("change", showHour);
showHour();
try {
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (tz) {
    document.getElementById("timezone").value = tz;
    const line = document.getElementById("tz-line");
    line.textContent = line.textContent.replace(/[^:：]*$/, " " + tz);
  }
} catch (e) { /* purana browser - server wala time zone hi rahe */ }
