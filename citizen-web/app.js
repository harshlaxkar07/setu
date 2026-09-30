/* Setu citizen chat widget (tasks 3.2/3.3/3.5/3.8; enhancements 6.3–6.5).
 *
 * - Press-and-hold MediaRecorder voice capture (audio/webm;codecs=opus),
 *   uploaded as multipart to POST /api/requests/voice.
 * - Text fallback to POST /api/requests/text.
 * - conversation_id: client-generated UUID, kept in localStorage (try/catch —
 *   private mode falls back to in-memory). It is the ONLY submitter identity:
 *   pseudonymous, no name/phone anywhere (citizen-intake spec).
 * - Receipt: polls GET /api/requests/{id}/status until the Understand stage
 *   completes, then renders the understood category + urgency with the
 *   AI-drafted provenance marker and a per-message language chip.
 * - Enhancements: UI language switch (hi/mr/en, i18n.js) that re-renders
 *   every message already shown; a live status timeline per submission;
 *   one follow-up question when the location could not be resolved;
 *   read-aloud using ON-DEVICE voices only (no text leaves the phone); and
 *   an assisted mode (?mode=assisted) for field workers with an offline
 *   queue that submits each report exactly once.
 */
"use strict";

const API = ""; // same origin: the page is served by the backend
const ASSISTED = new URLSearchParams(location.search).get("mode") === "assisted";

// ---------------------------------------------------------------- identity

function getConversationId() {
  const KEY = "setu_conversation_id";
  let id = null;
  try {
    id = localStorage.getItem(KEY);
  } catch (_) { /* storage unavailable — fall through to in-memory */ }
  if (!id) {
    id = uuid();
    try { localStorage.setItem(KEY, id); } catch (_) { /* in-memory only */ }
  }
  return id;
}

function uuid() {
  return (crypto.randomUUID && crypto.randomUUID()) ||
    "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
    });
}

const conversationId = getConversationId();

function storeGet(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch (_) { return fallback; }
}

function storeSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* ok */ }
}

// ------------------------------------------------------ translated text nodes
//
// Every translated node remembers its key + vars (data-i18n), so switching
// language re-renders messages already on screen, not just new ones.

function i18nNode(tag, key, vars, cls) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  el.dataset.i18n = JSON.stringify({ key, vars: vars || null });
  renderI18n(el);
  return el;
}

function renderI18n(el) {
  const { key, vars } = JSON.parse(el.dataset.i18n);
  const { main, sub } = tr(key, vars);
  el.textContent = "";
  const m = document.createElement("span");
  m.className = "i18n-main";
  m.textContent = main;
  el.appendChild(m);
  if (sub && !el.classList.contains("no-sub")) {
    const s = document.createElement("span");
    s.className = "en-sub";
    s.textContent = sub;
    el.appendChild(s);
  }
}

// ------------------------------------------------------------ chat helpers

const chatEl = document.getElementById("chat");

