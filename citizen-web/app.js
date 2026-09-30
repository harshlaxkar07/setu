/* Setu citizen chat widget (tasks 3.2/3.3/3.5/3.8).
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
 */
"use strict";

const API = ""; // same origin: the page is served by the backend

// ---------------------------------------------------------------- identity

function getConversationId() {
  const KEY = "setu_conversation_id";
  let id = null;
  try {
    id = localStorage.getItem(KEY);
  } catch (_) { /* storage unavailable — fall through to in-memory */ }
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) ||
      "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
      });
    try { localStorage.setItem(KEY, id); } catch (_) { /* in-memory only */ }
  }
  return id;
}

const conversationId = getConversationId();

// ------------------------------------------------------------ chat helpers

const chatEl = document.getElementById("chat");

function bubble(cls) {
  const el = document.createElement("div");
  el.className = "bubble " + cls;
  chatEl.appendChild(el);
  chatEl.scrollTop = chatEl.scrollHeight;
  return el;
}

/** Bilingual system bubble: Hindi primary, smaller English subtitle. */
function systemBubble(hi, en, extraCls) {
  const el = bubble("system" + (extraCls ? " " + extraCls : ""));
  const main = document.createElement("span");
  main.textContent = hi;
  const sub = document.createElement("span");
  sub.className = "en-sub";
  sub.textContent = en;
  el.append(main, sub);
  return el;
}

function chipEl(cls, text) {
  const c = document.createElement("span");
  c.className = "chip " + cls;
  c.textContent = text;
  return c;
}

function metaRow(parent) {
  let row = parent.querySelector(".meta");
  if (!row) {
    row = document.createElement("div");
    row.className = "meta";
    parent.appendChild(row);
  }
  return row;
}

function setStatusNote(msgEl, text) {
  const row = metaRow(msgEl);
  let note = row.querySelector(".status-note");
  if (!note) {
    note = document.createElement("span");
    note.className = "status-note";
    row.appendChild(note);
  }
  note.textContent = text;
}

/** Per-message language chip (citizen-intake spec) — set once known. */
function setLanguageChip(msgEl, language) {
  if (!language) return;
  const row = metaRow(msgEl);
  if (!row.querySelector(".chip.lang")) {
    row.appendChild(chipEl("lang", language));
  }
}

// ------------------------------------------------- receipt (bilingual copy)

const CATEGORY_HI = {
  water_infrastructure: ["पानी की समस्या", "water supply issue"],
  road_infrastructure: ["सड़क की समस्या", "road issue"],
  electricity: ["बिजली की समस्या", "electricity issue"],
  sanitation: ["सफ़ाई की समस्या", "sanitation issue"],
};

const URGENCY_HI = {
  high: ["ज़रूरी", "high urgency"],
  medium: ["सामान्य", "medium urgency"],
  low: ["कम ज़रूरी", "low urgency"],
};

function renderReceipt(receipt) {
  const [catHi, catEn] = CATEGORY_HI[receipt.category] ||
    [receipt.category.replace(/_/g, " "), receipt.category.replace(/_/g, " ")];
  const [urgHi, urgEn] = URGENCY_HI[receipt.urgency] ||
    [receipt.urgency, receipt.urgency];

  const el = bubble("system");
  const title = document.createElement("div");
  title.className = "receipt-title";
  title.textContent = "आपकी बात दर्ज हो गई है ✓";
  const line = document.createElement("div");
  line.className = "receipt-line";
  line.textContent = `हमने समझा: ${catHi}, ${urgHi}`;
  const sub = document.createElement("span");
  sub.className = "en-sub";
  sub.textContent = `We understood: ${catEn}, ${urgEn}`;
  el.append(title, line, sub);

  // AI-drafted provenance marker — distinct from the citizen's own messages.
  const row = metaRow(el);
  row.appendChild(chipEl("ai", "✦ AI-drafted / AI-सहायता से"));
  if (receipt.detected_language) {
    row.appendChild(chipEl("lang", receipt.detected_language));
  }
  chatEl.scrollTop = chatEl.scrollHeight;
}

// -------------------------------------------------------------- polling

const POLL_MS = 1500;
const POLL_MAX = 60; // ~90 s

