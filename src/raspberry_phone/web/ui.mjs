export function statusCopy(recordSeconds, streaming = false) {
  return {
    starting: {
      label: "Iniciando",
      detail: "Preparando o microfone…",
      action: "Aguarde…",
      busy: true,
    },
    ready: {
      label: "Online",
      detail: "Pronto pra falar.",
      action: "Falar",
      busy: false,
    },
    recording: {
      label: "Ouvindo",
      detail: streaming
        ? "Fale. Uma pausa encerra a pergunta."
        : `Gravando por ${recordSeconds}s.`,
      action: "Ouvindo…",
      busy: true,
    },
    transcribing: {
      label: "Transcrevendo",
      detail: "Convertendo áudio em texto…",
      action: "Transcrevendo…",
      busy: true,
    },
    thinking: {
      label: "Pensando",
      detail: "Montando a resposta…",
      action: "Pensando…",
      busy: true,
    },
    speaking: {
      label: "Falando",
      detail: "Reproduzindo no alto-falante.",
      action: "Falando…",
      busy: true,
    },
    error: {
      label: "Erro",
      detail: "Algo falhou. Tente de novo.",
      action: "Tentar de novo",
      busy: false,
    },
    stopped: {
      label: "Offline",
      detail: "Sessão encerrada.",
      action: "Offline",
      busy: true,
    },
  };
}

export function controlsDisabled(connected, requestPending, statusView) {
  return !connected || requestPending || statusView.busy;
}

export function shouldFollow(scrollHeight, scrollY, innerHeight) {
  return scrollHeight - scrollY - innerHeight < 180;
}

export function followBehavior(reducedMotion) {
  return "auto"; // Streaming must not restart a scrolling animation on every token.
}

export function writeText(element, value) {
  element.textContent = value;
}

// Serialize release behind press, including a release before the HTTP reply.
export class HoldToTalk {
  constructor(send, makeId) {
    this.send = send;
    this.makeId = makeId;
    this.active = null;
  }
  press() {
    if (this.active) return;
    const hold = { id: this.makeId() };
    this.active = hold;
    hold.started = this.send("/api/ptt/press", { capture_id: hold.id });
  }
  async finish(cancel = false) {
    const hold = this.active;
    if (!hold) return;
    this.active = null;
    if (await hold.started) {
      await this.send(cancel ? "/api/ptt/cancel" : "/api/ptt/release", { capture_id: hold.id });
    }
  }
}