function bubble(cls) {
  const el = document.createElement("div");
  el.className = "bubble " + cls;
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

/** Translated system bubble: chosen language + English subtitle, with a
 *  read-aloud control when an on-device voice exists. */
function systemBubble(key, vars, extraCls) {
  const el = bubble("system" + (extraCls ? " " + extraCls : ""));
  el.appendChild(i18nNode("div", key, vars, "i18n-block"));
  addSpeaker(el);
  return el;
}

function chipEl(cls, text) {
  const c = document.createElement("span");
  c.className = "chip " + cls;
  c.textContent = text;
  return c;
}

function metaRow(parent) {
  let row = parent.querySelector(":scope > .meta");
  if (!row) {
    row = document.createElement("div");
    row.className = "meta";
    parent.appendChild(row);
  }
  return row;
}

function setStatusNote(msgEl, key) {
  const row = metaRow(msgEl);
  let note = row.querySelector(".status-note");
  if (!key) { if (note) note.remove(); return; }
  if (!note) {
    note = document.createElement("span");
    note.className = "status-note no-sub";
    row.appendChild(note);
  }
  note.dataset.i18n = JSON.stringify({ key, vars: null });
  renderI18n(note);
}

/** Per-message language chip (citizen-intake spec) — set once known. */
function setLanguageChip(msgEl, language) {
  if (!language) return;
  const row = metaRow(msgEl);
  if (!row.querySelector(".chip.lang")) row.appendChild(chipEl("lang", language));
}

// ------------------------------------------------------------- read aloud
//
// Only voices that run ON THE DEVICE are used (voice.localService): some
// browsers' online voices send the text to a server, which the citizen spec
// forbids. No suitable local voice → no speaker button, nothing else changes.

function localVoice() {
  if (!("speechSynthesis" in window)) return null;
  const want = LANGS[currentLang].speech.toLowerCase();
  const base = want.split("-")[0];
  const voices = window.speechSynthesis.getVoices().filter((v) => v.localService);
  return voices.find((v) => v.lang.toLowerCase() === want) ||
    voices.find((v) => v.lang.toLowerCase().startsWith(base)) || null;
}

function addSpeaker(el) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "speak-btn";
  btn.textContent = "🔊";
  btn.addEventListener("click", () => {
    const voice = localVoice();
    if (!voice) return;
    const text = Array.from(el.querySelectorAll(".i18n-main"))
      .map((n) => n.textContent).join(". ");
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.voice = voice;
    u.lang = voice.lang;
    window.speechSynthesis.speak(u);
  });
  el.appendChild(btn);
  refreshSpeaker(btn);
}

function refreshSpeaker(btn) {
  const ok = !!localVoice();
  btn.hidden = !ok;
  btn.setAttribute("aria-label", t("speak_label"));
  btn.title = t("speak_label");
}

function refreshSpeakers() {
  document.querySelectorAll(".speak-btn").forEach(refreshSpeaker);
}

if ("speechSynthesis" in window) {
  // Voices load asynchronously on most browsers.
  window.speechSynthesis.addEventListener?.("voiceschanged", refreshSpeakers);
}

// --------------------------------------------------------------- receipts

