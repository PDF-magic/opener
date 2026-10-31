import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  POST_SCAN_BROWSING_RESTORATION_MODES,
  createPostScanBrowsingRestoration
} from "../src/post-scan-browsing-restoration.js";

const request = (patch = {}) => ({
  scanRequestId: "scan_1", holdId: "hold_7", tabId: 19, ...patch
});
const hold = (patch = {}) => ({
  ...request(), documentId: "document_5", browserId: "firefox",
  mode: "original-page", holdActive: true, permissionGranted: true,
  browserHoldVerified: true, nativeSessionAuthenticated: true,
  scanComplete: true, scanVerified: true, scanStatus: "clean",
  pdfIdentityVerified: true, originalPageAvailable: true,
  verifiedBytesRetained: false, nativeReleaseApproved: false, ...patch
});
const ack = (patch = {}) => ({ accepted: true, ...request(), ...patch });
function fixture({ snapshot = () => hold(), submit = async () => ack(),
  ready = true } = {}) {
  const calls = [];
  const coordinator = {
    browserRestorationReady: ready,
    readVerifiedBrowsingHold(reference) {
      calls.push(["read", reference]);
      return snapshot(reference);
    },
    requestRestoreHeldBrowsing(reference) {
      calls.push(["submit", reference]);
      return submit(reference);
    }
  };
  return {
    calls, coordinator, restorer: createPostScanBrowsingRestoration(coordinator)
  };
}
function assertSafe(result) {
  assert.ok(Object.isFrozen(result));
  assert.equal(result.browsingRestored, false);
  assert.equal(result.automaticInterceptionEnabled, false);
  assert.equal(result.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(result),
    /https?:|secret|path|document_5|scan_1|hold_7/iu);
}

test("clean native result can request revealing the intact original page without re-navigation", async () => {
  const f = fixture();
  assert.deepEqual(POST_SCAN_BROWSING_RESTORATION_MODES,
    ["original-page", "buffered-pdf-response"]);
  assert.ok(Object.isFrozen(f.restorer));
  assert.deepEqual(f.calls, []);
  const outcome = await f.restorer.restore(request());
  assert.equal(outcome.status, "restore-request-submitted");
  assert.equal(outcome.restorationRequested, true);
  assertSafe(outcome);
  assert.deepEqual(f.calls.map(x => x[0]), ["read", "submit", "read"]);
  assert.deepEqual(f.calls[1][1], {
    ...request(), documentId: "document_5",
    mode: "original-page", browserId: "firefox"
  });
  assert.ok(Object.isFrozen(f.calls[1][1]));
  assert.equal("url" in f.calls[1][1], false);
});

test("Firefox-only buffered restoration requires identical verified bytes and native release approval", async () => {
  const secure = {
    mode: "buffered-pdf-response", originalPageAvailable: false,
    verifiedBytesRetained: true, nativeReleaseApproved: true
  };
  for (const browserId of ["firefox", "chrome", "edge", "safari", "brave"]) {
    const f = fixture({ snapshot: () => hold({ ...secure, browserId }) });
    const result = await f.restorer.restore(request());
    assert.equal(result.status,
      browserId === "firefox" ? "restore-request-submitted" : "unavailable");
    assertSafe(result);
    assert.equal(f.calls.some(x => x[0] === "submit"), browserId === "firefox");
  }
  for (const override of [
    { nativeReleaseApproved: false }, { verifiedBytesRetained: false },
    { originalPageAvailable: true }
  ]) {
    const f = fixture({ snapshot: () => hold({ ...secure, ...override }) });
    assert.equal((await f.restorer.restore(request())).status, "unavailable");
    assert.deepEqual(f.calls.map(x => x[0]), ["read"]);
  }
});

test("untrusted status labels, non-clean scans, missing permissions and altered identity never resume", async () => {
  for (const patch of [
    { scanComplete: false }, { scanVerified: false },
    { scanStatus: "malwareDetected" }, { scanStatus: "blocked" },
    { scanStatus: "scanFailed" }, { scanStatus: "cancelled" },
    { scanStatus: "incompleteScan" }, { scanStatus: "clean", holdActive: false },
    { permissionGranted: false }, { browserHoldVerified: false },
    { nativeSessionAuthenticated: false }, { pdfIdentityVerified: false },
    { originalPageAvailable: false }, { nativeReleaseApproved: true },
    { verifiedBytesRetained: true }, { browserId: "unsupported-browser" },
    { documentId: "scan_1" }, { documentId: "../private" },
    { holdId: "hold_other" }, { tabId: 77 }, { scanRequestId: "scan_other" },
    { mode: "reopen-original-url" }, { url: "https://private.test/pdf?secret=yes" },
    { authorizesOpen: true }
  ]) {
    const f = fixture({ snapshot: () => hold(patch) });
    assert.equal((await f.restorer.restore(request())).status, "unavailable",
      JSON.stringify(patch));
    assert.deepEqual(f.calls.map(x => x[0]), ["read"]);
  }
});

