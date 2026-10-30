import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS,
  MAX_EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS,
  createExplicitPdfDownloadTimeout
} from "../src/explicit-pdf-download-timeout.js";

const request = (patch = {}) => ({
  version: 1, requestId: "attempt_1", source: "pdf-link",
  tabId: 4, frameId: 0, selectionId: "selected_1",
  userInitiated: true, ...patch
});

function fixture() {
  const listeners = {
    created: new Set(), changed: new Set(), erased: new Set()
  };
  const clocks = { now: 1_000_000, nextId: 0, timers: new Map() };
  const state = {
    startedAtMs: 1_000_000, state: "in_progress",
    selected: "selected_1", ready: true, granted: true,
    verified: true, downloadId: 37, requestId: "attempt_1",
    cancelThrows: false, cancelRejects: false
  };
  const calls = [];
  const downloadsApi = {
    cancel(id) {
      calls.push(["cancel", id]);
      if (state.cancelThrows) throw Error("https://example.test?secret=123");
      if (state.cancelRejects) return Promise.reject(Error("private token"));
      return Promise.resolve();
    }
  };
  for (const kind of ["created", "changed", "erased"]) {
    downloadsApi["on" + kind[0].toUpperCase() + kind.slice(1)] = {
      addListener(fn) { listeners[kind].add(fn); },
      removeListener(fn) { listeners[kind].delete(fn); }
    };
  }
  const coordinator = {
    downloadTimeoutReady: true,
    readVerifiedActiveDownload(reference) {
      calls.push(["read", reference]);
      return {
        requestId: state.requestId, downloadId: state.downloadId,
        selectionId: state.selected, tabId: 4, frameId: 0,
        startedAtMs: state.startedAtMs, state: state.state,
        verified: state.verified, permissionGranted: state.granted
      };
    }
  };
  const clock = () => clocks.now;
  function schedule(fn, ms) {
    const id = ++clocks.nextId;
    clocks.timers.set(id, { fn, due: clocks.now + ms });
    calls.push(["schedule", ms]);
    return id;
  }
  function unschedule(id) {
    clocks.timers.delete(id);
    calls.push(["unschedule", id]);
  }
  function advance(ms) {
    clocks.now += ms;
    let iterations = 0;
    for (;;) {
      const due = [...clocks.timers.entries()]
        .find(([, item]) => item.due <= clocks.now);
      if (!due) break;
      if (++iterations > 1000) throw Error("timer loop");
      clocks.timers.delete(due[0]);
      due[1].fn();
    }
  }
  function emit(kind, id = 37, data = {}) {
    const payload = kind === "erased" ? id : (
      kind === "changed" ? { id, ...Object.fromEntries(
        Object.entries(data).map(([key, value]) => [key, { current: value }])
      ) } : { id, ...data }
    );
    for (const listener of [...listeners[kind]]) listener(payload);
  }
  function action() {
    return createExplicitPdfDownloadTimeout({
      downloadsApi, coordinator, clock, schedule, unschedule
    });
  }
  function listenerCount() {
    return Object.values(listeners).reduce((sum, set) => sum + set.size, 0);
  }
  return { downloadsApi, coordinator, calls, state, clocks,
    action, advance, emit, listenerCount, schedule, unschedule, clock };
}

