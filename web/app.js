/* Threshold — the browser half.
 *
 * Three jobs live here and nothing else: hold the WebRTC peer connection
 * (only the browser can), grab frames off it, and render what the server
 * says. No decisions are made in this file — every verdict shown comes from
 * the server, so the interface cannot drift from the rules engine.
 *
 * The Ring token is posted once and never stored in JavaScript state beyond
 * that request; the server keeps it and signs the WHEP exchange itself.
 */

const $ = (id) => document.getElementById(id);
const api = async (path, options = {}) => {
  const res = await fetch(path, options);
  const type = res.headers.get("content-type") || "";
  const body = type.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((body && body.error) || `request failed (${res.status})`);
  return body;
};

const state = { connected: false, lastDecisions: [], watching: null, countdown: null };

/* ---------- theme ---------- */
const themeBtn = $("theme");
const storedTheme = (() => {
  try { return localStorage.getItem("threshold-theme"); } catch { return null; }
})();
if (storedTheme) document.documentElement.dataset.theme = storedTheme;
const syncThemeButton = () => {
  const dark = document.documentElement.dataset.theme === "dark";
  themeBtn.textContent = dark ? "Light" : "Dark";
  themeBtn.setAttribute("aria-pressed", String(dark));
};
themeBtn.addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme === "dark";
  document.documentElement.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("threshold-theme", dark ? "light" : "dark"); } catch { /* private mode */ }
  syncThemeButton();
});
syncThemeButton();

/* ---------- speech ---------- */
function speak(text) {
  if (!$("speak").checked || !("speechSynthesis" in window) || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  window.speechSynthesis.speak(utterance);
}

/* ---------- connection ---------- */
$("token-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = $("token").value.trim();
  try {
    const info = await api("/api/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    state.connected = true;
    $("token").value = "";
    renderDevice(info);
    await refresh();
  } catch (err) {
    $("token-state").textContent = err.message;
  }
});

function renderDevice(info) {
  const facts = $("device-facts");
  const caps = info.capabilities || {};
  facts.hidden = false;
  facts.innerHTML = `
    <dt>Device</dt><dd>${escape(info.device.name)}</dd>
    <dt>Status</dt><dd>${info.online ? "online" : "offline"}</dd>
    <dt>Video</dt><dd>${caps.max_resolution || "?"}p ${(caps.codecs || []).join(", ")}</dd>
    <dt>Motion zones</dt><dd>${(info.zones || []).length}</dd>
    <dt>Sensors</dt><dd>${(caps.sensors || []).length ? caps.sensors.join(", ") : "none reported"}</dd>`;
  $("mode-badge").hidden = !info.offline;
}

function renderToken(token) {
  const el = $("token-state");
  if (!token.present) { el.textContent = "Not connected. Generate a token in the Ring Playground and paste it above."; return; }
  if (token.expired) { el.textContent = "The token has expired. Generate a new one in the Playground."; return; }
  const minutes = Math.floor(token.seconds_left / 60);
  const seconds = String(token.seconds_left % 60).padStart(2, "0");
  const scopes = token.read_only ? " This token is read-only, so Threshold can watch but never act on the door." : "";
  el.textContent = `Connected. Token expires in ${minutes}:${seconds}.${scopes}`;
}

/* ---------- live view (WHEP) ---------- */
$("stream").addEventListener("click", async () => {
  const button = $("stream");
  button.disabled = true;
  button.textContent = "Connecting…";
  try {
    const pc = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });
    pc.ontrack = (event) => { $("video").srcObject = event.streams[0]; };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    // Wait for ICE rather than trickling: Ring's WHEP endpoint takes one shot.
    await new Promise((resolve) => {
      if (pc.iceGatheringState === "complete") return resolve();
      const done = () => { if (pc.iceGatheringState === "complete") { pc.removeEventListener("icegatheringstatechange", done); resolve(); } };
      pc.addEventListener("icegatheringstatechange", done);
      setTimeout(resolve, 2500);
    });

    const answer = await fetch("/api/whep", {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: pc.localDescription.sdp,
    });
    if (!answer.ok) throw new Error(await answer.text());
    await pc.setRemoteDescription({ type: "answer", sdp: await answer.text() });

    button.textContent = "Live";
  } catch (err) {
    button.disabled = false;
    button.textContent = "Start live view";
    $("token-state").textContent = `Live view failed: ${err.message}`;
  }
});

function grabFrame() {
  const video = $("video");
  if (!video.videoWidth) return null;
  const canvas = $("grab");
  const width = 960;
  canvas.width = width;
  canvas.height = Math.round((video.videoHeight / video.videoWidth) * width);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.7);
}

