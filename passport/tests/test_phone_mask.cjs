const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../static/passport/phone-mask.js"), "utf8");

function setup(initial = "") {
  const handlers = {};
  const field = {
    value: initial, selectionStart: initial.length, selectionEnd: initial.length,
    addEventListener(name, fn) { handlers[name] = fn; },
    setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; },
  };
  vm.runInNewContext(source, { document: { querySelector() { return field; } } });
  function input(text) {
    const start = field.selectionStart, end = field.selectionEnd;
    field.value = field.value.slice(0, start) + text + field.value.slice(end);
    field.setSelectionRange(start + text.length, start + text.length);
    handlers.input({ isComposing: false });
  }
  return { field, handlers, input };
}

test("formata a digitação progressiva sem alterar os dígitos", () => {
  const x = setup();
  for (const digit of "86912345678") x.input(digit);
  assert.equal(x.field.value, "(86) 91234-5678");
  assert.equal(x.field.selectionStart, x.field.value.length);
});

test("aceita número colado com DDI brasileiro", () => {
  const x = setup();
  x.input("+55 86 91234-5678");
  assert.equal(x.field.value, "+55 (86) 91234-5678");
  assert.equal(x.field.value.replace(/\D/g, ""), "5586912345678");
});

test("não elimina dígitos excedentes nem conteúdo inválido", () => {
  const x = setup();
  x.input("869123456789");
  assert.equal(x.field.value.replace(/\D/g, ""), "869123456789");
  const y = setup();
  y.input("86abc123");
  assert.equal(y.field.value, "86abc123");
});

test("backspace junto à pontuação remove o dígito anterior e mantém edição", () => {
  const x = setup("86912345678");
  x.field.setSelectionRange(5, 5);
  let prevented = false;
  x.handlers.beforeinput({ inputType: "deleteContentBackward", isComposing: false,
    preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(x.field.value.replace(/\D/g, ""), "8912345678");
  assert.equal(x.field.selectionStart, 2);
});