function renderReceipt(receipt) {
  const catKey = "cat_" + receipt.category;
  const urgKey = "urg_" + receipt.urgency;
  const el = bubble("system");
  el.appendChild(i18nNode("div", "receipt_title", null, "receipt-title i18n-block no-sub"));
  el.appendChild(i18nNode("div", "receipt_line", {
    cat: { key: STRINGS[catKey] ? catKey : "cat_other" },
    urg: { key: STRINGS[urgKey] ? urgKey : "urg_medium" },
  }, "receipt-line i18n-block"));
  // AI-drafted provenance marker — distinct from the citizen's own messages.
  const row = metaRow(el);
  const ai = i18nNode("span", "ai_chip", null, "chip ai no-sub");
  row.appendChild(ai);
  if (receipt.detected_language) row.appendChild(chipEl("lang", receipt.detected_language));
  addSpeaker(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

// -------------------------------------------------------------- timeline

const TIMELINE_MS = 5000;
const STAGE_DETAIL = {
  grouped: (s) => (s.others !== undefined ? ["grouped_with", { n: s.others }] :
    s.detail_en === "waiting for the place name" ? ["waiting_place"] : null),
  understood: (s) => (s.detail_en ? ["retrying"] : null),
  under_review: (s) => (s.detail_en === "changes requested" ? ["changes_requested"] :
    s.detail_en === "not approved this time" ? ["not_approved"] : null),
  resolved: (s) => (s.state !== "done" ? null :
    s.verified ? ["resolved_verified"] : ["resolved_unverified"]),
};

function renderTimeline(box, stages) {
  const list = box.querySelector("ol") || box.appendChild(document.createElement("ol"));
  list.className = "timeline";
  list.textContent = "";
  stages.forEach((s) => {
    const li = document.createElement("li");
    li.className = "tl-" + s.state;
    li.setAttribute("aria-current", s.state === "current" ? "step" : "false");
    const dot = document.createElement("span");
    dot.className = "tl-dot";
    dot.textContent = s.state === "done" ? "✓" : s.state === "current" ? "●" : "○";
    li.appendChild(dot);
    const label = i18nNode("span", "st_" + s.key, null, "tl-label no-sub");
    li.appendChild(label);
    const detail = STAGE_DETAIL[s.key] && STAGE_DETAIL[s.key](s);
    if (detail) li.appendChild(i18nNode("span", detail[0], detail[1], "tl-detail no-sub"));
    list.appendChild(li);
  });
}

async function watchTimeline(requestId) {
  const box = bubble("system timeline-bubble");
  box.appendChild(i18nNode("div", "timeline_title", null, "receipt-title no-sub"));
  let asked = false;
  const tick = async () => {
    try {
      const [tl, st] = await Promise.all([
        fetch(`${API}/api/requests/${requestId}/timeline`).then((r) => r.ok ? r.json() : null),
        fetch(`${API}/api/requests/${requestId}/status`).then((r) => r.ok ? r.json() : null),
      ]);
      if (tl) renderTimeline(box, tl.stages);
      if (st && st.verification_prompts) showVerificationPrompts(st.verification_prompts);
      if (st && st.needs_location && !asked) {
        asked = true;
        askLocation(requestId);
      }
      const done = tl && tl.stages.every((s) => s.state === "done");
      if (done) return; // fully resolved — nothing left to watch
    } catch (_) { /* transient — keep watching */ }
    setTimeout(tick, TIMELINE_MS);
  };
  tick();
}

// ------------------------------------------------ location follow-up (D8)

function askLocation(requestId) {
  const askedKey = "setu_location_asked";
  const asked = storeGet(askedKey, []);
  if (asked.includes(requestId)) return; // ask once, even across reloads
  storeSet(askedKey, asked.concat(requestId));

  const el = systemBubble("location_q", null, "verify");
  const form = document.createElement("form");
  form.className = "location-form";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "text-input";
  input.placeholder = t("location_placeholder");
  input.setAttribute("aria-label", t("location_q"));
  input.maxLength = 200;
  const btn = document.createElement("button");
  btn.type = "submit";
  btn.className = "send-btn";
  btn.textContent = "➤";
  btn.setAttribute("aria-label", t("send_label"));
  form.append(input, btn);
  el.appendChild(form);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const answer = input.value.trim();
    if (answer.length < 2) return;
    form.remove();
    const mine = bubble("mine");
    mine.textContent = answer;
    try {
      const res = await fetch(`${API}/api/requests/${requestId}/location`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer, conversation_id: conversationId }),
      });
      const data = res.ok ? await res.json() : { resolved: false };
      systemBubble(data.resolved ? "location_found" : "location_unfound");
    } catch (_) {
      systemBubble("send_failed", null, "error");
    }
  });
  input.focus();
}

// -------------------------------------------------------------- polling

const POLL_MS = 1500;
const POLL_MAX = 60; // ~90 s

async function pollReceipt(requestId, msgEl, attempt = 0) {
  if (attempt >= POLL_MAX) return;
  try {
    const res = await fetch(`${API}/api/requests/${requestId}/status`);
    if (res.ok) {
      const data = await res.json();
      // §8: the verification prompt rides this same status poll (design D4).
      if (data.verification_prompts) showVerificationPrompts(data.verification_prompts);
      if (data.receipt) {
        setStatusNote(msgEl, "recorded");
        setLanguageChip(msgEl, data.receipt.detected_language);
        renderReceipt(data.receipt);
        watchTimeline(requestId);
        return;
      }
      if (data.status === "needs_retry") {
        setStatusNote(msgEl, "recorded");
        systemBubble("retry_note");
        watchTimeline(requestId);
        return;
      }
    }
  } catch (_) { /* transient network error — keep polling */ }
  setTimeout(() => pollReceipt(requestId, msgEl, attempt + 1), POLL_MS);
}

// ------------------------------------------------------------ text sending

const inputEl = document.getElementById("text-input");
const sendBtn = document.getElementById("send-btn");