function safe(result) {
  assert.ok(Object.isFrozen(result));
  assert.equal(result.scanVerified, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.equal(result.automaticallyRetry, false);
  assert.doesNotMatch(JSON.stringify(result), /secret|example|token|password/);
}

test("watchdog is inactive on import and uses a bounded default timeout", () => {
  assert.equal(EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS, 120_000);
  assert.equal(MAX_EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS, 300_000);
  const f = fixture();
  const guard = f.action();
  assert.ok(Object.isFrozen(guard));
  assert.deepEqual(f.calls, []);
  assert.equal(f.listenerCount(), 0);
  assert.equal(f.clocks.timers.size, 0);
  assert.equal(guard.isBlocked("attempt_1"), true);
});

test("enforces an exact wall-clock deadline and calls browser cancellation once", async () => {
  const f = fixture();
  const guard = f.action();
  const session = guard.watch(request(), 37);
  assert.ok(session);
  assert.ok(Object.isFrozen(session));
  assert.equal(session.state().status, "monitoring");
  assert.equal(f.listenerCount(), 3);
  f.advance(119_999);
  assert.equal(session.state().status, "monitoring");
  assert.equal(f.calls.some(([kind]) => kind === "cancel"), false);
  f.advance(1);
  const result = await session.done;
  assert.equal(result.status, "timed-out");
  assert.equal(result.cancelRequested, true);
  assert.equal(result.transferComplete, false);
  assert.equal(guard.isBlocked("attempt_1"), true);
  assert.deepEqual(f.calls.filter(([kind]) => kind === "cancel"), [["cancel", 37]]);
  assert.equal(f.listenerCount(), 0);
  assert.equal(f.clocks.timers.size, 0);
  safe(result);
  f.state.state = "complete";
  f.emit("changed", 37, { state: "complete" });
  assert.strictEqual(session.state(), result);
  assert.equal((await session.done).status, "timed-out");
});

test("already elapsed transfer deadline fails before registering a timer", async () => {
  const f = fixture();
  f.state.startedAtMs = f.clocks.now - 200_000;
  const guard = f.action();
  const session = guard.watch(request(), 37);
  assert.ok(session);
  assert.equal((await session.done).status, "timed-out");
  assert.equal(f.calls.filter(([kind]) => kind === "schedule").length, 0);
  assert.deepEqual(f.calls.filter(([kind]) => kind === "cancel"), [["cancel", 37]]);
  assert.equal(f.listenerCount(), 0);
});

test("an early timer wakeup is rearmed without shortening the deadline", async () => {
  const f = fixture();
  const session = f.action().watch(request(), 37, 30_000);
  assert.ok(session);
  const token = f.clocks.timers.values().next().value;
  token.fn(); // browser timer fired early; real wall clock did not advance
  assert.equal(session.state().status, "monitoring");
  assert.equal(f.clocks.timers.size, 1);
  assert.equal(f.calls.some(([kind]) => kind === "cancel"), false);
  f.advance(30_000);
  assert.equal((await session.done).status, "timed-out");
  assert.equal(f.calls.filter(([kind]) => kind === "cancel").length, 1);
});

test("a trusted completion strictly before deadline stops the watchdog", async () => {
  const f = fixture();
  const guard = f.action();
  const session = guard.watch(request(), 37, 2000);
  f.advance(1999);
  f.state.state = "complete";
  f.emit("changed", 37, { state: "complete" });
  const result = await session.done;
  assert.equal(result.status, "completed");
  assert.equal(result.transferComplete, true);
  assert.equal(result.cancelRequested, false);
  safe(result);
  assert.equal(guard.isBlocked("attempt_1"), false);
  assert.equal(f.clocks.timers.size, 0);
  assert.equal(f.listenerCount(), 0);
  f.advance(100_000);
  assert.equal(f.calls.some(([kind]) => kind === "cancel"), false);
});

test("a late completion event cannot turn a timed-out download into success", async () => {
  const f = fixture();
  const session = f.action().watch(request(), 37, 1000);
  f.clocks.now += 1000; // deadline elapsed before completion event delivery
  f.state.state = "complete";
  f.emit("changed", 37, { state: "complete" });
  const result = await session.done;
  assert.equal(result.status, "timed-out");
  assert.equal(result.cancelRequested, false); // already complete, no unsafe cancel
  assert.equal(f.calls.some(([kind]) => kind === "cancel"), false);
  safe(result);
});

test("only the exact ID and terminal onChanged states can finish the transfer", async () => {
  const f = fixture();
  const session = f.action().watch(request(), 37, 1000);
  f.emit("changed", 38, { state: "complete" });
  f.emit("created", 37, { state: "in_progress" });
  f.emit("changed", 37, { danger: "safe" });
  f.emit("changed", 37, { state: "in_progress" });
  f.emit("changed", 37, { state: "complete", error: "NET_FAILED" });
  // Browser-only "complete" cannot override the trusted in-progress record.
  assert.equal(session.state().status, "unavailable");
  assert.equal((await session.done).status, "unavailable");
  safe(session.state());
});

test("interrupted and erased downloads terminate without a scan or retry", async () => {
  const f = fixture();
  const session = f.action().watch(request(), 37);
  f.state.state = "interrupted";
  f.emit("changed", 37, { state: "interrupted" });
  assert.equal((await session.done).status, "interrupted");
  assert.equal(f.calls.some(([kind]) => kind === "cancel"), false);
  safe(session.state());
  const g = fixture();
  const second = g.action().watch(request(), 37);
  g.emit("erased", 37);
  assert.equal((await second.done).status, "unavailable");
  assert.equal(g.listenerCount(), 0);
  assert.equal(g.clocks.timers.size, 0);
});

test("a stale or unverified browser identity never cancels a different download", async () => {
  for (const update of [
    { downloadId: 38 }, { requestId: "different" },
    { selected: "different" }, { granted: false },
    { verified: false }, { startedAtMs: 1_000_001 }
  ]) {
    const f = fixture();
    const session = f.action().watch(request(), 37, 1000);
    Object.assign(f.state, update);
    f.advance(1000);
    assert.equal((await session.done).status, "unavailable",
      JSON.stringify(update));
    assert.deepEqual(f.calls.filter(([kind]) => kind === "cancel"), []);
    safe(session.state());
  }
});

test("rejects invalid IDs, requests, options and unverified transfer starts", () => {
  for (const [req, downloadId, timeout] of [
    [null, 37, 1000], [request({ userInitiated: false }), 37, 1000],
    [request({ source: "page" }), 37, 1000],
    [request({ url: "https://example.test/private" }), 37, 1000],
    [request(), -1, 1000], [request(), "37", 1000],
    [request(), 1.5, 1000], [request(), 37, 0],
    [request(), 37, -1], [request(), 37, 3.1],
    [request(), 37, MAX_EXPLICIT_PDF_DOWNLOAD_TIMEOUT_MS + 1]
  ]) {
    const f = fixture();
    assert.equal(f.action().watch(req, downloadId, timeout), null);
    assert.equal(f.clocks.timers.size, 0);
    assert.equal(f.listenerCount(), 0);
  }
  for (const update of [
    { state: "complete" }, { state: "interrupted" },
    { granted: false }, { verified: false },
    { startedAtMs: 1_000_001 },
    { startedAtMs: Number.MAX_SAFE_INTEGER + 1 },
    { selected: "invalid" }
  ]) {
    const f = fixture();
    Object.assign(f.state, update);
    assert.equal(f.action().watch(request(), 37), null);
    assert.equal(f.listenerCount(), 0);
  }
});

test("duplicate concurrent attempts and reused IDs cannot open a second watchdog", () => {
  const f = fixture();
  const guard = f.action();
  const session = guard.watch(request(), 37);
  assert.ok(session);
  assert.equal(guard.watch(request(), 37), null);
  f.state.state = "complete";
  f.emit("changed", 37, { state: "complete" });
  assert.equal(guard.watch(request(), 37), null);
  assert.equal(f.listenerCount(), 0);
});

test("timeout remains failed even when browser cancellation throws or rejects", async () => {
  for (const key of ["cancelThrows", "cancelRejects"]) {
    const f = fixture();
    f.state[key] = true;
    const session = f.action().watch(request(), 37, 100);
    f.advance(100);
    const result = await session.done;
    assert.equal(result.status, "timed-out");
    assert.equal(result.cancelRequested, true);
    assert.deepEqual(f.calls.filter(([kind]) => kind === "cancel"), [["cancel", 37]]);
    safe(result);
  }
});

test("disposal cancels only a currently verified active download and never resumes", async () => {
  const f = fixture();
  const guard = f.action();
  const session = guard.watch(request(), 37);
  const result = session.dispose();
  assert.equal(result.status, "disposed");
  assert.equal(result.cancelRequested, true);
  assert.equal((await session.done).status, "disposed");
  assert.equal(f.calls.filter(([kind]) => kind === "cancel").length, 1);
  f.advance(200_000);
  assert.equal(f.calls.filter(([kind]) => kind === "cancel").length, 1);
  assert.equal(guard.isBlocked("attempt_1"), true);
  guard.dispose();
  guard.dispose();
  assert.equal(guard.watch(request({ requestId: "attempt_2" }), 37), null);
  safe(result);
});

test("a no-longer-trusted selection cannot be cancelled on disposal", async () => {
  const f = fixture();
  const session = f.action().watch(request(), 37);
  f.state.downloadId = 38;
  const result = session.dispose();
  assert.equal(result.status, "disposed");
  assert.equal(result.cancelRequested, false);
  assert.equal((await session.done).status, "disposed");
  assert.equal(f.calls.some(([kind]) => kind === "cancel"), false);
});

test("manual deadline checks do not stack timers or bypass elapsed time", async () => {
  const f = fixture();
  const session = f.action().watch(request(), 37, 1000);
  session.checkDeadline();
  session.checkDeadline();
  assert.equal(f.clocks.timers.size, 1);
  f.advance(999);
  assert.equal(session.checkDeadline().status, "monitoring");
  assert.equal(f.clocks.timers.size, 1);
  f.advance(1);
  assert.equal((await session.done).status, "timed-out");
  assert.equal(f.clocks.timers.size, 0);
});

test("hostile getters, invalid coordinator and missing event sources fail closed", async () => {
  const f = fixture();
  const invalid = Object.create(null);
  Object.defineProperty(invalid, "verified", { get() {
    throw Error("https://example.test/?token=private");
  } });
  f.coordinator.readVerifiedActiveDownload = () => invalid;
  assert.equal(f.action().watch(request(), 37), null);
  const g = fixture();
  g.downloadsApi.onErased = undefined;
  const guard = g.action();
  const session = guard.watch(request(), 37);
  assert.ok(session);
  assert.equal((await session.done).status, "unavailable");
  assert.equal(g.clocks.timers.size, 0);
  assert.equal(guard.isBlocked("attempt_1"), true);
});

test("native scanner, manifest and extension background remain inactive", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifest, background, packageJson, workflow] = await Promise.all([
    read("../src/explicit-pdf-download-timeout.js"),
    read("../manifest.json"), read("../src/background.js"),
    read("../package.json"), read("../../../.github/workflows/ci.yml")
  ]);
  assert.deepEqual(JSON.parse(manifest).permissions, []);
  assert.deepEqual(JSON.parse(manifest).host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(packageJson).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(workflow, /node --test tests\/explicit-pdf-download-acquisition\.test\.mjs/);
  for (const forbidden of [
    "chrome.", "browser.", "fetch(", "XMLHttpRequest",
    "downloads.download(", "downloads.open(", "sendNativeMessage(",
    "connectNative(", "permissions.request(", "window.open(",
    "localStorage", "sessionStorage", "node:fs", "clamscan("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
