import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  EXPIRED_PDF_URL_FAILURE_CODES, createExpiredPdfUrlHandler
} from "../src/expired-pdf-url.js";

const event = (patch = {}) => ({
  requestId: "scan_1", downloadId: 12, kind: "http", code: 410, ...patch
});
const source = (patch = {}) => ({
  requestId: "scan_1", downloadId: 12,
  selectionId: "selected_1", resourceId: "document_2",
  expiresAtMs: null, observedAtMs: 20000, verified: true, ...patch
});
function fixture({ read = () => source(), notify = () => {} } = {}) {
  const calls = [];
  const coordinator = {
    readVerifiedRemotePdfUrlSource(reference) {
      calls.push(["read", reference]);
      return read(reference);
    },
    notifyExpiredPdfUrl(response) {
      calls.push(["notify", response]);
      return notify(response);
    }
  };
  return { calls, coordinator, handler: createExpiredPdfUrlHandler(coordinator) };
}
function safe(response) {
  assert.equal(response.scanVerified, false);
  assert.equal(response.authorizesScan, false);
  assert.equal(response.authorizesOpen, false);
  assert.equal(response.automaticallyRetry, false);
  assert.ok(Object.isFrozen(response));
}

test("HTTP 410 blocks a verified, permanently unavailable PDF link", () => {
  assert.deepEqual(EXPIRED_PDF_URL_FAILURE_CODES, {
    http: [403, 404, 410], expiry: "DEADLINE_PASSED"
  });
  assert.ok(Object.isFrozen(EXPIRED_PDF_URL_FAILURE_CODES));
  assert.ok(Object.isFrozen(EXPIRED_PDF_URL_FAILURE_CODES.http));
  const f = fixture();
  const result = f.handler.observeFailure(event());
  assert.equal(result.status, "expired-document-url");
  assert.equal(result.reason, "gone");
  assert.match(result.message, /new link/i);
  assert.equal(result.requiresNewDocumentLink, true);
  assert.equal(result.requiresNewConsent, true);
  assert.equal(result.requestId, "scan_1");
  assert.equal(result.downloadId, 12);
  assert.equal(f.handler.isBlocked("scan_1"), true);
  safe(result);
  assert.deepEqual(f.calls.map(x => x[0]), ["read", "notify"]);
  assert.deepEqual(f.calls[0][1], { requestId: "scan_1", downloadId: 12 });
  assert.ok(Object.isFrozen(f.calls[0][1]));
});

test("403 and 404 are expired only with verified elapsed deadline metadata", () => {
  for (const code of [403, 404]) {
    const f = fixture({ read: () => source({ expiresAtMs: 19999 }) });
    const result = f.handler.observeFailure(event({ code }));
    assert.equal(result.status, "expired-document-url");
    assert.equal(result.reason, "expired");
    assert.match(result.message, /expired/i);
    assert.equal(f.handler.isBlocked("scan_1"), true);
    safe(result);
  }
  for (const expiresAtMs of [null, 20001, 999999]) {
    for (const code of [403, 404]) {
      const f = fixture({ read: () => source({ expiresAtMs }) });
      assert.equal(f.handler.observeFailure(event({ code })).status, "unavailable");
      assert.equal(f.handler.isBlocked("scan_1"), false);
      assert.deepEqual(f.calls.map(x => x[0]), ["read"]);
    }
  }
});

test("verified explicit deadline check blocks an expired URL without a response", () => {
  const f = fixture({ read: () => source({ expiresAtMs: 20000, downloadId: null }) });
  const result = f.handler.observeFailure(event({
    kind: "expiry", code: "DEADLINE_PASSED", downloadId: null
  }));
  assert.equal(result.reason, "expired");
  assert.equal(result.downloadId, null);
  assert.equal(f.handler.isBlocked("scan_1"), true);
  safe(result);
  const fresh = fixture({ read: () => source({ expiresAtMs: 20001, downloadId: null }) });
  assert.equal(fresh.handler.observeFailure(event({
    kind: "expiry", code: "DEADLINE_PASSED", downloadId: null
  })).status, "unavailable");
});

