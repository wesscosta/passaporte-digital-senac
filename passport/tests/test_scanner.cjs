"use strict";
const assert = require("node:assert/strict");
const { validateQrText } = require("../static/passport/scanner.js");
const origin = "https://passaporte.example";

assert.equal(validateQrText(origin + "/visitar/1/123456/", origin), "/visitar/1/123456/");
assert.equal(validateQrText("/visitar/42/000001/", origin), "/visitar/42/000001/");
for (const value of [
  "https://malicioso.example/visitar/1/123456/",
  "https://passaporte.example.malicioso.example/visitar/1/123456/",
  "javascript:alert(1)",
  "/visitar/0/123456/",
  "/visitar/1/12345/",
  "/visitar/1/123456/?redirect=https://malicioso.example",
  "/visitar/1/123456/#destino",
  "/admin/",
]) {
  assert.equal(validateQrText(value, origin), null, value);
}
console.log("Validação de URLs do leitor: OK");