/* ---------- observe ---------- */
async function observe(trigger = "manual") {
  const button = $("look");
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = "Looking…";
  try {
    const frame = grabFrame();
    // With no stream yet there is still something worth doing: the server's
    // fallback provider answers, clearly marked, rather than erroring.
    const result = await api("/api/observe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ frames: [frame || "placeholder"], trigger }),
    });
    renderObservation(result);
    await refresh();
  } catch (err) {
    $("announcement").textContent = err.message;
  } finally {
    button.disabled = false;
    button.textContent = previous;
  }
}

$("look").addEventListener("click", () => observe("manual"));

$("watch").addEventListener("change", (event) => {
  if (event.target.checked) {
    state.watching = setInterval(() => observe("motion"), 15000);
  } else {
    clearInterval(state.watching);
    state.watching = null;
  }
});

function renderObservation(result) {
  const { narration, decisions, event, anomalies, latency_ms: latency, provider_attempts: attempts } = result;
  $("announcement").textContent = narration.announcement;
  $("reason").textContent = narration.reason;
  const caption = $("caption");
  caption.hidden = false;
  caption.textContent = narration.caption;

  const provider = event.provider || "none";
  const anomalyNote = anomalies.length ? ` · ${anomalies.length} anomaly noted` : "";
  const rungs = (attempts || []).filter((a) => !a.ok).map((a) => a.provider);
  const skipped = rungs.length ? ` · skipped ${rungs.join(", ")}` : "";
  $("latency").textContent = `${Math.round(latency)} ms · described by ${provider}${skipped}${anomalyNote}`;

  state.lastDecisions = decisions;
  speak(narration.announcement);
}

/* ---------- rules ---------- */
$("rule-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("rule-text");
  const text = input.value.trim();
  if (!text) return;
  try {
    await api("/api/rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    input.value = "";
    await refresh();
  } catch (err) {
    $("token-state").textContent = err.message;
  }
});

function renderRules(rules) {
  const list = $("rules");
  list.innerHTML = "";
  const byId = new Map(state.lastDecisions.map((d) => [d.rule_id, d]));

  rules.forEach((rule) => {
    const decision = byId.get(rule.id);
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="rule-head">
        <span class="rule-name">${escape(rule.name)}</span>
        ${decision ? `<span class="verdict ${decision.fired ? "fired" : ""}">${decision.fired ? "fired" : "did not fire"}</span>` : ""}
        <button class="ghost small-btn" data-remove="${rule.id}" type="button">Remove</button>
      </div>
      <p class="compiled">${escape(explain(rule))}</p>
      ${decision ? `<p class="why">${escape(decision.explanation)}</p>` : ""}
      <p class="why">compiled by ${escape(rule.compiled_by || "keyword")} · notifies ${(rule.channels || []).join(", ")}</p>`;
    list.appendChild(li);
  });

  list.querySelectorAll("[data-remove]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/rules/${button.dataset.remove}`, { method: "DELETE" });
      await refresh();
    });
  });
}

function explain(rule) {
  const who = rule.subject === "any" ? "anything" : `a ${rule.subject}`;
  // `|| fallback` was wrong here: the "any" case is an empty string, which is
  // falsy, so every unzoned rule rendered as "in zone any". Use a presence check.
  const zones = { any: "", inside: " inside a motion zone", outside: " outside every motion zone" };
  const where = rule.zone in zones ? zones[rule.zone] : ` in zone ${String(rule.zone).slice(0, 8)}`;
  const when = rule.window_label === "any time" ? "" : `, between ${rule.window_label}`;
  const night = rule.night_only ? " and only at night" : "";
  const dwell = rule.min_dwell_s ? `, if it stays at least ${Math.round(rule.min_dwell_s)} seconds` : "";
  return `Tell me when ${who}${where} is seen${when}${night}${dwell}.`;
}

