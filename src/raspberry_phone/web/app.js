"use strict";

import {
  controlsDisabled,
  HoldToTalk,
  followBehavior,
  shouldFollow,
  statusCopy,
  writeText,
} from "/ui.mjs";

const body = document.body;
const statusLabel = document.querySelector("#status-label");
const talkButton = document.querySelector("#talk-button");
const resetButton = document.querySelector("#reset-button");
const resetDialog = document.querySelector("#reset-dialog");
const toast = document.querySelector("#toast");
const turnList = document.querySelector("#turn-list");
const emptyState = document.querySelector("#empty-state");

const recordSeconds = Number.parseInt(body.dataset.recordSeconds ?? "7", 10);
const COPY = statusCopy(recordSeconds, body.dataset.streaming === "true");

let currentState = null;
let connected = false;
const pendingCommands = new Set();
let toastTimer = null;
const modeControl = document.querySelector("#mode-control");
const modeInputs = [...document.querySelectorAll('input[name="conversation-mode"]')];
const talkLabel = document.querySelector("#talk-label");
const sessionDetail = document.querySelector("#session-detail");
const hold = new HoldToTalk(sendCommand, () => Array.from(crypto.getRandomValues(new Uint32Array(4)), n => n.toString(16).padStart(8, "0")).join(""));
const isManual = () => currentState?.session_supported && currentState.mode === "push-to-talk";
let suppressManualClick = false;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function setConnected(value) {
  connected = value;
  body.dataset.connected = String(value);
  if (!value) writeText(statusLabel, "Offline");
  updateControls();
}

function updateControls() {
  const status = currentState?.status ?? "starting";
  const copy = COPY[status] ?? COPY.starting;
  const pending = [...pendingCommands].at(-1)?.path;
  const supported = currentState?.session_supported;
  const active = Boolean(currentState?.session_active);
  const holding = Boolean(hold.active);
  const busy = pendingCommands.size > 0;
  const stopping = pending === "/api/session/stop" || pending === "/api/ptt/cancel";
  const starting = pending === "/api/session/start" || pending === "/api/ptt/press";
  const releasing = pending === "/api/ptt/release";
  let label = copy.action;
  let detail = currentState?.error || copy.detail;
  if (connected) writeText(statusLabel, copy.label);
  modeControl.hidden = !supported;
  modeControl.disabled = !connected || busy || active || copy.busy;
  for (const input of modeInputs) input.checked = input.value === currentState?.mode;
  resetButton.disabled = !connected || busy || active || copy.busy;
  talkButton.disabled = controlsDisabled(connected, busy, copy);
  if (supported) {
    label = isManual() ? "Segure para falar" : "Iniciar conversa";
    detail = isManual() ? "Segure para gravar. Solte para enviar." : "Toque para começar. Fale e faça uma pausa.";
    talkButton.disabled = holding ? false : (!connected || busy || (!active && copy.busy));
    if (active) {
      label = isManual() ? "Cancelar" : "Parar conversa";
      const response = currentState.response_status;
      const stateLabel = response === "speaking" ? "Falando" : response === "thinking" ? "Pensando" : currentState.listening ? "Ouvindo" : "Preparando";
      if (connected) writeText(statusLabel, stateLabel);
      detail = isManual()
        ? (response === "speaking" ? "Respondendo…" : response === "thinking" ? "Preparando a resposta…" : "Gravando…")
        : "Microfone ligado. Você pode interromper falando.";
    }
    if (holding) { label = "Solte para enviar"; detail = "Gravando…"; }
    else if (stopping) { label = "Parando…"; detail = "Encerrando a conversa…"; }
    else if (releasing) { label = "Enviando…"; detail = "Finalizando sua fala…"; }
    else if (starting) { label = "Iniciando…"; detail = "Abrindo o microfone…"; }
    if (currentState.error) detail = currentState.error;
    writeText(emptyState.querySelector("span"), isManual() ? "Segure o microfone e solte para enviar." : "Inicie a conversa e fale normalmente.");
  }
  if (!connected) { label = "Reconectando…"; detail = "Tentando restabelecer a conexão…"; }
  body.dataset.micActive = String(holding || active);
  body.dataset.pending = String(busy);
  writeText(talkLabel, label);
  talkButton.setAttribute("aria-label", label);
  talkButton.setAttribute("aria-pressed", String(holding || active));
  talkButton.setAttribute("aria-busy", String(busy));
  writeText(sessionDetail, detail);
}

