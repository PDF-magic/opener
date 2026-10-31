import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createTabScanClosureGuard as createGuard } from "../src/tab-scan-closure.js";

function fixture() {
  const listeners = new Set();
  const calls = { added: 0, removed: 0 };
  const tabs = { onRemoved: {
    addListener(listener) { calls.added++; listeners.add(listener); },
    removeListener(listener) { calls.removed++; listeners.delete(listener); }
  } };
  return {
    tabs, calls, listeners,
    close(tabId) { for (const listener of [...listeners]) listener(tabId, { windowId: 2 }); }
  };
}

const unavailable = { status: "unavailable", scanVerified: false, authorizesOpen: false };

test("listener registers only for opt-in guard and disposal removes it", () => {
  const f = fixture();
  assert.equal(f.listeners.size, 0);
  const guard = createGuard(f.tabs);
  assert.equal(f.listeners.size, 1);
  assert.equal(Object.isFrozen(guard), true);
  assert.equal(guard.tabClosed(2), false);
  guard.dispose();
  assert.equal(f.listeners.size, 0);
  assert.equal(f.calls.removed, 1);
  assert.throws(() => guard.track(2, () => {}), /unavailable/);
});

test("closing one tab cancels its jobs, not parallel scans in other tabs", () => {
  const f = fixture(), guard = createGuard(f.tabs), cancelled = [];
  let first;
  first = guard.track(11, () => {
    assert.equal(guard.isActive(first), false);
    assert.equal(guard.tabClosed(11), true);
    assert.throws(() => guard.track(11, () => {}), /unavailable/);
    cancelled.push("11a");
  });
  const second = guard.track(11, () => cancelled.push("11b"));
  const other = guard.track(12, () => cancelled.push("12"));
  f.close(11);
  assert.deepEqual(cancelled, ["11a", "11b"]);
  assert.equal(guard.isActive(second), false);
  assert.equal(guard.isActive(other), true);
  assert.equal(guard.release(first), false);
  assert.equal(guard.release(other), true);
  f.close(11);
  f.close(12);
  assert.deepEqual(cancelled, ["11a", "11b"]);
  guard.dispose();
});

test("a tab closed before a scan is tracked cannot receive a new scan", () => {
  const f = fixture(), guard = createGuard(f.tabs);
  f.close(20);
  assert.equal(guard.tabClosed(20), true);
  assert.throws(() => guard.track(20, () => {}), /unavailable/);
  const token = guard.track(21, () => {});
  assert.equal(guard.isActive(token), true);
  guard.dispose();
});

test("late clean results cannot authorize opening a tab that was closed", async () => {
  const f = fixture(), guard = createGuard(f.tabs);
  let finish, cancelled = 0;
  const pending = new Promise(resolve => { finish = resolve; });
  const token = guard.track(1, () => { cancelled++; });
  const result = guard.receive(token, pending);
  f.close(1);
  finish({ status: "clean", scanVerified: true, authorizesOpen: true,
    path: "/private/document.pdf" });
  assert.deepEqual(await result, unavailable);
  assert.equal(cancelled, 1);
  assert.equal(guard.isActive(token), false);
  assert.deepEqual(await guard.receive(token, new Promise(() => {})), unavailable);
  guard.dispose();
});

test("still-active jobs only return unverified scanner input and release once", async () => {
  const f = fixture(), guard = createGuard(f.tabs), cancelled = [];
  const token = guard.track(3, () => cancelled.push("stale"));
  const result = Object.freeze({ status: "pending-native-verification" });
  assert.equal(await guard.receive(token, Promise.resolve(result)), result);
  assert.equal(guard.release(token), true);
  assert.equal(guard.release(token), false);
  f.close(3);
  assert.deepEqual(cancelled, []);
  guard.dispose();
});

test("closure before promise settles and rejection fail closed", async () => {
  const f = fixture(), guard = createGuard(f.tabs);
  const token = guard.track(8, () => {});
  assert.deepEqual(await guard.receive(token, Promise.reject(Error("private"))), unavailable);
  f.close(8);
  assert.deepEqual(await guard.receive(token, Promise.resolve({ status: "clean" })), unavailable);
  guard.dispose();
});