test("login failures and other statuses do not masquerade as expired URLs", () => {
  const unsupported = [
    ["http", 200], ["http", 302], ["http", 401], ["http", 407],
    ["http", 408], ["http", 429], ["http", 500], ["http", "410"],
    ["http", -1], ["download", "SERVER_UNAUTHORIZED"],
    ["download", "SERVER_FORBIDDEN"], ["download", "SERVER_FAILED"],
    ["download", "NETWORK_FAILED"], ["expiry", "EXPIRED"],
    ["expiry", false], ["other", 410]
  ];
  for (const [kind, code] of unsupported) {
    const f = fixture({ read: () => source({ expiresAtMs: 10000 }) });
    const result = f.handler.observeFailure(event({ kind, code }));
    assert.equal(result.status, "unavailable", kind + ":" + code);
    safe(result);
    assert.equal(f.calls.length, 0);
    assert.equal(f.handler.isBlocked("scan_1"), false);
  }
});

test("rejects spoofed requests, injected URLs, cookies, headers and invalid IDs", () => {
  for (const patch of [
    { requestId: "" }, { requestId: "../private.pdf" },
    { requestId: "x".repeat(81) }, { requestId: 3 },
    { downloadId: -1 }, { downloadId: "12" }, { downloadId: 1.25 },
    { downloadId: Number.MAX_SAFE_INTEGER + 1 },
    { downloadId: undefined }, { downloadId: NaN },
    { code: 410, url: "https://example.test/doc.pdf?token=secret" },
    { cookie: "secret" }, { responseHeaders: { Authorization: "secret" } },
    { expiresAtMs: 0 }, { userInitiated: true }, { clean: true }
  ]) {
    const f = fixture();
    assert.equal(f.handler.observeFailure(event(patch)).status, "unavailable");
    assert.deepEqual(f.calls, []);
  }
});

test("trusted source must match the exact current scan attempt and document IDs", () => {
  for (const patch of [
    { requestId: "other" }, { downloadId: 13 },
    { selectionId: "" }, { selectionId: "/private/doc.pdf" },
    { selectionId: "scan_1" }, { resourceId: "" },
    { resourceId: "https://example.test/pdf" },
    { resourceId: "scan_1" }, { verified: false },
    { verified: "true" }, { url: "https://example.test/doc.pdf" },
    { mime: "application/pdf" }, { siteOrigin: "https://example.test" }
  ]) {
    const f = fixture({ read: () => source(patch) });
    assert.equal(f.handler.observeFailure(event()).status, "unavailable");
    assert.deepEqual(f.calls.map(x => x[0]), ["read"]);
    assert.equal(f.handler.isBlocked("scan_1"), false);
  }
});

test("invalid, page-supplied or missing expiry evidence cannot silently authorize a retry", () => {
  for (const expiresAtMs of [
    -1, 0, 1.3, "1000", Number.MAX_SAFE_INTEGER + 1,
    undefined, {}, new Date(1000)
  ]) {
    const f = fixture({ read: () => source({ expiresAtMs }) });
    assert.equal(f.handler.observeFailure(event({ code: 403 })).status, "unavailable");
    assert.equal(f.handler.isBlocked("scan_1"), false);
  }
  for (const observedAtMs of [
    null, -1, 1.3, "20000", undefined, Infinity,
    Number.MAX_SAFE_INTEGER + 1
  ]) {
    const f = fixture({ read: () => source({ expiresAtMs: 10000, observedAtMs }) });
    assert.equal(f.handler.observeFailure(event({ code: 403 })).status, "unavailable");
  }
});

test("a failure is latched before notification and cannot be undone by errors", () => {
  let handler;
  let blockedAtNotification = false;
  const f = fixture({ notify: () => {
    blockedAtNotification = handler.isBlocked("scan_1");
    throw Error("https://example.test/doc.pdf?token=secret");
  } });
  handler = f.handler;
  const result = handler.observeFailure(event());
  assert.equal(blockedAtNotification, true);
  assert.equal(result.status, "expired-document-url");
  assert.equal(handler.isBlocked("scan_1"), true);
  assert.strictEqual(handler.observeFailure(event({ code: 403 })), result);
  assert.deepEqual(f.calls.map(x => x[0]), ["read", "notify", "read"]);
  assert.doesNotMatch(JSON.stringify(result), /token|secret|example/);
});