test("invalid caller input never invokes coordinator or browser API", async () => {
  for (const bad of [
    null, undefined, {}, [], request({ tabId: -1 }),
    request({ tabId: 1.2 }), request({ tabId: "19" }),
    request({ holdId: "scan_1" }), request({ holdId: "/tmp/a" }),
    request({ scanRequestId: "" }), request({ url: "https://private.test" }),
    request({ clean: true }), Object.create({ ...request() })
  ]) {
    const f = fixture();
    const result = await f.restorer.restore(bad);
    assert.equal(result.status, "not-requested");
    assertSafe(result);
    assert.deepEqual(f.calls, []);
  }
  const getter = request();
  Object.defineProperty(getter, "holdId", {
    enumerable: true, get() { throw new Error("secret"); }
  });
  const f = fixture();
  assert.equal((await f.restorer.restore(getter)).status, "not-requested");
  assert.deepEqual(f.calls, []);
});

test("unavailable coordinator never resumes browsing", async () => {
  const absent = createPostScanBrowsingRestoration();
  assert.equal((await absent.restore(request())).status, "unavailable");
  const disabled = fixture({ ready: false });
  assert.equal((await disabled.restorer.restore(request())).status, "unavailable");
  assert.deepEqual(disabled.calls, []);
  for (const key of ["readVerifiedBrowsingHold", "requestRestoreHeldBrowsing"]) {
    const f = fixture();
    f.coordinator[key] = undefined;
    assert.equal((await f.restorer.restore(request())).status, "unavailable");
    assert.deepEqual(f.calls, []);
  }
});

test("concurrent duplicate and replay cannot submit another browsing release", async () => {
  let release;
  const f = fixture({ submit: () => new Promise(resolve => { release = resolve; }) });
  const first = f.restorer.restore(request());
  const repeat = await f.restorer.restore(request());
  assert.equal(repeat.status, "duplicate");
  assertSafe(repeat);
  release(ack());
  assert.equal((await first).status, "restore-request-submitted");
  assert.equal((await f.restorer.restore(request())).status, "duplicate");
  assert.equal(f.calls.filter(x => x[0] === "submit").length, 1);
});

test("stale document, permission revocation or changed hold during pending work fails closed", async () => {
  for (const patch of [
    { documentId: "new_page" }, { holdActive: false },
    { permissionGranted: false }, { scanStatus: "blocked" },
    { nativeReleaseApproved: true }, { browserHoldVerified: false },
    { scanVerified: false }
  ]) {
    let count = 0;
    const f = fixture({ snapshot: () => hold(++count === 1 ? {} : patch) });
    const outcome = await f.restorer.restore(request());
    assert.equal(outcome.status, "unavailable");
    assert.deepEqual(f.calls.map(x => x[0]), ["read", "submit", "read"]);
    assertSafe(outcome);
  }
});

test("acknowledgments must match the hold exactly and do not prove browsing was restored", async () => {
  for (const response of [
    ack({ accepted: false }), ack({ scanRequestId: "other" }),
    ack({ holdId: "other" }), ack({ tabId: 20 }),
    { ...ack(), pdfOpen: true }, { accepted: true },
    { ...ack(), accepted: "true" }, null, true, undefined
  ]) {
    const f = fixture({ submit: async () => response });
    const result = await f.restorer.restore(request());
    assert.equal(result.status, "unavailable");
    assertSafe(result);
    assert.equal(f.calls.filter(x => x[0] === "submit").length, 1);
  }
});

test("dispose and changed coordinator invalidate in-flight restoration", async () => {
  for (const mutate of [
    f => f.restorer.dispose(),
    f => { f.coordinator.browserRestorationReady = false; },
    f => { f.coordinator.readVerifiedBrowsingHold = () => hold(); },
    f => { f.coordinator.requestRestoreHeldBrowsing = async () => ack(); }
  ]) {
    let release;
    const f = fixture({ submit: () => new Promise(resolve => { release = resolve; }) });
    const pending = f.restorer.restore(request());
    mutate(f);
    release(ack());
    assert.equal((await pending).status, "unavailable");
    assertSafe(await f.restorer.restore(request()));
  }
});

test("module, extension, and CI remain inert and run restoration regressions", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [background, manifest, pkg, source] = await Promise.all([
    read("../src/background.js"), read("../manifest.json"),
    read("../package.json"), read("../src/post-scan-browsing-restoration.js")
  ]);
  assert.doesNotMatch(background, /onBeforeRequest|requestRestoreHeldBrowsing/);
  const parsed = JSON.parse(manifest);
  assert.deepEqual(parsed.permissions, []);
  assert.deepEqual(parsed.host_permissions, []);
  assert.equal(JSON.parse(pkg).scripts.test,
    "node --test --test-concurrency=1 tests/*.test.mjs");
  assert.doesNotMatch(source, /tabs\.update\s*\(|fetch\s*\(|window\.location\s*=/);
});