test("all callbacks are revoked before reentrant cancellation and failures are contained", async () => {
  const f = fixture(), guard = createGuard(f.tabs), called = [];
  guard.track(10, () => { called.push("throw"); throw Error("/secret.pdf"); });
  guard.track(10, () => { called.push("reject"); return Promise.reject(Error("private")); });
  const token = guard.track(10, () => { called.push("last"); });
  assert.doesNotThrow(() => f.close(10));
  await Promise.resolve();
  assert.deepEqual(called, ["throw", "reject", "last"]);
  assert.equal(guard.isActive(token), false);
  guard.dispose();
});

test("disposal cancels remaining jobs exactly once without touching other tabs", () => {
  const f = fixture(), guard = createGuard(f.tabs), called = [];
  guard.track(10, () => called.push(10));
  guard.track(20, () => called.push(20));
  f.close(10);
  guard.dispose();
  guard.dispose();
  f.close(20);
  assert.deepEqual(called, [10, 20]);
  assert.equal(f.listeners.size, 0);
});

test("synchronous tab closure during registration is remembered", () => {
  const f = fixture();
  f.tabs.onRemoved.addListener = cb => { f.listeners.add(cb); cb(12); };
  const guard = createGuard(f.tabs);
  assert.throws(() => guard.track(12, () => {}), /unavailable/);
  assert.equal(guard.tabClosed(12), true);
  guard.dispose();
});

test("invalid or missing privileged event emitter fails closed", () => {
  for (const invalid of [null, {}, { onRemoved: {} },
    { onRemoved: { addListener() {} } },
    { get onRemoved() { throw Error("private"); } }]) {
    assert.throws(() => createGuard(invalid), /unavailable/);
  }
  const f = fixture();
  f.tabs.onRemoved.addListener = () => { throw Error("private"); };
  assert.throws(() => createGuard(f.tabs), /registration failed/);
});

test("malformed tab ID closes the entire scan session rather than losing cancellation", () => {
  for (const invalid of [undefined, -1, 1.3, Infinity, "12", {}, null]) {
    const f = fixture(), guard = createGuard(f.tabs), cancelled = [];
    guard.track(1, () => cancelled.push("one"));
    guard.track(2, () => cancelled.push("two"));
    f.close(invalid);
    assert.deepEqual(cancelled, ["one", "two"]);
    assert.equal(f.listeners.size, 0);
    assert.throws(() => guard.track(1, () => {}), /unavailable/);
  }
});

test("disposed tokens are never valid in another scan session", () => {
  const f = fixture(), old = createGuard(f.tabs);
  const token = old.track(3, () => {});
  old.dispose();
  const newer = createGuard(f.tabs);
  assert.equal(newer.isActive(token), false);
  newer.dispose();
});

test("no scan launch, permission mutation, navigation, or preference writes", async () => {
  const source = await readFile(new URL("../src/tab-scan-closure.js", import.meta.url), "utf8");
  for (const forbidden of ["chrome.", "browser.", "connectNative(", "sendNativeMessage(",
    "downloads.open(", "tabs.remove(", "tabs.update(", "scan_and_open", "clamscan",
    "node:fs", "node:child_process", "fetch(", "localStorage", "storage.local",
    "permissions.request("]) assert.equal(source.includes(forbidden), false, forbidden);
  const f = fixture(), prefs = Object.freeze({ selectedPdfApp: "custom", protection: "maximum" });
  const before = JSON.stringify(prefs), guard = createGuard(f.tabs);
  guard.track(1, () => {});
  f.close(1);
  assert.equal(JSON.stringify(prefs), before);
  guard.dispose();
});

test("repeated tab removal does not exhaust the bounded closed-tab ledger", () => {
  const f = fixture(), guard = createGuard(f.tabs);
  f.close(3);
  for (let i = 0; i < 5000; i++) f.close(3);
  assert.equal(guard.tabClosed(3), true);
  const token = guard.track(4, () => {});
  assert.equal(guard.isActive(token), true);
  guard.dispose();
});

test("bounded tab-removal tracking fails closed rather than growing without limit", () => {
  const f = fixture(), guard = createGuard(f.tabs), cancelled = [];
  guard.track(5000, () => cancelled.push("stopped"));
  for (let id = 0; id <= 4096; id++) f.close(id);
  assert.deepEqual(cancelled, ["stopped"]);
  assert.equal(f.listeners.size, 0);
  assert.throws(() => guard.track(5001, () => {}), /unavailable/);
});

test("a trapping privileged event object fails without revealing its exception", () => {
  const source = new Proxy({}, {
    getOwnPropertyDescriptor() { throw Error("/private/tab.pdf"); }
  });
  assert.throws(() => createGuard(source), /unavailable/);
});
