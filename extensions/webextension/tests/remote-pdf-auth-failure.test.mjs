import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  REMOTE_PDF_AUTH_FAILURE_CODES, createRemotePdfAuthenticationFailureHandler
} from "../src/remote-pdf-auth-failure.js";

const event = (patch = {}) => ({
  requestId: "attempt_1", downloadId: 54, kind: "http", code: 401, ...patch
});
const transfer = (patch = {}) => ({
  requestId: "attempt_1", downloadId: 54,
  selectionId: "selected_88", verified: true, ...patch
});
function fixture({ read = () => transfer(), notify = () => {} } = {}) {
  const calls = [];
  const coordinator = {
    readVerifiedRemotePdfTransfer(reference) {
      calls.push(["read", reference]);
      return read(reference);
    },
    notifyRemotePdfAuthenticationFailure(result) {
      calls.push(["notify", result]);
      return notify(result);
    }
  };
  return { calls, coordinator,
    handler: createRemotePdfAuthenticationFailureHandler(coordinator) };
}
function blocked(result) {
  assert.equal(result.scanVerified, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.equal(result.automaticallyRetry, false);
  assert.ok(Object.isFrozen(result));
}

test("HTTP 401/403/407 failures produce distinct safe browser guidance", () => {
  assert.deepEqual(REMOTE_PDF_AUTH_FAILURE_CODES.http, [401, 403, 407]);
  assert.deepEqual(REMOTE_PDF_AUTH_FAILURE_CODES.download,
    ["SERVER_UNAUTHORIZED", "SERVER_FORBIDDEN"]);
  assert.ok(Object.isFrozen(REMOTE_PDF_AUTH_FAILURE_CODES));
  for (const [code, reason, status, pattern] of [
    [401, "sign-in-required", "authentication-required", /sign in/i],
    [403, "access-denied", "access-denied", /denied access/i],
    [407, "proxy-sign-in-required", "authentication-required", /proxy authentication/i]
  ]) {
    const f = fixture();
    const result = f.handler.observeFailure(event({ code }));
    assert.equal(result.reason, reason);
    assert.equal(result.status, status);
    assert.match(result.message, pattern);
    assert.equal(result.manualRetryRequired, true);
    assert.equal(result.requestId, "attempt_1");
    assert.equal(result.downloadId, 54);
    assert.equal(f.handler.isBlocked("attempt_1"), true);
    blocked(result);
    assert.equal(f.calls.length, 2);
    assert.deepEqual(Object.keys(f.calls[0][1]), ["requestId", "downloadId"]);
  }
});

test("supported download errors map to authentication failure without raw errors", () => {
  for (const [code, reason] of [
    ["SERVER_UNAUTHORIZED", "sign-in-required"],
    ["SERVER_FORBIDDEN", "access-denied"]
  ]) {
    const f = fixture();
    const result = f.handler.observeFailure(event({ kind: "download", code }));
    assert.equal(result.reason, reason);
    blocked(result);
    assert.equal(f.handler.isBlocked("attempt_1"), true);
    assert.doesNotMatch(JSON.stringify(result), /SERVER_|PRIVATE|https:/);
  }
});

test("a response failure can be handled before download ID allocation", () => {
  const f = fixture({ read: () => transfer({ downloadId: null }) });
  const result = f.handler.observeFailure(event({ downloadId: null }));
  assert.equal(result.reason, "sign-in-required");
  assert.equal(result.downloadId, null);
  blocked(result);
  assert.equal(f.handler.isBlocked("attempt_1"), true);
  assert.equal(f.handler.observeFailure(event({
    downloadId: null, kind: "download", code: "SERVER_UNAUTHORIZED"
  })).status, "unavailable");
});

test("non-authentication network errors do not masquerade as sign-in prompts", () => {
  for (const [kind, code] of [
    ["http", 200], ["http", 302], ["http", 404], ["http", 408],
    ["http", 429], ["http", 500], ["http", "401"], ["http", -1],
    ["download", "SERVER_FAILED"], ["download", "NETWORK_FAILED"],
    ["download", "USER_CANCELED"], ["download", "SERVER_UNAUTHORIZED_EXTRA"],
    ["download", "server_unauthorized"], ["download", 401],
    ["other", 401]
  ]) {
    const f = fixture();
    const result = f.handler.observeFailure(event({ kind, code }));
    assert.equal(result.status, "unavailable", String(code));
    blocked(result);
    assert.equal(f.calls.length, 0);
    assert.equal(f.handler.isBlocked("attempt_1"), false);
  }
});

test("untrusted request IDs and malformed download IDs cannot trigger UI", () => {
  const mutations = [
    { requestId: "" }, { requestId: "../private.pdf" },
    { requestId: "a".repeat(81) }, { requestId: 123 },
    { downloadId: -1 }, { downloadId: "54" }, { downloadId: 1.5 },
    { downloadId: Number.MAX_SAFE_INTEGER + 1 },
    { downloadId: undefined }, { downloadId: NaN },
    { kind: "download", code: "SERVER_UNAUTHORIZED", downloadId: null },
    { url: "https://example.test/report.pdf?cookie=private" },
    { error: "SERVER_UNAUTHORIZED" }, { responseHeaders: [] },
    { authorization: "Bearer secret" }, { cookies: "secret" }
  ];
  for (const invalid of mutations) {
    const f = fixture();
    assert.equal(f.handler.observeFailure(event(invalid)).status, "unavailable",
      JSON.stringify(invalid));
    assert.deepEqual(f.calls, []);
  }
});

test("only trusted exact request/download/selection correlation may block an attempt", () => {
  for (const change of [
    { requestId: "other" }, { downloadId: 19 },
    { selectionId: "" }, { selectionId: "/private/report.pdf" },
    { selectionId: "attempt_1" }, { verified: false },
    { verified: "true" }, { url: "https://example.test/private.pdf" },
    { status: "clean" }
  ]) {
    const f = fixture({ read: () => transfer(change) });
    assert.equal(f.handler.observeFailure(event()).status, "unavailable");
    assert.deepEqual(f.calls.map(x => x[0]), ["read"]);
    assert.equal(f.handler.isBlocked("attempt_1"), false);
  }
  for (const read of [
    () => undefined, () => null, () => Promise.resolve(transfer()),
    () => { throw Error("Authorization: Bearer private"); }
  ]) {
    const f = fixture({ read });
    const result = f.handler.observeFailure(event());
    assert.equal(result.status, "unavailable");
    assert.doesNotMatch(JSON.stringify(result), /Bearer|private/);
    assert.equal(f.calls.some(x => x[0] === "notify"), false);
  }
});

test("auth failure is latched before notifying, including when notice callback throws", () => {
  let handler;
  let blockedDuringNotification = false;
  const f = fixture({ notify: () => {
    blockedDuringNotification = handler.isBlocked("attempt_1");
    throw Error("https://example.test/report.pdf?secret=private");
  } });
  handler = f.handler;
  const first = handler.observeFailure(event());
  assert.equal(blockedDuringNotification, true);
  assert.equal(first.reason, "sign-in-required");
  assert.equal(handler.isBlocked("attempt_1"), true);
  assert.strictEqual(handler.observeFailure(event()), first);
  assert.deepEqual(f.calls.map(x => x[0]), ["read", "notify", "read"]);
  assert.doesNotMatch(JSON.stringify(first), /secret|example/);
});

test("repeated and changed failure codes cannot silently unlock an attempt", () => {
  const f = fixture();
  const original = f.handler.observeFailure(event());
  assert.equal(original.reason, "sign-in-required");
  const second = f.handler.observeFailure(event({ code: 403 }));
  assert.strictEqual(second, original);
  assert.equal(f.handler.isBlocked("attempt_1"), true);
  assert.equal(f.calls.filter(x => x[0] === "notify").length, 1);
  assert.equal(f.handler.isBlocked("attempt_2"), false);
  assert.equal(f.handler.isBlocked(""), true);
  assert.equal(f.handler.isBlocked(123), true);
});

test("fail-closed handling of accessors, proxies, symbols and inherited data", () => {
  let getterCalls = 0;
  const accessor = event();
  Object.defineProperty(accessor, "code", { get() {
    getterCalls++;
    throw Error("must not read");
  } });
  const inherited = Object.create(event());
  const symbol = event();
  symbol[Symbol("token")] = "secret";
  const proxy = new Proxy(event(), { ownKeys() {
    throw Error("secret");
  } });
  for (const invalid of [null, undefined, [], 3, accessor, inherited, symbol, proxy]) {
    const f = fixture();
    assert.equal(f.handler.observeFailure(invalid).status, "unavailable");
    assert.deepEqual(f.calls, []);
  }
  assert.equal(getterCalls, 0);
  const trustedAccessor = transfer();
  Object.defineProperty(trustedAccessor, "verified", { get() {
    getterCalls++;
    return true;
  } });
  const f = fixture({ read: () => trustedAccessor });
  assert.equal(f.handler.observeFailure(event()).status, "unavailable");
  assert.equal(getterCalls, 0);
  const nullProto = Object.assign(Object.create(null), event());
  assert.equal(fixture().handler.observeFailure(nullProto).reason, "sign-in-required");
});

test("handler is inert without an authenticated coordinator and closes on disposal", () => {
  const absent = createRemotePdfAuthenticationFailureHandler();
  const response = absent.observeFailure(event());
  assert.equal(response.status, "unavailable");
  blocked(response);
  assert.equal(absent.isBlocked("attempt_1"), false);
  assert.ok(Object.isFrozen(absent));
  assert.equal(absent.dispose().status, "ended");
  assert.equal(absent.isBlocked("attempt_1"), true);
  assert.equal(absent.observeFailure(event()).status, "ended");
  assert.equal(absent.dispose().status, "ended");
});

test("bounded correlation cache refuses additional failures without granting scans", () => {
  const f = fixture({ read: context => transfer({
    requestId: context.requestId, downloadId: context.downloadId
  }) });
  for (let i = 0; i < 256; i++) {
    assert.equal(f.handler.observeFailure(event({
      requestId: "attempt_" + i, downloadId: i
    })).status, "authentication-required");
  }
  assert.equal(f.handler.observeFailure(event({
    requestId: "attempt_overflow", downloadId: 300
  })).status, "unavailable");
  assert.equal(f.handler.isBlocked("attempt_0"), true);
  assert.equal(f.calls.filter(x => x[0] === "notify").length, 256);
});

test("handler introduces no login prompts, credential access, downloads or native scanner bypass", async () => {
  const load = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifestText, background, pkg, workflow] = await Promise.all([
    load("../src/remote-pdf-auth-failure.js"),
    load("../manifest.json"),
    load("../src/background.js"),
    load("../package.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(JSON.parse(pkg).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(workflow, /npm test/);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "fetch(", "XMLHttpRequest",
    "downloads.download(", "downloads.open(", "permissions.request(",
    "sendNativeMessage(", "connectNative(", "window.open(", "localStorage",
    "sessionStorage", "node:fs", "scan-and-open", "clamscan("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
