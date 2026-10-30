import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createBrowserScanClosureGuard as createGuard } from "../src/browser-scan-closure.js";

function events() {
  const listeners = new Set();
  const counts = { added: 0, removed: 0 };
  return {
    source: {
      addListener(callback) { counts.added++; listeners.add(callback); },
      removeListener(callback) { counts.removed++; listeners.delete(callback); }
    },
    counts,
    get size() { return listeners.size; },
    emit() { for (const cb of [...listeners]) cb(); }
  };
}
function fixture(withSuspend = true) {
  const disconnect = events(), suspension = events();
  const port = {
    onDisconnect: disconnect.source,
    disconnect() { throw Error("Must not close browser port"); }
  };
  const lifecycle = withSuspend ? { onSuspend: suspension.source } : null;
  return { port, lifecycle, disconnect, suspension };
}

test("initialization is opt-in and never starts a scan or native connection", () => {
  const f = fixture();
  assert.equal(f.disconnect.size, 0);
  assert.equal(f.suspension.size, 0);
  const guard = createGuard(f.port, f.lifecycle);
  assert.equal(f.disconnect.size, 1);
  assert.equal(f.suspension.size, 1);
  assert.equal(guard.connectionLost(), false);
  assert.equal(Object.isFrozen(guard), true);
  guard.dispose();
  assert.equal(f.disconnect.size, 0);
  assert.equal(f.suspension.size, 0);
});

test("graceful browser closure synchronously cancels every active scan", () => {
  const f = fixture(), cancelled = [];
  const guard = createGuard(f.port, f.lifecycle);
  const a = guard.track(() => {
    assert.equal(guard.connectionLost(), true);
    assert.equal(guard.isActive(a), false);
    cancelled.push("a");
  });
  const b = guard.track(() => cancelled.push("b"));
  f.suspension.emit();
  assert.deepEqual(cancelled, ["a", "b"]);
  assert.equal(guard.isActive(a), false);
  assert.equal(guard.isActive(b), false);
  assert.equal(guard.release(a), false);
  assert.throws(() => guard.track(() => {}), /unavailable/);
  assert.deepEqual([f.disconnect.size, f.suspension.size], [0, 0]);
  f.disconnect.emit();
  f.suspension.emit();
  guard.dispose();
  assert.deepEqual(cancelled, ["a", "b"]);
});

test("Port disconnect aborts scans when no suspend event fires", () => {
  const f = fixture(), cancelled = [];
  const guard = createGuard(f.port, f.lifecycle);
  const token = guard.track(() => cancelled.push("lost"));
  f.disconnect.emit();
  assert.deepEqual(cancelled, ["lost"]);
  assert.equal(guard.isActive(token), false);
  assert.equal(guard.connectionLost(), true);
  assert.throws(() => guard.track(() => {}), /unavailable/);
  guard.dispose();
  assert.equal(f.suspension.size, 0);
});

test("browsers lacking onSuspend still use Port disconnect", () => {
  const f = fixture(false);
  const guard = createGuard(f.port);
  let count = 0;
  const token = guard.track(() => { count++; });
  f.disconnect.emit();
  assert.equal(count, 1);
  assert.equal(guard.isActive(token), false);
  assert.equal(guard.release(token), false);
  guard.dispose();
});

test("finished jobs are not cancelled, but pending ones are", () => {
  const f = fixture(), cancelled = [];
  const guard = createGuard(f.port, f.lifecycle);
  const done = guard.track(() => cancelled.push("done"));
  const active = guard.track(() => cancelled.push("pending"));
  assert.equal(guard.release(done), true);
  assert.equal(guard.release(done), false);
  assert.equal(guard.isActive(active), true);
  f.suspension.emit();
  assert.deepEqual(cancelled, ["pending"]);
});

test("late scanner verdicts cannot regain tokens after browser shutdown", async () => {
  const old = fixture();
  const guard = createGuard(old.port, old.lifecycle);
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const token = guard.track(() => {});
  old.suspension.emit();
  finish({ status: "clean", authorizesOpen: true, path: "/private/report.pdf" });
  const reply = await pending;
  assert.equal(reply.status, "clean");
  assert.equal(guard.isActive(token), false);
  assert.equal(guard.release(token), false);
  const next = fixture();
  const fresh = createGuard(next.port, next.lifecycle);
  assert.equal(fresh.isActive(token), false);
  assert.throws(() => guard.track(() => {}), /unavailable/);
  fresh.dispose();
});

test("throwing and rejected cleanup cannot skip other scans", async () => {
  const f = fixture(), guard = createGuard(f.port, f.lifecycle);
  let called = 0;
  const a = guard.track(() => { throw Error("private path"); });
  const b = guard.track(() => Promise.reject(Error("scanner diagnostic")));
  const c = guard.track(() => { called++; });
  f.suspension.emit();
  await Promise.resolve();
  assert.equal(called, 1);
  for (const token of [a, b, c]) assert.equal(guard.isActive(token), false);
});

test("invalid lifecycle sources fail closed without leaking Port listeners", () => {
  const f = fixture();
  for (const lifecycle of [{}, { onSuspend: {} }, {
    onSuspend: { addListener() {}, removeListener: null }
  }]) {
    assert.throws(() => createGuard(f.port, lifecycle), /unavailable/);
    assert.equal(f.disconnect.size, 0);
  }
  const bad = fixture();
  bad.suspension.source.addListener = () => { throw Error("secret"); };
  assert.throws(() => createGuard(bad.port, bad.lifecycle), /registration failed/);
  assert.equal(bad.disconnect.size, 0);
  const lost = fixture();
  assert.throws(() => createGuard(null, lost.lifecycle), /unavailable/);
  assert.equal(lost.suspension.size, 0);
});

test("synchronous suspension during registration is fail-closed", () => {
  const f = fixture();
  const add = f.suspension.source.addListener;
  f.suspension.source.addListener = cb => { add(cb); cb(); };
  const guard = createGuard(f.port, f.lifecycle);
  assert.equal(guard.connectionLost(), true);
  assert.throws(() => guard.track(() => {}), /unavailable/);
  assert.deepEqual([f.disconnect.size, f.suspension.size], [0, 0]);
});

test("explicit disposal cancels once and preserves user preferences", () => {
  const prefs = Object.freeze({ pdfApplication: "custom", protectionLevel: "built-in" });
  const original = JSON.stringify(prefs);
  const f = fixture(), guard = createGuard(f.port, f.lifecycle);
  let calls = 0;
  const token = guard.track(() => { calls++; });
  guard.dispose();
  guard.dispose();
  assert.equal(calls, 1);
  assert.equal(guard.isActive(token), false);
  assert.deepEqual([f.disconnect.size, f.suspension.size], [0, 0]);
  assert.equal(JSON.stringify(prefs), original);
});

test("no browser globals, native scan actions or automatic opening", async () => {
  const code = await readFile(new URL("../src/browser-scan-closure.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "chrome.", "browser.", "connectNative(", "sendNativeMessage(",
    "downloads.open(", "scan_and_open", "clamscan",
    "node:fs", "node:child_process", "fetch(", "localStorage",
    "storage.local", "permissions.request("
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