async function sendText() {
  const text = inputEl.value.trim();
  if (!text) return;
  if (ASSISTED) return sendAssisted(text);
  inputEl.value = "";

  const el = bubble("mine");
  const span = document.createElement("span");
  span.textContent = text;
  el.appendChild(span);
  setStatusNote(el, "sending");

  try {
    const res = await fetch(`${API}/api/requests/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, conversation_id: conversationId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    setStatusNote(el, "received");
    rememberRequestId(data.id);
    pollReceipt(data.id, el);
  } catch (_) {
    setStatusNote(el, null);
    systemBubble("send_failed", null, "error");
  }
}

sendBtn.addEventListener("click", sendText);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendText();
});

// ------------------------------------ assisted field-worker mode (6.5, D11)
//
// A field worker reports on behalf of residents: village + households are
// tagged, no resident name/phone is ever collected. Reports are queued on the
// device with an idempotency key and flushed when online; the backend returns
// the existing request for a replayed key, so each report is created once.

const QUEUE_KEY = "setu_assisted_queue";

function queue() { return storeGet(QUEUE_KEY, []); }

function updateQueueCount() {
  const el = document.getElementById("queue-count");
  if (!el) return;
  const n = queue().length;
  el.dataset.i18n = JSON.stringify(n ? { key: "queue_count", vars: { n } }
    : { key: "queue_empty", vars: null });
  renderI18n(el);
  el.classList.toggle("has-items", n > 0);
}

function sendAssisted(text) {
  const village = document.getElementById("assist-village").value.trim();
  const households = parseInt(document.getElementById("assist-households").value, 10) || 1;
  if (!village) {
    systemBubble("assisted_need_village", null, "error");
    return;
  }
  inputEl.value = "";
  const item = { key: uuid(), text, village, households, at: Date.now() };
  storeSet(QUEUE_KEY, queue().concat(item));
  const el = bubble("mine");
  el.dataset.queueKey = item.key;
  el.textContent = `${village} (${households}) — ${text}`;
  setStatusNote(el, "sending");
  updateQueueCount();
  flushQueue();
}

let flushing = false;
let offlineNoticeShown = false; // one notice per offline period, not per report

async function flushQueue() {
  if (flushing || !navigator.onLine) {
    if (!navigator.onLine && queue().length && !offlineNoticeShown) {
      offlineNoticeShown = true;
      systemBubble("queued_offline");
    }
    return;
  }
  flushing = true;
  let sent = 0;
  try {
    for (const item of queue()) {
      let res;
      try {
        res = await fetch(`${API}/api/requests/text`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: item.text, conversation_id: conversationId, assisted: true,
            village: item.village, households: item.households,
            idempotency_key: item.key,
          }),
        });
      } catch (_) { break; } // offline again — keep the rest queued
      if (!res.ok) break;
      const data = await res.json();
      storeSet(QUEUE_KEY, queue().filter((q) => q.key !== item.key));
      sent += 1;
      const b = document.querySelector(`.bubble.mine[data-queue-key="${item.key}"]`);
      if (b) setStatusNote(b, "received");
      rememberRequestId(data.id);
      if (b) pollReceipt(data.id, b);
    }
  } finally {
    flushing = false;
    updateQueueCount();
  }
  if (sent && offlineNoticeShown) {
    offlineNoticeShown = false;
    systemBubble("queue_flushed", { n: sent });
  }
}

window.addEventListener("online", flushQueue);
window.addEventListener("offline", () => flushQueue());

// -------------------------------------------------- press-and-hold voice

const micBtn = document.getElementById("mic-btn");

let mediaStream = null;
let recorder = null;
let recChunks = [];
let recording = false;
let micDeniedShown = false;

function recorderMime() {
  const preferred = "audio/webm;codecs=opus";
  if (window.MediaRecorder && MediaRecorder.isTypeSupported &&
      MediaRecorder.isTypeSupported(preferred)) {
    return preferred;
  }
  return ""; // browser default (e.g. Safari) — backend/ffmpeg decodes either
}

function showMicDenied() {
  verificationVoiceTarget = null; // a failed hold must not linger as a target
  if (micDeniedShown) return;
  micDeniedShown = true;
  systemBubble("mic_denied", null, "error");
}

async function startRecording() {
  if (recording) return;
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    showMicDenied();
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (_) {
    showMicDenied();
    return;
  }
  recChunks = [];
  const mime = recorderMime();
  recorder = mime ? new MediaRecorder(mediaStream, { mimeType: mime })
                  : new MediaRecorder(mediaStream);
  recorder.ondataavailable = (e) => { if (e.data.size) recChunks.push(e.data); };
  recorder.onstop = onRecordingStopped;
  recorder.start();
  recording = true;
  micBtn.classList.add("recording");
}

let recordStartedAt = 0;

function stopRecording() {
  if (!recording) return;
  recording = false;
  micBtn.classList.remove("recording");
  if (recorder && recorder.state !== "inactive") recorder.stop();
}

function releaseStream() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((tr_) => tr_.stop());
    mediaStream = null;
  }
}

async function onRecordingStopped() {
  releaseStream();
  // §8: a hold started from a verification prompt's mic uploads the voice
  // note as follow-up evidence instead of a new complaint.
  const vTarget = verificationVoiceTarget;
  verificationVoiceTarget = null;
  const heldMs = Date.now() - recordStartedAt;
  const blob = new Blob(recChunks, { type: recorder.mimeType || "audio/webm" });
  recChunks = [];
  if (heldMs < 400 || blob.size === 0) {
    systemBubble("hold_hint");
    return;
  }
  if (vTarget) {
    await sendVerificationVoice(vTarget, blob);
    return;
  }

  // Voice bubble with inline playback (citizen-intake spec).
  const el = bubble("mine");
  const audio = document.createElement("audio");
  audio.controls = true;
  audio.src = URL.createObjectURL(blob);
  el.appendChild(audio);
  setStatusNote(el, "sending");

  const form = new FormData();
  form.append("audio", blob, "note.webm");
  form.append("conversation_id", conversationId);
  try {
    const res = await fetch(`${API}/api/requests/voice`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    setStatusNote(el, "received");
    rememberRequestId(data.id);
    pollReceipt(data.id, el);
  } catch (_) {
    setStatusNote(el, null);
    systemBubble("voice_failed", null, "error");
  }
}

// press-and-hold: pointer events cover mouse + touch; keep touchstart for
// older mobile browsers. Releasing anywhere (or cancel) stops the recording.
micBtn.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  verificationVoiceTarget = null; // the main mic always files a complaint
  recordStartedAt = Date.now();
  startRecording();
});
window.addEventListener("pointerup", stopRecording);
window.addEventListener("pointercancel", stopRecording);
micBtn.addEventListener("touchstart", (e) => {
  if (window.PointerEvent) return; // pointer events already handle it
  e.preventDefault();
  verificationVoiceTarget = null;
  recordStartedAt = Date.now();
  startRecording();
}, { passive: false });
window.addEventListener("touchend", () => {
  if (!window.PointerEvent) stopRecording();
});
micBtn.addEventListener("contextmenu", (e) => e.preventDefault());

// ----------------------------------------- verification follow-up (§8)
//
// After officials mark a cluster resolved, the status poll of any request
// this conversation contributed carries `verification_prompts`. The page
// then asks for follow-up evidence — a current photo (before/after pair
// welcome) or a press-and-hold voice note — uploaded to
// POST /api/verification/{cluster_id}. Same pseudonymous conversation_id.

const LAST_REQUEST_KEY = "setu_last_request_id";
const VERIFY_SENT_KEY = "setu_verification_sent";
const VERIFY_POLL_MS = 6000;

let verificationVoiceTarget = null; // cluster id while a prompt's mic is held
let verificationTimer = null;
const promptedClusters = new Set(); // one prompt bubble per cluster per visit

function rememberRequestId(id) {
  try { localStorage.setItem(LAST_REQUEST_KEY, id); } catch (_) { /* ok */ }
  startVerificationWatch(id);
}

function sentClusters() {
  return storeGet(VERIFY_SENT_KEY, []);
}

function markClusterSent(clusterId) {
  const sent = sentClusters();
  if (!sent.includes(clusterId)) storeSet(VERIFY_SENT_KEY, sent.concat(clusterId));
}

/** Slow background watch on the conversation's latest request: the prompt
 *  appears live when the cluster is resolved mid-session, and on reopen. */
function startVerificationWatch(requestId) {
  if (verificationTimer) clearInterval(verificationTimer);
  const check = async () => {
    try {
      const res = await fetch(`${API}/api/requests/${requestId}/status`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.verification_prompts) showVerificationPrompts(data.verification_prompts);
    } catch (_) { /* transient — keep watching */ }
  };
  check();
  verificationTimer = setInterval(check, VERIFY_POLL_MS);
}

function showVerificationPrompts(prompts) {
  const already = sentClusters();
  prompts.forEach((p) => {
    if (promptedClusters.has(p.cluster_id)) return;
    if (already.includes(p.cluster_id)) return;
    promptedClusters.add(p.cluster_id);
    renderVerificationPrompt(p);
  });
}

function verifyActionButton(key) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "verify-btn";
  btn.appendChild(i18nNode("span", key, null, "i18n-block"));
  return btn;
}

function renderVerificationPrompt(p) {
  const el = bubble("system verify");
  el.appendChild(i18nNode("div", "verify_title", null, "receipt-title i18n-block no-sub"));
  el.appendChild(i18nNode("div", "verify_line", null, "receipt-line i18n-block"));
  if (p.summary) {
    el.appendChild(i18nNode("div", "verify_issue", { summary: p.summary },
      "verify-summary no-sub"));
  }
  addSpeaker(el);

  const actions = document.createElement("div");
  actions.className = "verify-actions";

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
  fileInput.multiple = true; // a before/after pair is welcome
  fileInput.className = "visually-hidden";
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length) {
      sendVerificationPhotos(p.cluster_id, fileInput.files);
      fileInput.value = "";
    }
  });

  const photoBtn = verifyActionButton("verify_photo");
  photoBtn.addEventListener("click", () => fileInput.click());

  // Press-and-hold voice follow-up: same recorder, verification target set
  // for the duration of the hold (the global pointerup stops it).
  const voiceBtn = verifyActionButton("verify_voice");
  const beginVerifyHold = () => {
    verificationVoiceTarget = p.cluster_id;
    recordStartedAt = Date.now();
    startRecording();
    voiceBtn.classList.add("recording");
  };
  voiceBtn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    beginVerifyHold();
  });
  voiceBtn.addEventListener("touchstart", (e) => {
    if (window.PointerEvent) return;
    e.preventDefault();
    beginVerifyHold();
  }, { passive: false });
  ["pointerup", "pointercancel", "touchend"].forEach((ev) =>
    window.addEventListener(ev, () => voiceBtn.classList.remove("recording")));
  voiceBtn.addEventListener("contextmenu", (e) => e.preventDefault());

  actions.append(photoBtn, voiceBtn, fileInput);
  el.appendChild(actions);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function postVerification(clusterId, form, el) {
  setStatusNote(el, "sending");
  try {
    const res = await fetch(`${API}/api/verification/${clusterId}`, {
      method: "POST", body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    setStatusNote(el, "received");
    markClusterSent(clusterId);
    systemBubble("verify_thanks");
  } catch (_) {
    setStatusNote(el, null);
    systemBubble("send_failed", null, "error");
  }
}

async function sendVerificationPhotos(clusterId, files) {
  const el = bubble("mine");
  el.appendChild(files.length > 1
    ? i18nNode("span", "photos", { n: files.length }, "no-sub")
    : i18nNode("span", "photo", null, "no-sub"));
  const form = new FormData();
  Array.from(files).slice(0, 6).forEach((f, i) =>
    form.append("photos", f, f.name || `photo-${i}.jpg`));
  form.append("conversation_id", conversationId);
  await postVerification(clusterId, form, el);
}

async function sendVerificationVoice(clusterId, blob) {
  const el = bubble("mine");
  const audio = document.createElement("audio");
  audio.controls = true;
  audio.src = URL.createObjectURL(blob);
  el.appendChild(audio);
  const form = new FormData();
  form.append("voice", blob, "followup.webm");
  form.append("conversation_id", conversationId);
  await postVerification(clusterId, form, el);
}

// ----------------------------------------------------- language switching

const TOPICS = [
  ["💧", "topic_water", "prefix_water"],
  ["🛣️", "topic_road", "prefix_road"],
  ["🏥", "topic_health", "prefix_health"],
  ["⚡", "topic_power", "prefix_power"],
];

function renderChrome() {
  document.documentElement.lang = LANGS[currentLang].htmlLang;
  document.querySelectorAll("[data-i18n]").forEach(renderI18n);
  inputEl.placeholder = t("placeholder");
  sendBtn.setAttribute("aria-label", t("send_label"));
  micBtn.setAttribute("aria-label", t("mic_label"));
  document.querySelectorAll(".lang-btn").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.lang === currentLang)));
  refreshSpeakers();
}

function setLanguage(lang) {
  if (!LANGS[lang]) return;
  currentLang = lang;
  try { localStorage.setItem("setu_ui_lang", lang); } catch (_) { /* ok */ }
  renderChrome();
}

document.querySelectorAll(".lang-btn").forEach((b) =>
  b.addEventListener("click", () => setLanguage(b.dataset.lang)));

// ------------------------------------------------------------------ boot

const welcomeEl = systemBubble(ASSISTED ? "assisted_welcome" : "welcome");

// Topic chips: one tap starts a typed message with the topic already named.
// They only prefill the input — nothing is sent until the citizen presses send.
const topicRow = document.createElement("div");
topicRow.className = "topic-row";
for (const [icon, labelKey, prefixKey] of TOPICS) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "topic-chip";
  const iconEl = document.createElement("span");
  iconEl.setAttribute("aria-hidden", "true");
  iconEl.textContent = icon;
  btn.append(iconEl, i18nNode("span", labelKey, null, "topic-label"));
  btn.addEventListener("click", () => {
    const prefix = t(prefixKey);
    inputEl.value = prefix;
    inputEl.focus();
    inputEl.setSelectionRange(prefix.length, prefix.length);
  });
  topicRow.appendChild(btn);
}
welcomeEl.insertBefore(topicRow, welcomeEl.querySelector(".speak-btn"));

function buildAssistPanel() {
  const panel = document.createElement("div");
  panel.className = "assist-panel";
  panel.innerHTML = `
    <div class="assist-head">
      <span class="assist-badge no-sub" data-i18n='{"key":"assisted_badge","vars":null}'></span>
      <span id="queue-count" class="queue-count no-sub" aria-live="polite"></span>
    </div>
    <div class="assist-fields">
      <label class="assist-field">
        <span class="no-sub" data-i18n='{"key":"assisted_village","vars":null}'></span>
        <input id="assist-village" class="text-input" type="text" maxlength="120" autocomplete="off">
      </label>
      <label class="assist-field narrow">
        <span class="no-sub" data-i18n='{"key":"assisted_households","vars":null}'></span>
        <input id="assist-households" class="text-input" type="number" min="1" max="5000"
               value="1" inputmode="numeric">
      </label>
    </div>`;
  document.querySelector(".header").after(panel);
}

if (ASSISTED) {
  document.body.classList.add("assisted");
  buildAssistPanel();
  updateQueueCount();
  flushQueue();
}
renderChrome();

// Reopening the conversation: check the last request's status once (and keep
// watching) so a prompt for a since-resolved cluster appears (verification
// spec "Prompt appears once the cluster is resolved").
try {
  const lastRequestId = localStorage.getItem(LAST_REQUEST_KEY);
  if (lastRequestId) startVerificationWatch(lastRequestId);
} catch (_) { /* storage unavailable — prompts arrive with the next send */ }