/* ---------- pattern ---------- */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function renderPattern(snapshot) {
  const { baseline, counts, silence } = snapshot;

  $("tiles").innerHTML = [
    tile(counts.live, "events seen live"),
    tile(counts.seeded, "seeded for the baseline"),
    tile(baseline.days_observed, "days of history"),
    tile(Object.keys(baseline.buckets).length, "busy hours known"),
  ].join("");

  const alert = $("silence");
  alert.hidden = !silence;
  if (silence) alert.textContent = silence.message;

  const counts_ = baseline.buckets || {};
  const peak = Math.max(1, ...Object.values(counts_));
  const grid = $("heatmap");
  grid.innerHTML = "";
  grid.setAttribute("aria-label",
    `Door activity by weekday and hour. ${Object.values(counts_).reduce((a, b) => a + b, 0)} events across ${baseline.days_observed} days.`);

  grid.appendChild(cellEl("div", "hlabel", ""));
  for (let hour = 0; hour < 24; hour += 1) {
    grid.appendChild(cellEl("div", "htop", hour % 3 === 0 ? String(hour) : ""));
  }

  DAYS.forEach((day, dayIndex) => {
    grid.appendChild(cellEl("div", "hlabel", day));
    for (let hour = 0; hour < 24; hour += 1) {
      const value = counts_[`${dayIndex}:${hour}`] || 0;
      const level = value === 0 ? 0 : Math.max(1, Math.ceil((value / peak) * 7));
      const cell = cellEl("div", "cell", "");
      cell.dataset.level = String(level);
      cell.tabIndex = 0;
      cell.title = `${day} ${String(hour).padStart(2, "0")}:00 — ${value} event${value === 1 ? "" : "s"}`;
      cell.setAttribute("aria-label", cell.title);
      grid.appendChild(cell);
    }
  });

  renderHeatTable(counts_);
  $("counts").textContent = `${counts.total} events stored — ${counts.live} live, ${counts.seeded} seeded.`;
}

function renderHeatTable(buckets) {
  const rows = DAYS.map((day, dayIndex) => {
    const cells = Array.from({ length: 24 }, (_, hour) => `<td>${buckets[`${dayIndex}:${hour}`] || 0}</td>`).join("");
    return `<tr><th scope="row">${day}</th>${cells}</tr>`;
  }).join("");
  const head = Array.from({ length: 24 }, (_, hour) => `<th scope="col">${hour}</th>`).join("");
  $("hm-table").innerHTML = `<table><caption class="note">Events per weekday and hour</caption>
    <thead><tr><th scope="col">Day</th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

$("hm-table-toggle").addEventListener("click", (event) => {
  const table = $("hm-table");
  table.hidden = !table.hidden;
  event.target.setAttribute("aria-expanded", String(!table.hidden));
  event.target.textContent = table.hidden ? "Show as a table" : "Hide the table";
});

$("seed").addEventListener("click", async () => {
  $("seed").disabled = true;
  try {
    await api("/api/seed", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    await refresh();
  } finally {
    $("seed").disabled = false;
  }
});

/* ---------- log ---------- */
function renderLog(events) {
  const list = $("log");
  list.innerHTML = "";
  events.slice(0, 12).forEach((event) => {
    const li = document.createElement("li");
    if (event.source === "seeded") li.classList.add("seeded");
    const when = new Date(event.at * 1000);
    const time = when.toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
    li.innerHTML = `
      <div class="when">${escape(time)}${event.source === "seeded" ? '<span class="tag">seeded</span>' : ""}</div>
      <p class="what">${escape(event.summary || `${event.subject} — ${event.action}`)}</p>`;
    list.appendChild(li);
  });
  if (!events.length) list.innerHTML = '<li class="note">Nothing yet.</li>';
}

/* ---------- glue ---------- */
function tile(value, label) {
  return `<div class="tile"><div class="value">${value}</div><div class="label">${escape(label)}</div></div>`;
}

function cellEl(tag, className, text) {
  const el = document.createElement(tag);
  el.className = className;
  if (text) el.textContent = text;
  return el;
}

function escape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

async function refresh() {
  const snapshot = await api("/api/state");
  renderToken(snapshot.token);
  if (snapshot.device) {
    renderDevice({
      device: snapshot.device,
      online: snapshot.online !== false,
      zones: snapshot.zones,
      capabilities: snapshot.capabilities || {},
      offline: snapshot.offline,
    });
  }
  // A reload should not lose the last thing the door said.
  const lastLive = (snapshot.events || []).find((e) => e.source !== "seeded");
  if (lastLive && $("announcement").textContent === "Nothing described yet.") {
    $("announcement").textContent = lastLive.summary || "";
    $("reason").textContent = "From before this page was reloaded.";
  }
  renderRules(snapshot.rules);
  renderPattern(snapshot);
  renderLog(snapshot.events);

  // A countdown that only ticks while a token is live, so the demo never
  // discovers an expired token mid-sentence.
  clearInterval(state.countdown);
  if (snapshot.token.present && !snapshot.token.expired) {
    let left = snapshot.token.seconds_left;
    state.countdown = setInterval(() => {
      left -= 1;
      renderToken({ ...snapshot.token, seconds_left: Math.max(0, left), expired: left <= 0 });
      if (left <= 0) clearInterval(state.countdown);
    }, 1000);
  }
}

refresh().catch((err) => { $("token-state").textContent = err.message; });
