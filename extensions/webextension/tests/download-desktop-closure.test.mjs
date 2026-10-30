import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createDownloadDesktopClosureGuard
} from "../src/download-desktop-closure.js";

function lifecycle() {
  const listeners = new Set();
  const calls = { added: 0, removed: 0, cancelled: 0 };
  const event = {
    addListener(callback) { calls.added++; listeners.add(callback); },
    removeListener(callback) { calls.removed++; listeners.delete(callback); }
  };
  const coordinator = {
    nativeDesktopLifecycleReady: true, onDesktopApplicationClosed: event
  };
  return {
    calls, listeners, coordinator,
    close() { for (const listener of [...listeners]) listener(); }
  };
}
const unavailable = {
  status: "unavailable", scanVerified: false, authorizesOpen: false
};

test("trusted native desktop lifecycle registration is opt-in and non-authorizing", () => {
  const f = lifecycle();
  assert.equal(f.listeners.size, 0);
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  assert.equal(f.listeners.size, 1);
  assert.equal(f.calls.added, 1);
  assert.equal(guard.applicationClosed(), false);
  assert.equal(guard.isActive(Symbol("foreign")), false);
  assert.equal(Object.isFrozen(guard), true);
  guard.dispose();
  assert.equal(f.calls.removed, 1);
});

test("desktop closure synchronously cancels every owned in-flight download scan", () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  const cancelled = [];
  let first;
  first = guard.track(() => {
    assert.equal(guard.applicationClosed(), true);
    assert.equal(guard.isActive(first), false);
    assert.throws(() => guard.track(() => {}), /unavailable/);
    cancelled.push("first");
  });
  const second = guard.track(() => cancelled.push("second"));
  assert.equal(guard.isActive(first), true);
  assert.equal(guard.isActive(second), true);
  f.close();
  assert.deepEqual(cancelled, ["first", "second"]);
  assert.equal(guard.isActive(first), false);
  assert.equal(guard.isActive(second), false);
  assert.equal(guard.release(first), false);
  assert.equal(f.listeners.size, 0);
  assert.equal(f.calls.removed, 1);
  f.close();
  guard.dispose();
  assert.deepEqual(cancelled, ["first", "second"]);
});

test("late clean completion cannot become actionable after desktop app exits", async () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  let deliver;
  const pending = new Promise(resolve => { deliver = resolve; });
  let cancels = 0;
  const token = guard.track(() => { cancels++; });
  const received = guard.receive(token, pending);
  f.close();
  deliver({ status: "clean", scanVerified: true, authorizesOpen: true,
    path: "/private/document.pdf" });
  assert.deepEqual(await received, unavailable);
  assert.equal(cancels, 1);
  assert.equal(guard.release(token), false);
});

test("desktop closure blocks uncompleted native promises without waiting for scanner to settle", async () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  const token = guard.track(() => {});
  f.close();
  const pending = new Promise(() => {});
  assert.deepEqual(await guard.receive(token, pending), unavailable);
});

test("a live session can consume an opaque result but does not certify or open it", async () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  let cancels = 0;
  const token = guard.track(() => { cancels++; });
  const payload = Object.freeze({ status: "requires-native-verification" });
  assert.equal(await guard.receive(token, Promise.resolve(payload)), payload);
  assert.equal(guard.isActive(token), true);
  assert.equal(guard.release(token), true);
  assert.equal(guard.release(token), false);
  f.close();
  assert.equal(cancels, 0);
  assert.equal(guard.applicationClosed(), true);
});

test("a released successful scan is never cancelled by a later application exit", () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  const calls = [];
  const finished = guard.track(() => calls.push("finished"));
  const stillScanning = guard.track(() => calls.push("active"));
  assert.equal(guard.release(finished), true);
  f.close();
  assert.deepEqual(calls, ["active"]);
  assert.equal(guard.isActive(stillScanning), false);
});

test("callback errors and rejected cancellation promises never prevent other aborts", async () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  const called = [];
  guard.track(() => { called.push(1); throw Error("/private/secret.pdf"); });
  guard.track(() => {
    called.push(2);
    return Promise.reject(Error("private native scan failure"));
  });
  guard.track(() => called.push(3));
  assert.doesNotThrow(f.close);
  await Promise.resolve();
  assert.deepEqual(called, [1, 2, 3]);
  assert.equal(guard.applicationClosed(), true);
  assert.equal(f.listeners.size, 0);
});

