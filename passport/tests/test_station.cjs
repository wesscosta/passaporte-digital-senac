const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/passport/station.js"), "utf8");

function setup({ fail = false, invalid = false } = {}) {
  const callbacks = new Map();
  const events = {};
  let nextId = 1;
  let clock = 0;
  const timers = {
    set(fn, delay) { const id = nextId++; callbacks.set(id, { fn, delay, at: clock + delay }); return id; },
    clear(id) { callbacks.delete(id); },
    async advance(delay) {
      const target = clock + delay;
      while (true) {
        const next = [...callbacks.entries()].sort((a, b) => a[1].at - b[1].at)[0];
        if (!next || next[1].at > target) break;
        callbacks.delete(next[0]);
        clock = next[1].at;
        await next[1].fn();
      }
      clock = target;
    },
    pending() { return [...callbacks.values()]; },
  };
  const image = { hidden: false, src: "data:image/svg+xml;base64,old" };
  const code = { textContent: "111111" };
  const status = { textContent: "" };
  const countdown = { hidden: true };
  const seconds = { textContent: "" };
  const progress = { value: 0 };
  const classes = new Set();
  const root = {
    dataset: { refreshMs: "5000" },
    querySelector(selector) {
      return { ".station-qr": image, ".station-code": code, "[data-station-status]": status,
        "[data-station-timer]": countdown, "[data-station-seconds]": seconds,
        "[data-station-progress]": progress }[selector];
    },
    classList: { add(name) { classes.add(name); }, remove(name) { classes.delete(name); } },
  };
  const freshImage = { getAttribute() { return "data:image/svg+xml;base64,new"; } };
  const freshCode = { textContent: invalid ? "inválido" : "222222" };
  const fresh = {
    dataset: { refreshMs: "55000" },
    querySelector(selector) { return { ".station-qr": freshImage, ".station-code": freshCode }[selector]; },
  };
  const document = { hidden: false, querySelector() { return root; }, addEventListener(name, fn) { events[name] = fn; } };
  const window = { location: { href: "http://testserver/equipe/estande/1/" }, addEventListener(name, fn) { events[name] = fn; } };
  class DOMParser {
    parseFromString() { return { querySelector() { return fresh; } }; }
  }
  const state = { fail };
  const context = {
    document, window, DOMParser, AbortController, performance: { now: () => clock },
    setTimeout: timers.set, clearTimeout: timers.clear,
    fetch: async () => {
      if (state.fail) throw new Error("sem conexão");
      return { ok: true, redirected: false, text: async () => "<html></html>" };
    },
  };
  vm.runInNewContext(source, context);
  return { timers, image, code, status, countdown, seconds, progress, classes, document, events, state };
}

test("barra diminui e QR e código são atualizados juntos", async () => {
  const x = setup();
  assert.equal(x.seconds.textContent, "5 s");
  assert.equal(x.progress.value, 5000);
  await x.timers.advance(2000);
  assert.equal(x.seconds.textContent, "3 s");
  assert.equal(x.progress.value, 3000);
  await x.timers.advance(3250);
  assert.equal(x.image.src, "data:image/svg+xml;base64,new");
  assert.equal(x.code.textContent, "222222");
  assert.equal(x.image.hidden, false);
  assert.equal(x.seconds.textContent, "55 s");
  assert.match(x.status.textContent, /a cada minuto/);
});

test("falha esconde código e retoma automaticamente após recuperar conexão", async () => {
  const x = setup({ fail: true });
  await x.timers.advance(5250);
  assert.equal(x.image.hidden, true);
  assert.equal(x.code.textContent, "------");
  assert.equal(x.countdown.hidden, true);
  assert.ok(x.classes.has("is-stale"));
  assert.match(x.status.textContent, /Não foi possível atualizar/);
  assert.ok(x.timers.pending().some(timer => timer.delay === 15000));
  x.state.fail = false;
  await x.timers.advance(15000);
  assert.equal(x.image.hidden, false);
  assert.equal(x.code.textContent, "222222");
  assert.equal(x.countdown.hidden, false);
});

test("resposta inválida não substitui o código com valor malformado", async () => {
  const x = setup({ invalid: true });
  await x.timers.advance(5250);
  assert.equal(x.image.hidden, true);
  assert.equal(x.code.textContent, "------");
});

test("ao voltar para a aba busca um novo código sem confiar em temporizador suspenso", async () => {
  const x = setup();
  x.document.hidden = true;
  x.events.visibilitychange();
  await x.timers.advance(120000);
  assert.equal(x.code.textContent, "111111");
  x.document.hidden = false;
  x.events.visibilitychange();
  await new Promise(setImmediate);
  assert.equal(x.code.textContent, "222222");
  assert.equal(x.image.hidden, false);
});