test("one expired URL cannot cause automatic retries or reuse a new attempt", () => {
  const f = fixture();
  assert.equal(f.handler.observeFailure(event()).status, "expired-document-url");
  assert.equal(f.handler.isBlocked("scan_1"), true);
  assert.equal(f.handler.isBlocked("scan_2"), false);
  assert.equal(f.calls.filter(x => x[0] === "notify").length, 1);
  assert.equal(f.handler.isBlocked(""), true);
  assert.equal(f.handler.isBlocked(123), true);
});

test("hostile getters, inherited records, symbols and proxies fail closed", () => {
  let calls = 0;
  const accessor = event();
  Object.defineProperty(accessor, "code", { get() { calls++; return 410; } });
  const inherited = Object.create(event());
  const symbol = event();
  symbol[Symbol("secret")] = true;
  const proxy = new Proxy(event(), { ownKeys() { throw Error("secret"); } });
  for (const bad of [null, undefined, "", [], accessor, inherited, symbol, proxy]) {
    const f = fixture();
    assert.equal(f.handler.observeFailure(bad).status, "unavailable");
    assert.deepEqual(f.calls, []);
  }
  const trustedGetter = source();
  Object.defineProperty(trustedGetter, "verified", { get() { calls++; return true; } });
  assert.equal(fixture({ read: () => trustedGetter })
    .handler.observeFailure(event()).status, "unavailable");
  assert.equal(calls, 0);
  const normal = Object.assign(Object.create(null), event());
  assert.equal(fixture().handler.observeFailure(normal).reason, "gone");
});

test("missing or asynchronous trust evidence cannot create expiry failures", () => {
  for (const read of [
    () => null, () => undefined, () => Promise.resolve(source()),
    () => { throw Error("https://example.test/private.pdf?secret=abc"); }
  ]) {
    const f = fixture({ read });
    const result = f.handler.observeFailure(event());
    assert.equal(result.status, "unavailable");
    safe(result);
    assert.equal(f.calls.filter(x => x[0] === "notify").length, 0);
  }
  const empty = createExpiredPdfUrlHandler();
  assert.equal(empty.observeFailure(event()).status, "unavailable");
  assert.equal(empty.isBlocked("scan_1"), false);
});

test("cache remains bounded and a disposed handler stays closed", () => {
  const f = fixture({ read: ref => source({
    requestId: ref.requestId, downloadId: ref.downloadId
  }) });
  for (let i = 0; i < 256; i++) {
    assert.equal(f.handler.observeFailure(event({
      requestId: "attempt_" + i, downloadId: i
    })).status, "expired-document-url");
  }
  assert.equal(f.handler.observeFailure(event({
    requestId: "overflow", downloadId: 257
  })).status, "unavailable");
  assert.equal(f.calls.filter(x => x[0] === "notify").length, 256);
  assert.equal(f.handler.isBlocked("attempt_0"), true);
  assert.equal(f.handler.dispose().status, "ended");
  assert.equal(f.handler.isBlocked("attempt_0"), true);
  assert.equal(f.handler.observeFailure(event()).status, "ended");
  assert.equal(f.handler.dispose().status, "ended");
  assert.ok(Object.isFrozen(f.handler));
});

test("expiry handler never registers fetches, login, downloads or scanner bypass", async () => {
  const load = path => readFile(new URL(path, import.meta.url), "utf8");
  const [moduleText, manifestText, background, pkg, workflow] = await Promise.all([
    load("../src/expired-pdf-url.js"), load("../manifest.json"),
    load("../src/background.js"), load("../package.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  assert.deepEqual(JSON.parse(manifestText).permissions, []);
  assert.deepEqual(JSON.parse(manifestText).host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(pkg).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(workflow, /npm test/);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "fetch(", "XMLHttpRequest",
    "downloads.download(", "downloads.open(", "permissions.request(",
    "connectNative(", "sendNativeMessage(", "window.open(",
    "localStorage", "sessionStorage", "node:fs", "scan-and-open",
    "clamscan("
  ]) assert.equal(moduleText.includes(forbidden), false, forbidden);
});
