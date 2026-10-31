import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS,
  createPdfInterceptionNavigationLoopGuard
} from "../src/pdf-interception-navigation-loop-guard.js";

const request = (requestId = "req_1", tabId = 7) =>
  ({ requestId, tabId, frameId: 0 });
const snapshot = (ref, patch = {}) =>
  ({ ...ref, navigationId: "nav_1", origin: "web",
    destination: "web-pdf", verified: true, ...patch });
const coordinator = (transform = snapshot) => ({
  loopGuardReady: true,
  readVerifiedNavigation(ref) { return transform(ref); }
});
const read = path => readFile(new URL(path, import.meta.url), "utf8");

function safe(result, suppress = true) {
  assert.ok(Object.isFrozen(result));
  assert.equal(result.suppressAutomaticInterception, suppress);
  assert.equal(result.reservationRecorded, !suppress);
  assert.equal(result.navigationRequested, false);
  assert.equal(result.scanVerified, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(result), /pdf|token|secret|https?:|file:\/\//i);
}

test("one verified external top-frame PDF may reserve an attempt, never an open", () => {
  const gate = createPdfInterceptionNavigationLoopGuard(coordinator());
  const result = gate.reserveAttempt(request());
  assert.equal(result.status, "reserved-for-independent-review");
  safe(result, false);
});

test("extension and PDFOpener sourced navigation never enters interception", () => {
  for (const origin of ["extension", "pdfopener", "unknown"]) {
    const gate = createPdfInterceptionNavigationLoopGuard(
      coordinator(ref => snapshot(ref, { origin })));
    const result = gate.reserveAttempt(request());
    assert.equal(result.status, "extension-or-pdfopener-route");
    safe(result);
  }
});

test("a browser URL redirecting to extension or PDFOpener cannot be intercepted", () => {
  for (const destination of ["extension", "pdfopener", "unknown"]) {
    const gate = createPdfInterceptionNavigationLoopGuard(
      coordinator(ref => snapshot(ref, { destination })));
    const result = gate.reserveAttempt(request());
    assert.equal(result.status, "extension-or-pdfopener-route");
    safe(result);
  }
});

test("same request in same or different tabs can never be reserved twice", () => {
  const gate = createPdfInterceptionNavigationLoopGuard(coordinator());
  safe(gate.reserveAttempt(request()), false);
  assert.equal(gate.reserveAttempt(request()).status, "duplicate-navigation");
  assert.equal(gate.reserveAttempt(request("req_1", 20)).status, "duplicate-navigation");
  safe(gate.reserveAttempt(request("req_1", 20)));
});

test("a changed navigation ID or request in one tab does not reset the latch", () => {
  let next = "first";
  const gate = createPdfInterceptionNavigationLoopGuard(
    coordinator(ref => snapshot(ref, { navigationId: next })));
  safe(gate.reserveAttempt(request("req_1", 1)), false);
  next = "second";
  const result = gate.reserveAttempt(request("req_2", 1));
  assert.equal(result.status, "tab-already-reserved");
  safe(result);
  // Other independent tabs can still be evaluated.
  safe(gate.reserveAttempt(request("req_3", 2)), false);
});

test("failed and unknown verifier results deny by default, without a reservation", () => {
  const rejects = [
    null, {}, undefined, false,
    snapshot(request(), { verified: false }),
    snapshot(request(), { requestId: "different" }),
    snapshot(request(), { tabId: 10 }),
    snapshot(request(), { frameId: 1 }),
    snapshot(request(), { navigationId: "../path" }),
    snapshot(request(), { navigationId: "" }),
    snapshot(request(), { origin: "untrusted" }),
    snapshot(request(), { destination: "file" })
  ];
  for (const result of rejects) {
    const gate = createPdfInterceptionNavigationLoopGuard(coordinator(() => result));
    const denied = gate.reserveAttempt(request());
    assert.equal(denied.status, "unverified-navigation");
    safe(denied);
  }
  assert.equal(
    createPdfInterceptionNavigationLoopGuard().reserveAttempt(request()).status,
    "unverified-navigation"
  );
});

test("untrusted claims and invalid frame or tab references are rejected", () => {
  for (const ref of [
    undefined, null, [], {}, { ...request(), frameId: 1 },
    { ...request(), tabId: -1 }, { ...request(), tabId: 1.5 },
    { ...request(), requestId: "bad/id" }, { ...request(), requestId: "" },
    { ...request(), url: "https://secret.test/token.pdf" },
    Object.create(request())
  ]) {
    const gate = createPdfInterceptionNavigationLoopGuard(coordinator());
    assert.equal(gate.reserveAttempt(ref).status, "unverified-navigation");
    safe(gate.reserveAttempt(ref));
  }
});

test("getter, inherited, symbol and proxy metadata cannot grant an attempt", () => {
  const accessor = request();
  Object.defineProperty(accessor, "requestId", { get() {
    throw new Error("https://secret.test/token.pdf");
  } });
  const symbol = request();
  symbol[Symbol("ignored")] = true;
  const proxy = new Proxy(request(), {
    ownKeys() { throw new Error("file:///private/contract.pdf"); }
  });
  for (const ref of [accessor, symbol, proxy]) {
    const gate = createPdfInterceptionNavigationLoopGuard(coordinator());
    assert.equal(gate.reserveAttempt(ref).status, "unverified-navigation");
  }
  const malicious = snapshot(request());
  Object.defineProperty(malicious, "origin", { get() {
    throw new Error("https://secret.test/token.pdf");
  } });
  const gate = createPdfInterceptionNavigationLoopGuard(coordinator(() => malicious));
  safe(gate.reserveAttempt(request()));
});

test("reentrant verifier can reserve at most one attempt", () => {
  let gate;
  let inner;
  let entered = false;
  gate = createPdfInterceptionNavigationLoopGuard(coordinator(ref => {
    if (!entered) {
      entered = true;
      inner = gate.reserveAttempt(ref);
    }
    return snapshot(ref);
  }));
  const outer = gate.reserveAttempt(request());
  assert.equal(inner.status, "reserved-for-independent-review");
  assert.equal(outer.status, "duplicate-navigation");
  safe(inner, false);
  safe(outer);
});

test("bounded reservations fail closed rather than evict old tab or request IDs", () => {
  assert.equal(PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS, 256);
  const gate = createPdfInterceptionNavigationLoopGuard(coordinator());
  for (let i = 0; i < PDF_INTERCEPTION_LOOP_GUARD_MAX_RESERVATIONS; i++) {
    safe(gate.reserveAttempt(request("req_" + i, i)), false);
  }
  const result = gate.reserveAttempt(request("req_overflow", 600));
  assert.equal(result.status, "capacity-exhausted");
  safe(result);
  assert.equal(gate.reserveAttempt(request("req_0", 0)).status,
    "duplicate-navigation");
  assert.equal(gate.reserveAttempt(request("req_other", 0)).status,
    "tab-already-reserved");
});

test("unavailable, throwing and asynchronous coordinators cannot grant navigation", () => {
  for (const config of [
    { loopGuardReady: false, readVerifiedNavigation: () => snapshot(request()) },
    { loopGuardReady: true, readVerifiedNavigation: () => {
      throw Error("https://secret.test");
    } },
    { loopGuardReady: true, readVerifiedNavigation: async ref => snapshot(ref) },
    { loopGuardReady: true, readVerifiedNavigation: "not a function" }
  ]) {
    const gate = createPdfInterceptionNavigationLoopGuard(config);
    assert.equal(gate.reserveAttempt(request()).status, "unverified-navigation");
  }
});

test("dispose ends the guard without allowing a retry", () => {
  const gate = createPdfInterceptionNavigationLoopGuard(coordinator());
  safe(gate.reserveAttempt(request()), false);
  assert.equal(gate.dispose().status, "disposed");
  assert.equal(gate.dispose().status, "disposed");
  safe(gate.reserveAttempt(request()));
  assert.equal(gate.reserveAttempt(request()).status, "disposed");
  assert.ok(Object.isFrozen(gate));
});

test("documentation explains native-origin loops, durable state and opt-in safety", async () => {
  const doc = await read("../src/pdf-interception-navigation-loop-guard.md");
  for (const phrase of [
    "opener-0786", "PDFOpener", "extension", "redirect",
    "service worker", "tab", "ClamAV", "scanner", "user",
    "preferences", "verified", "restarts", "fail closed"
  ]) assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
  assert.match(doc, /pdf-preload-interception-trigger\.js/);
});

test("CI discovers regression cases without activating browser interception or scanning", async () => {
  const [source, background, manifest, safari, pkg, ci] = await Promise.all([
    read("../src/pdf-interception-navigation-loop-guard.js"),
    read("../src/background.js"),
    read("../manifest.json").then(JSON.parse),
    read("../../safari/manifest.json").then(JSON.parse),
    read("../package.json").then(JSON.parse),
    read("../../../.github/workflows/ci.yml")
  ]);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const forbidden of [
    "chrome.", "browser.", "globalThis.", "addListener(",
    "permissions.request(", "fetch(", "sendNativeMessage(",
    "connectNative(", "tabs.update(", "tabs.create(",
    "location.href", "window.open(", "localStorage", "sessionStorage",
    "node:fs", "scan-and-open"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
