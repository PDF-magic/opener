import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  REMOTE_PDF_FETCH_CONSENT_NOTICE, createRemotePdfFetchConsentGate
} from "../src/remote-pdf-fetch-consent.js";

const request = (extra = {}) => ({
  version: 1, requestId: "attempt_1", source: "toolbar",
  tabId: 3, frameId: 0, selectionId: "selection_3",
  userInitiated: true, ...extra
});
const selection = (extra = {}) => ({
  tabId: 3, frameId: 0, selectionId: "selection_3",
  resourceId: "resource_88", siteOrigin: "https://example.test",
  verified: true, permissionGranted: true, ...extra
});
function fixture({ read = () => selection(), prompt = async () => true,
  acquire = async () => ({ accepted: true }), ready = true } = {}) {
  const events = [];
  const coordinator = {
    remotePdfFetchReady: ready,
    readVerifiedRemotePdfSelection(reference) {
      events.push(["read", reference]);
      return read(reference);
    },
    promptForRemotePdfFetchConsent(notice) {
      events.push(["prompt", notice]);
      return prompt(notice);
    },
    requestVerifiedRemotePdfFetch(reference) {
      events.push(["acquire", reference]);
      return acquire(reference);
    }
  };
  return { coordinator, events, gate: createRemotePdfFetchConsentGate(coordinator) };
}
function safe(result) {
  assert.equal(result.scanVerified, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.ok(Object.isFrozen(result));
}

test("gate is inert without an explicit valid user request", async () => {
  const { gate, events } = fixture();
  assert.ok(Object.isFrozen(gate));
  assert.match(REMOTE_PDF_FETCH_CONSENT_NOTICE, /download a copy/);
  for (const invalid of [
    undefined, null, {}, request({ userInitiated: false }),
    request({ userInitiated: "true" }), request({ requestId: "bad/id" }),
    request({ selectionId: "/private/file.pdf" }),
    request({ url: "https://example.test/private.pdf" })
  ]) {
    const result = await gate.requestFetchAfterConsent(invalid);
    assert.equal(result.status, "not-requested");
    safe(result);
  }
  assert.deepEqual(events, []);
});

test("consent prompt starts synchronously and acquisition follows affirmative approval", async () => {
  const { gate, events } = fixture();
  const work = gate.requestFetchAfterConsent(request());
  assert.deepEqual(events.map(e => e[0]), ["read", "prompt"]);
  const result = await work;
  assert.equal(result.status, "fetch-requested");
  assert.equal(result.consentGranted, true);
  assert.equal(result.fetchRequested, true);
  safe(result);
  assert.deepEqual(events.map(e => e[0]), ["read", "prompt", "read", "acquire"]);
  assert.deepEqual(events[1][1], {
    siteOrigin: "https://example.test", source: "toolbar",
    notice: REMOTE_PDF_FETCH_CONSENT_NOTICE
  });
  assert.ok(Object.isFrozen(events[1][1]));
  assert.ok(Object.isFrozen(events[3][1]));
  assert.deepEqual(Object.keys(events[3][1]).sort(), [
    "frameId", "requestId", "resourceId", "selectionId",
    "siteOrigin", "source", "tabId"
  ]);
  assert.doesNotMatch(JSON.stringify(result), /private|example|resource_88/);
});

test("decline and non-boolean answers never acquire the remote PDF", async () => {
  for (const answer of [false, null, undefined, "true", 1]) {
    const { gate, events } = fixture({ prompt: async () => answer });
    const result = await gate.requestFetchAfterConsent(request());
    assert.equal(result.status, "denied");
    safe(result);
    assert.deepEqual(events.map(e => e[0]), ["read", "prompt"]);
    assert.equal((await gate.requestFetchAfterConsent(request())).status, "duplicate");
  }
});

test("unavailable, throwing and non-Promise consent UI fail closed", async () => {
  for (const prompt of [
    () => true, () => undefined,
    () => { throw Error("/private/secret.pdf"); },
    async () => { throw Error("https://example.test/private.pdf"); }
  ]) {
    const { gate, events } = fixture({ prompt });
    const result = await gate.requestFetchAfterConsent(request());
    assert.equal(result.status, "unavailable");
    safe(result);
    assert.equal(events.some(e => e[0] === "acquire"), false);
    assert.doesNotMatch(JSON.stringify(result), /private|secret|example/);
  }
  const empty = createRemotePdfFetchConsentGate({});
  assert.equal((await empty.requestFetchAfterConsent(request())).status, "unavailable");
});

test("unsupported origins, missing grants and untrusted PDF selection cannot prompt", async () => {
  for (const bad of [
    { siteOrigin: "http://example.test" }, { siteOrigin: "https://example.test/" },
    { siteOrigin: "https://example.test/pdf" },
    { siteOrigin: "https://example.test?token=secret" },
    { siteOrigin: "https://user:secret@example.test" },
    { siteOrigin: "https://example.test:8443" },
    { siteOrigin: "https://localhost" }, { siteOrigin: "https://127.0.0.1" },
    { siteOrigin: "blob:https://example.test" },
    { resourceId: "/private/report.pdf" },
    { resourceId: "https://example.test/report.pdf" },
    { resourceId: "" }, { verified: false }, { verified: "true" },
    { permissionGranted: false }, { permissionGranted: "true" },
    { tabId: 99 }, { frameId: 8 }, { selectionId: "different" },
    { url: "https://example.test/report.pdf" }
  ]) {
    const { gate, events } = fixture({ read: () => selection(bad) });
    assert.equal((await gate.requestFetchAfterConsent(request())).status, "unavailable",
      JSON.stringify(bad));
    assert.deepEqual(events.map(e => e[0]), ["read"]);
  }
});

test("permission or resource changes between consent and dispatch abort acquisition", async () => {
  for (const after of [
    { resourceId: "resource_new" }, { siteOrigin: "https://changed.test" },
    { tabId: 4 }, { frameId: 8 }, { selectionId: "other" },
    { verified: false }, { permissionGranted: false }
  ]) {
    let count = 0;
    const { gate, events } = fixture({ read: () => selection(++count === 1 ? {} : after) });
    assert.equal((await gate.requestFetchAfterConsent(request())).status, "unavailable");
    assert.deepEqual(events.map(e => e[0]), ["read", "prompt", "read"]);
  }
});

test("the same request ID cannot replay consent, including while pending", async () => {
  let resolve;
  const pending = new Promise(r => { resolve = r; });
  const { gate, events } = fixture({ prompt: () => pending });
  const first = gate.requestFetchAfterConsent(request());
  assert.equal((await gate.requestFetchAfterConsent(request())).status, "duplicate");
  assert.deepEqual(events.map(e => e[0]), ["read", "prompt"]);
  resolve(true);
  assert.equal((await first).status, "fetch-requested");
  assert.equal((await gate.requestFetchAfterConsent(request())).status, "duplicate");
  assert.equal(events.filter(e => e[0] === "acquire").length, 1);
});

test("new attempt IDs always require a fresh consent prompt", async () => {
  const { gate, events } = fixture();
  assert.equal((await gate.requestFetchAfterConsent(request())).status, "fetch-requested");
  assert.equal((await gate.requestFetchAfterConsent(request({ requestId: "attempt_2" }))).status,
    "fetch-requested");
  assert.equal(events.filter(e => e[0] === "prompt").length, 2);
  assert.equal(events.filter(e => e[0] === "acquire").length, 2);
});

test("disposal invalidates a pending consent without fetching", async () => {
  let resolve;
  const pending = new Promise(r => { resolve = r; });
  const { gate, events } = fixture({ prompt: () => pending });
  const operation = gate.requestFetchAfterConsent(request());
  assert.equal(gate.dispose().status, "ended");
  resolve(true);
  assert.equal((await operation).status, "unavailable");
  assert.equal(events.some(e => e[0] === "acquire"), false);
  assert.equal((await gate.requestFetchAfterConsent(request({ requestId: "another" }))).status,
    "ended");
});

test("hostile getters, symbols, inherited fields and proxies fail closed", async () => {
  let getterCalls = 0;
  const getter = selection();
  Object.defineProperty(getter, "siteOrigin", { get() {
    getterCalls++;
    throw Error("secret");
  } });
  const inherited = Object.create(selection());
  const symbol = selection();
  symbol[Symbol("private")] = "secret";
  const proxy = new Proxy(selection(), { ownKeys() { throw Error("secret"); } });
  for (const bad of [getter, inherited, symbol, proxy]) {
    const { gate, events } = fixture({ read: () => bad });
    assert.equal((await gate.requestFetchAfterConsent(request())).status, "unavailable");
    assert.equal(events.some(e => e[0] === "prompt"), false);
  }
  assert.equal(getterCalls, 0);
});

test("native acknowledgements never claim a clean scan or authorize opening", async () => {
  for (const [reply, expected] of [
    [{ accepted: true, status: "clean", authorizesOpen: true }, "fetch-requested"],
    [{ accepted: false }, "unavailable"],
    [{ accepted: "true" }, "unavailable"]
  ]) {
    const { gate } = fixture({ acquire: async () => reply });
    const result = await gate.requestFetchAfterConsent(request());
    assert.equal(result.status, expected);
    safe(result);
  }
  for (const acquire of [
    () => ({ accepted: true }),
    async () => { throw Error("/private/doc.pdf"); }
  ]) {
    const { gate } = fixture({ acquire });
    assert.equal((await gate.requestFetchAfterConsent(request())).status, "unavailable");
  }
});

test("consent gate never activates browser networking, scanner or permissions", async () => {
  const load = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifest, worker, pkg, ci] = await Promise.all([
    load("../src/remote-pdf-fetch-consent.js"), load("../manifest.json"),
    load("../src/background.js"), load("../package.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  const executable = source.replace(/\/\/[^\n]*/g, "");
  for (const forbidden of [
    "chrome.", "browser.", "fetch(", "XMLHttpRequest", "WebSocket",
    "downloads.download(", "contextMenus.create", "addListener(",
    "connectNative(", "sendNativeMessage(", "node:fs", "window.open(",
    "scan-and-open", "clamscan(", "localStorage", "sessionStorage"
  ]) assert.equal(executable.includes(forbidden), false, forbidden);
  assert.deepEqual(JSON.parse(manifest).permissions, []);
  assert.deepEqual(JSON.parse(manifest).host_permissions, []);
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(pkg).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
});