function showToast(message) {
  writeText(toast, message);
  toast.classList.add("toast--visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("toast--visible"), 3600);
}

// Keep existing bubbles mounted; only change text as new partials arrive.
const entries = new Map();
function updateEntry(key, speaker, text, kind, error, activeKeys) {
  activeKeys.add(key);
  let entry = entries.get(key);
  if (!entry) {
    const item = document.createElement("li");
    item.className = `turn turn--${kind}`;
    const bubble = document.createElement("section");
    bubble.className = `utterance utterance--${kind}`;
    const label = document.createElement("span");
    label.className = "utterance__speaker";
    writeText(label, speaker);
    const paragraph = document.createElement("p");
    const failure = document.createElement("p");
    failure.className = "turn__error";
    bubble.append(label, paragraph);
    item.append(bubble, failure);
    entry = { item, paragraph, failure };
    entries.set(key, entry);
    turnList.append(item);
  }
  // A live input bubble can already exist when a new response arrives.
  // Place every entry in transcript order without remounting its contents.
  const expected = turnList.children[activeKeys.size - 1];
  if (expected !== entry.item) turnList.insertBefore(entry.item, expected ?? null);
  if (entry.paragraph.textContent !== text) writeText(entry.paragraph, text);
  writeText(entry.failure, error || "");
  entry.failure.hidden = !error;
}

function render(state) {
  if (currentState && state.revision < currentState.revision) return;
  const nearBottom = shouldFollow(
    document.documentElement.scrollHeight, window.scrollY, window.innerHeight,
  );
  currentState = state;
  body.dataset.status = state.status;
  const activeKeys = new Set();
  for (const turn of state.turns ?? []) {
    const live = turn.status === "pending";
    const transcript = (live ? state.transcript : turn.transcript) || turn.transcript;
    updateEntry(`${turn.id}:user`, "Você", transcript || (live ? "Ouvindo…" : "Não ouvi nada."), "user", null, activeKeys);
    const answer = live ? state.answer : turn.answer;
    const error = live ? state.error : turn.error;
    if (answer || error || (live && ["thinking", "speaking"].includes(state.status))) {
      updateEntry(`${turn.id}:assistant`, "Resposta", answer || "…", "assistant", error, activeKeys);
    }
  }
  if (state.input_transcript) {
    updateEntry("input:live", "Você", state.input_transcript, "user", null, activeKeys);
  }
  for (const [key, entry] of entries) {
    if (!activeKeys.has(key)) { entry.item.remove(); entries.delete(key); }
  }
  emptyState.hidden = entries.size > 0;
  updateControls();
  if (nearBottom) {
    requestAnimationFrame(() => window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: followBehavior(reducedMotion.matches),
    }));
  }
}

async function sendCommand(path, payload = {}) {
  const command = { path };
  pendingCommands.add(command);
  updateControls();
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      throw new Error(errorPayload.error || "Sem resposta. Tente de novo.");
    }
    render(await response.json());
    return true;
  } catch (error) {
    showToast(error.name === "TimeoutError" ? "O comando demorou. Confira a conexão e tente novamente." : error.message);
    return false;
  } finally {
    pendingCommands.delete(command);
    updateControls();
  }
}

talkButton.addEventListener("click", () => {
  if (isManual() && suppressManualClick) { suppressManualClick = false; return; }
  if (currentState?.session_active && !hold.active) {
    sendCommand("/api/session/stop", { capture_id: currentState.capture_id });
  } else if (!isManual()) {
    sendCommand(currentState?.session_supported ? "/api/session/start" : "/api/turn");
  }
});
modeControl.addEventListener("change", event => {
  if (event.target.name === "conversation-mode") {
    sendCommand("/api/session/mode", { mode: event.target.value });
  }
});
talkButton.addEventListener("pointerdown", event => {
  suppressManualClick = false;
  if (!isManual() || currentState?.session_active || event.button !== 0 || talkButton.disabled) return;
  event.preventDefault();
  talkButton.setPointerCapture(event.pointerId);
  suppressManualClick = true;
  hold.press();
  updateControls();
});
talkButton.addEventListener("pointerup", () => { hold.finish(); updateControls(); });
talkButton.addEventListener("pointercancel", () => { hold.finish(true); updateControls(); });
talkButton.addEventListener("lostpointercapture", () => { hold.finish(true); updateControls(); });
talkButton.addEventListener("keydown", event => {
  if (!hold.active) suppressManualClick = false;
  if (!isManual() || (currentState?.session_active && !hold.active) || ![" ", "Enter"].includes(event.key)) return;
  event.preventDefault();
  if (!event.repeat && !talkButton.disabled) { suppressManualClick = true; hold.press(); updateControls(); }
});
talkButton.addEventListener("keyup", event => {
  if (!isManual() || (currentState?.session_active && !hold.active) || ![" ", "Enter"].includes(event.key)) return;
  event.preventDefault();
  hold.finish();
  updateControls();
});
function cancelHold() { hold.finish(true); updateControls(); }
window.addEventListener("blur", cancelHold);
window.addEventListener("pagehide", cancelHold);
talkButton.addEventListener("blur", cancelHold);
document.addEventListener("visibilitychange", () => { if (document.hidden) cancelHold(); });

resetButton.addEventListener("click", () => {
  resetDialog.returnValue = "cancel";
  resetDialog.showModal();
});
resetDialog.addEventListener("close", () => {
  if (resetDialog.returnValue === "confirm") {
    sendCommand("/api/conversation/reset");
  }
});

let awaitingSnapshot = true;
const events = new EventSource("/api/events");
events.addEventListener("open", () => { awaitingSnapshot = true; setConnected(true); });
events.addEventListener("error", () => setConnected(false));
events.addEventListener("state", (event) => {
  setConnected(true);
  if (awaitingSnapshot) { currentState = null; awaitingSnapshot = false; }
  render(JSON.parse(event.data));
});

events.addEventListener("delta", (event) => {
  setConnected(true);
  render({ ...currentState, ...JSON.parse(event.data) });
});
setConnected(false);
