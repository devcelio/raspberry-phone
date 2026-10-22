// Exercise the actual browser entry point without requiring browser packages.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
import * as ui from '../src/raspberry_phone/web/ui.mjs';

class Element {
  constructor() {
    this.children = [];
    this.handlers = {};
    this.dataset = {};
    this.textContent = '';
    this.classList = { add() {}, remove() {} };
  }
  append(...children) { for (const child of children) this.insertBefore(child, null); }
  insertBefore(child, before) {
    child.remove();
    const index = before ? this.children.indexOf(before) : this.children.length;
    this.children.splice(index, 0, child);
    child.parent = this;
  }
  remove() {
    if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(type, handler) { (this.handlers[type] ??= []).push(handler); }
  fire(type, fields = {}) {
    for (const handler of this.handlers[type] ??= []) handler({ preventDefault() {}, ...fields });
  }
  querySelector() { return this.children[0]; }
  setPointerCapture() {}
}
const selectors = new Map();
for (const id of ['status-label', 'talk-button', 'reset-button', 'reset-dialog', 'toast', 'turn-list', 'empty-state', 'mode-control', 'talk-label', 'session-detail']) selectors.set(`#${id}`, new Element());
selectors.get('#empty-state').append(new Element());
const radio = ['continuous', 'push-to-talk'].map(value => Object.assign(new Element(), { value, name: 'conversation-mode' }));
const window = Object.assign(new Element(), { matchMedia: () => ({ matches: false }), scrollTo() {}, scrollY: 0, innerHeight: 844 });
const document = Object.assign(new Element(), {
  body: new Element(), documentElement: { scrollHeight: 844 },
  querySelector: selector => selectors.get(selector), querySelectorAll: () => radio,
  createElement: () => new Element(),
});
let stream;
class EventSource extends Element {
  constructor() { super(); stream = this; }
  emit(type, state = {}) { this.fire(type, { data: JSON.stringify(state) }); }
}
const requests = [];
const context = vm.createContext({
  ...ui, document, window, EventSource, crypto: webcrypto, AbortSignal,
  setTimeout: () => 0, clearTimeout() {}, requestAnimationFrame: fn => fn(),
  fetch: (path, options) => new Promise(resolve => requests.push({ path, payload: JSON.parse(options.body), resolve })),
});
const source = readFileSync(new URL('../src/raspberry_phone/web/app.js', import.meta.url), 'utf8');
vm.runInContext(source.replace(/import\s*\{[\s\S]*?\}\s*from\s*"\/ui.mjs";/, ''), context);
let state = { revision: 1, status: 'ready', turns: [], session_supported: true, session_active: false, mode: 'continuous' };
const emit = (patch, type = 'state') => { state = { ...state, ...patch }; stream.emit(type, state); };
const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const reply = async () => { requests.shift().resolve({ ok: true, json: async () => state }); await tick(); };
const talk = selectors.get('#talk-button');
const label = () => selectors.get('#talk-label').textContent;
emit({});
talk.fire('click');
assert.equal(label(), 'Iniciando…');
assert.equal(talk.disabled, true);
emit({ revision: 2, session_active: true, listening: true });
await reply();
assert.equal(label(), 'Parar conversa');
assert.equal(talk.disabled, false);
emit({ revision: 3, status: 'thinking', response_status: 'thinking', turns: [{ id: 1, status: 'pending', transcript: 'Olá' }], transcript: 'Olá' });
emit({ revision: 4, input_transcript: 'Outra pergunta' }, 'delta');
emit({ revision: 5, answer: 'Resposta ao vivo' }, 'delta');
const paragraphs = () => selectors.get('#turn-list').children.map(item => item.children[0].children[1].textContent);
assert.deepEqual(paragraphs(), ['Olá', 'Resposta ao vivo', 'Outra pergunta']);
emit({ revision: 4, answer: 'atrasada' }, 'delta');
assert.equal(paragraphs()[1], 'Resposta ao vivo');
// The same microphone button must stop even while generating a response.
talk.fire('click');
assert.equal(requests[0].path, '/api/session/stop');
assert.equal(label(), 'Parando…');
emit({ revision: 6, status: 'ready', session_active: false, turns: [], answer: '', input_transcript: '', mode: 'push-to-talk' });
await reply();
talk.fire('pointerdown', { button: 0, pointerId: 1 });
assert.equal(label(), 'Solte para enviar');
assert.equal(talk.disabled, false);
talk.fire('pointerup');
assert.equal(requests.length, 1); // Release must wait for press acknowledgement.
const capture = requests[0].payload.capture_id;
emit({ revision: 7, session_active: true, capture_id: capture });
await reply();
assert.equal(requests[0].path, '/api/ptt/release');
assert.equal(requests[0].payload.capture_id, capture);
await reply();
talk.fire('click'); // A synthetic click after release must not stop the answer.
assert.equal(requests.length, 0);
talk.fire('keydown', { key: 'Enter', repeat: false });
talk.fire('keyup', { key: 'Enter' });
talk.fire('click'); // Enter on an active manual session cancels it.
assert.equal(requests[0].path, '/api/session/stop');
await reply();
stream.emit('error');
assert.equal(talk.disabled, true);
stream.emit('open');
emit({ revision: 1, status: 'ready', session_active: false, mode: 'continuous' });
assert.equal(label(), 'Iniciar conversa');
assert.equal(talk.disabled, false);
console.log('Frontend: feedback, stop, streaming order, early release, keyboard and reconnect passed');
