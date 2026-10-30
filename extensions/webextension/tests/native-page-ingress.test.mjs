import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createNativePageIngress } from "../src/native-page-ingress.js";

const chromeId = "abcdefghijklmnopabcdefghijklmnop";
const chromeBase = `chrome-extension://${chromeId}/`;
const geckoId = "pdf-magic-opener@example.invalid";
const firefoxBase = "moz-extension://123e4567-e89b-12d3-a456-426614174000/";
const health = () => ({
  version: 1, kind: "request", topic: "host.health", requestId: "check_1", payload: null
});
const sender = (base = chromeBase, id = chromeId) => ({ id, url: `${base}popup.html` });

function rig(options = {}) {
  const calls = [];
  const gate = createNativePageIngress({
    extensionId: chromeId, extensionBaseUrl: chromeBase,
    onReadOnlyRequest(message) { calls.push(message); }, ...options
  });
  return { gate, calls };
}

test("only the browser-provided internal extension sender reaches a read-only callback", () => {
  const { gate, calls } = rig();
  const input = health();
  assert.equal(gate.handleRuntimeMessage(input, sender()), true);
  assert.deepEqual(calls, [health()]);
  assert.notEqual(calls[0], input);
  assert.equal(Object.isFrozen(calls[0]), true);
  input.topic = "scan.request";
  assert.equal(calls[0].topic, "host.health");
  assert.equal(gate.handleRuntimeMessage({ ...health(), topic: "host.ping" }, sender()), true);
  assert.equal(calls.length, 2);
});

test("untrusted webpages, content scripts, external origins, and frames cannot request native actions", () => {
  const { gate, calls } = rig();
  const denied = [
    { id: chromeId, url: "https://example.org/popup.html" },
    { id: chromeId, url: "file:///private/file.html" },
    { id: chromeId, url: `${chromeBase}popup.html`, tab: { id: 5 } },
    { id: chromeId, url: `${chromeBase}popup.html`, tab: undefined },
    { id: chromeId, url: `${chromeBase}popup.html`, frameId: 0 },
    { id: chromeId, url: `${chromeBase}popup.html`, origin: "https://example.org" },
    { id: chromeId, url: `chrome-extension://${chromeId}evil/popup.html` },
    { id: "ponmlkjihgfedcbaponmlkjihgfedcba", url: `${chromeBase}popup.html` },
    { url: `${chromeBase}popup.html` }, {}, null,
    Object.assign(Object.create({ id: chromeId }), { url: `${chromeBase}popup.html` })
  ];
  for (const forged of denied) assert.equal(gate.handleRuntimeMessage(health(), forged), false);
  assert.deepEqual(calls, []);
});

test("native scan, open, process, permissions and arbitrary page-supplied payloads never reach callback", () => {
  const { gate, calls } = rig();
  for (const topic of ["scan.request", "scan.status", "scan.cancel", "scan.result", "pdf.open", "process.exec", "host.handshake", "unknown"])
    assert.equal(gate.handleRuntimeMessage({ ...health(), topic }, sender()), false, topic);
  for (const bad of [
    { ...health(), payload: { path: "/private/document.pdf" } },
    { ...health(), payload: { userInitiated: true } },
    { ...health(), payload: { connectNative: "org.pdfmagic.opener" } },
    { ...health(), allowOpen: true },
    { ...health(), requestId: "../../escape" },
    { ...health(), version: 2 },
    { ...health(), kind: "event" },
    { ...health(), payload: undefined },
    { ...health(), payload: false }, "host.health", [], null
  ]) assert.equal(gate.handleRuntimeMessage(bad, sender()), false);
  assert.deepEqual(calls, []);
});

test("Firefox allows an internal moz-extension page, not a normal website or mismatched Gecko identity", () => {
  const { gate, calls } = rig({ extensionId: geckoId, extensionBaseUrl: firefoxBase });
  assert.equal(gate.handleRuntimeMessage(health(), sender(firefoxBase, geckoId)), true);
  assert.equal(calls.length, 1);
  assert.equal(gate.handleRuntimeMessage(health(), sender(chromeBase, geckoId)), false);
  assert.equal(gate.handleRuntimeMessage(health(), sender(firefoxBase, "other@example.invalid")), false);
  assert.equal(gate.handleRuntimeMessage(health(), {
    ...sender(firefoxBase, geckoId), tab: { id: 3 }
  }), false);
  assert.equal(calls.length, 1);
});

test("invalid extension origins and missing handler fail closed", () => {
  for (const base of ["https://example.org/", "file:///tmp/", `chrome-extension://${chromeId}evil/`,
    `chrome-extension://${chromeId}/other/`, `chrome-extension://${chromeId}/?allowed=1`,
    "moz-extension://not-a-uuid/"] ) {
    const { gate, calls } = rig({ extensionBaseUrl: base });
    assert.equal(gate.handleRuntimeMessage(health(), sender()), false);
    assert.deepEqual(calls, []);
  }
  assert.equal(createNativePageIngress({ extensionId: chromeId, extensionBaseUrl: chromeBase })
    .handleRuntimeMessage(health(), sender()), false);
});

test("hostile getters, inherited messages, accessor IDs and symbols never execute or dispatch", () => {
  let getterCalls = 0;
  const badSender = sender();
  Object.defineProperty(badSender, "url", { get() { getterCalls++; throw Error("private"); } });
  const badMessage = health();
  Object.defineProperty(badMessage, "topic", { get() { getterCalls++; throw Error("private"); } });
  const withSymbol = health();
  withSymbol[Symbol("unsafe")] = true;
  const { gate, calls } = rig();
  for (const [message, from] of [[health(), badSender], [badMessage, sender()],
    [withSymbol, sender()], [Object.assign(Object.create(health()), {}), sender()]]) {
    assert.equal(gate.handleRuntimeMessage(message, from), false);
  }
  assert.equal(getterCalls, 0);
  assert.equal(calls.length, 0);
});

test("the current packaged workers and manifests cannot expose native control to webpages", async () => {
  const base = new URL("../", import.meta.url);
  const worker = await readFile(new URL("src/background.js", base), "utf8");
  for (const name of ["src/background.js", "dist/background.js", "dist/firefox/background.js"])
    assert.equal(await readFile(new URL(name, base), "utf8"), worker);
  for (const name of ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"]) {
    const manifest = JSON.parse(await readFile(new URL(name, base), "utf8"));
    for (const disallowed of ["content_scripts", "externally_connectable", "web_accessible_resources"])
      assert.equal(Object.hasOwn(manifest, disallowed), false, name);
    assert.equal(manifest.permissions.includes("nativeMessaging"), false);
    assert.equal(manifest.optional_permissions.includes("nativeMessaging"), false);
  }
  const source = await readFile(new URL("src/native-page-ingress.js", base), "utf8");
  for (const forbidden of ["onMessageExternal", "window.postMessage", "window.addEventListener", "connectNative(", "sendNativeMessage("])
    assert.equal(source.includes(forbidden), false, forbidden);
});