test("queued tokens cannot be added after closure and closure is permanent", () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  f.close();
  assert.throws(() => guard.track(() => {}), /unavailable/);
  assert.throws(() => guard.track(null), /unavailable/);
  const other = lifecycle();
  const fresh = createDownloadDesktopClosureGuard(other.coordinator);
  const token = fresh.track(() => {});
  assert.equal(fresh.isActive(token), true);
  assert.equal(guard.isActive(token), false);
  fresh.dispose();
});

test("the coordinator may report closure synchronously during subscription", () => {
  const f = lifecycle();
  f.coordinator.onDesktopApplicationClosed.addListener = callback => {
    f.listeners.add(callback);
    callback();
  };
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  assert.equal(guard.applicationClosed(), true);
  assert.equal(f.listeners.size, 0);
  assert.throws(() => guard.track(() => {}), /unavailable/);
});

test("untrusted, absent or broken lifecycle registration fails closed", () => {
  for (const invalid of [
    null, {}, { nativeDesktopLifecycleReady: true },
    { nativeDesktopLifecycleReady: false,
      onDesktopApplicationClosed: lifecycle().coordinator.onDesktopApplicationClosed },
    { nativeDesktopLifecycleReady: true, onDesktopApplicationClosed: {} },
    { nativeDesktopLifecycleReady: true,
      onDesktopApplicationClosed: { addListener() {} } },
    { nativeDesktopLifecycleReady: true,
      get onDesktopApplicationClosed() { throw Error("private"); } }
  ]) {
    assert.throws(() => createDownloadDesktopClosureGuard(invalid), /unavailable/);
  }
  const f = lifecycle();
  f.coordinator.onDesktopApplicationClosed.addListener = () => {
    throw Error("private scanner owner");
  };
  assert.throws(() => createDownloadDesktopClosureGuard(f.coordinator),
    /registration failed/);
});

test("disposed session aborts immediately, revokes results and removes listeners", async () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  let deliver;
  const pending = new Promise(resolve => { deliver = resolve; });
  const calls = [];
  const token = guard.track(() => calls.push("aborted"));
  const received = guard.receive(token, pending);
  guard.dispose();
  guard.dispose();
  deliver({ status: "clean", authorizesOpen: true });
  assert.deepEqual(await received, unavailable);
  assert.deepEqual(calls, ["aborted"]);
  assert.equal(f.listeners.size, 0);
  assert.equal(guard.applicationClosed(), true);
});

test("invalid completions, rejected promises and unknown tokens never pass", async () => {
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  const token = guard.track(() => {});
  const outsider = Symbol("another-scan");
  assert.deepEqual(await guard.receive(outsider, Promise.resolve("clean")), unavailable);
  assert.deepEqual(await guard.receive(token, "clean"), unavailable);
  assert.deepEqual(await guard.receive(token, null), unavailable);
  assert.deepEqual(await guard.receive(token, Promise.reject(Error("private"))), unavailable);
  assert.throws(() => guard.track("cancel"), /unavailable/);
  guard.dispose();
});

test("module import does not contact native host, listen to browser or alter preferences", async () => {
  const code = await readFile(
    new URL("../src/download-desktop-closure.js", import.meta.url), "utf8");
  const background = await readFile(
    new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "chrome.", "browser.", "connectNative(", "sendNativeMessage(",
    "permissions.request(", "downloads.open(", "scan_and_open",
    "clamscan", "node:fs", "node:child_process", "fetch(",
    "window.open(", "localStorage", "storage.local", "console.log("
  ]) assert.equal(code.includes(forbidden), false, forbidden);
  const preferences = Object.freeze({ selectedPDFApplication: "user choice",
    scanPolicy: "built-in" });
  const snapshot = JSON.stringify(preferences);
  const f = lifecycle();
  const guard = createDownloadDesktopClosureGuard(f.coordinator);
  guard.track(() => {});
  f.close();
  assert.equal(JSON.stringify(preferences), snapshot);
});