async function pollReceipt(requestId, msgEl, attempt = 0) {
  if (attempt >= POLL_MAX) {
    setStatusNote(msgEl, "…");
    return;
  }
  try {
    const res = await fetch(`${API}/api/requests/${requestId}/status`);
    if (res.ok) {
      const data = await res.json();
      // §8: the verification prompt rides this same status poll (design D4).
      if (data.verification_prompts) {
        showVerificationPrompts(data.verification_prompts);
      }
      if (data.receipt) {
        setStatusNote(msgEl, "दर्ज / received");
        setLanguageChip(msgEl, data.receipt.detected_language);
        renderReceipt(data.receipt);
        return;
      }
      if (data.status === "needs_retry") {
        setStatusNote(msgEl, "दर्ज / received");
        systemBubble(
          "आपकी बात सुरक्षित दर्ज है। सिस्टम इसे थोड़ी देर में दोबारा पढ़ेगा।",
          "Your message is safely recorded; the system will retry processing it."
        );
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
  inputEl.value = "";

  const el = bubble("mine");
  const span = document.createElement("span");
  span.textContent = text;
  el.appendChild(span);
  setStatusNote(el, "भेजा जा रहा… / sending…");

  try {
    const res = await fetch(`${API}/api/requests/text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, conversation_id: conversationId }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    setStatusNote(el, "मिल गया / received");
    rememberRequestId(data.id);
    pollReceipt(data.id, el);
  } catch (_) {
    setStatusNote(el, "");
    systemBubble(
      "भेजा नहीं जा सका — कृपया दोबारा कोशिश करें।",
      "Could not send — please try again.",
      "error"
    );
  }
}

sendBtn.addEventListener("click", sendText);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendText();
});

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
  systemBubble(
    "माइक की अनुमति नहीं मिली, इसलिए आवाज़ से भेजना अभी संभव नहीं है। आप नीचे लिखकर अपनी बात भेज सकते हैं।",
    "Microphone permission was denied, so voice is unavailable. You can still type your message below.",
    "error"
  );
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
    mediaStream.getTracks().forEach((t) => t.stop());
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
    systemBubble(
      "बोलने के लिए माइक बटन दबाकर रखें।",
      "Press and hold the mic button while you speak."
    );
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
  setStatusNote(el, "भेजा जा रहा… / sending…");

  const form = new FormData();
  form.append("audio", blob, "note.webm");
  form.append("conversation_id", conversationId);
  try {
    const res = await fetch(`${API}/api/requests/voice`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    setStatusNote(el, "मिल गया / received");
    rememberRequestId(data.id);
    pollReceipt(data.id, el);
  } catch (_) {
    setStatusNote(el, "");
    systemBubble(
      "आवाज़ भेजी नहीं जा सकी — कृपया दोबारा कोशिश करें।",
      "Could not send the voice note — please try again.",
      "error"
    );
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
  verificationVoiceTarget = null; // the main mic always files a complaint
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
// POST /api/verification/{cluster_id}. Same pseudonymous conversation_id,
// still no name or phone, ever.

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
  try {
    return JSON.parse(localStorage.getItem(VERIFY_SENT_KEY) || "[]");
  } catch (_) { return []; }
}

function markClusterSent(clusterId) {
  try {
    const sent = sentClusters();
    if (!sent.includes(clusterId)) {
      sent.push(clusterId);
      localStorage.setItem(VERIFY_SENT_KEY, JSON.stringify(sent));
    }
  } catch (_) { /* in-memory session only */ }
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
      if (data.verification_prompts) {
        showVerificationPrompts(data.verification_prompts);
      }
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

function verifyActionButton(hi, en, extraCls) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "verify-btn" + (extraCls ? " " + extraCls : "");
  const main = document.createElement("span");
  main.textContent = hi;
  const sub = document.createElement("span");
  sub.className = "en-sub";
  sub.textContent = en;
  btn.append(main, sub);
  return btn;
}

function renderVerificationPrompt(p) {
  const el = bubble("system verify");
  const title = document.createElement("div");
  title.className = "receipt-title";
  title.textContent = "आपके इलाक़े की समस्या हल बताई गई है";
  const line = document.createElement("div");
  line.className = "receipt-line";
  line.textContent =
    "क्या यह सच में ठीक हो गई? कृपया अभी की फोटो भेजिए, या माइक दबाकर बताइए।";
  const sub = document.createElement("span");
  sub.className = "en-sub";
  sub.textContent =
    "Officials report this issue as resolved. Is it really fixed? " +
    "Please send a current photo, or press and hold the mic to tell us.";
  el.append(title, line, sub);
  if (p.summary) {
    const orig = document.createElement("div");
    orig.className = "verify-summary";
    orig.textContent = "समस्या / issue: " + p.summary;
    el.appendChild(orig);
  }

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

  const photoBtn = verifyActionButton("📷 फोटो भेजिए", "send photo");
  photoBtn.addEventListener("click", () => fileInput.click());

  // Press-and-hold voice follow-up: same recorder, verification target set
  // for the duration of the hold (the global pointerup stops it).
  const voiceBtn = verifyActionButton("🎙️ दबाकर बोलिए", "hold to speak");
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

function verificationThanks() {
  systemBubble(
    "धन्यवाद! आपका जवाब दर्ज हो गया है — इसकी जाँच की जाएगी।",
    "Thank you! Your follow-up is recorded and will be checked."
  );
}

function verificationSendFailed() {
  systemBubble(
    "भेजा नहीं जा सका — कृपया दोबारा कोशिश करें।",
    "Could not send — please try again.",
    "error"
  );
}

async function sendVerificationPhotos(clusterId, files) {
  const el = bubble("mine");
  const span = document.createElement("span");
  span.textContent =
    files.length > 1 ? `📷 ${files.length} फोटो / photos` : "📷 फोटो / photo";
  el.appendChild(span);
  setStatusNote(el, "भेजा जा रहा… / sending…");

  const form = new FormData();
  Array.from(files).slice(0, 6).forEach((f, i) =>
    form.append("photos", f, f.name || `photo-${i}.jpg`));
  form.append("conversation_id", conversationId);
  try {
    const res = await fetch(`${API}/api/verification/${clusterId}`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    setStatusNote(el, "मिल गया / received");
    markClusterSent(clusterId);
    verificationThanks();
  } catch (_) {
    setStatusNote(el, "");
    verificationSendFailed();
  }
}

async function sendVerificationVoice(clusterId, blob) {
  const el = bubble("mine");
  const audio = document.createElement("audio");
  audio.controls = true;
  audio.src = URL.createObjectURL(blob);
  el.appendChild(audio);
  setStatusNote(el, "भेजा जा रहा… / sending…");

  const form = new FormData();
  form.append("voice", blob, "followup.webm");
  form.append("conversation_id", conversationId);
  try {
    const res = await fetch(`${API}/api/verification/${clusterId}`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    setStatusNote(el, "मिल गया / received");
    markClusterSent(clusterId);
    verificationThanks();
  } catch (_) {
    setStatusNote(el, "");
    verificationSendFailed();
  }
}

// ------------------------------------------------------------------ boot

const welcomeEl = systemBubble(
  "नमस्ते! पानी, सड़क या बिजली की समस्या हो तो माइक दबाकर बोलिए, या नीचे लिखिए। आपका नाम या फ़ोन नंबर नहीं पूछा जाएगा।",
  "Namaste! Press and hold the mic to describe a water, road or electricity problem — or type below. We never ask your name or phone number."
);

// Topic chips: one tap starts a typed message with the topic already named.
// They only prefill the input — nothing is sent until the citizen presses send.
const TOPICS = [
  ["💧", "पानी", "Water", "पानी की समस्या: "],
  ["🛣️", "सड़क", "Road", "सड़क की समस्या: "],
  ["⚡", "बिजली", "Electricity", "बिजली की समस्या: "],
  ["🧹", "सफ़ाई", "Sanitation", "सफ़ाई की समस्या: "],
];
const topicRow = document.createElement("div");
topicRow.className = "topic-row";
for (const [icon, hi, en, prefix] of TOPICS) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "topic-chip";
  btn.setAttribute("aria-label", `${hi} / ${en}`);
  const iconEl = document.createElement("span");
  iconEl.setAttribute("aria-hidden", "true");
  iconEl.textContent = icon;
  const labelEl = document.createElement("span");
  labelEl.className = "topic-label";
  const hiEl = document.createElement("span");
  hiEl.textContent = hi;
  const enEl = document.createElement("span");
  enEl.className = "en-sub";
  enEl.textContent = en;
  labelEl.append(hiEl, enEl);
  btn.append(iconEl, labelEl);
  btn.addEventListener("click", () => {
    inputEl.value = prefix;
    inputEl.focus();
    inputEl.setSelectionRange(prefix.length, prefix.length);
  });
  topicRow.appendChild(btn);
}
welcomeEl.appendChild(topicRow);

// Reopening the conversation: check the last request's status once (and keep
// watching) so a prompt for a since-resolved cluster appears (verification
// spec "Prompt appears once the cluster is resolved").
try {
  const lastRequestId = localStorage.getItem(LAST_REQUEST_KEY);
  if (lastRequestId) startVerificationWatch(lastRequestId);
} catch (_) { /* storage unavailable — prompts arrive with the next send */ }
