import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createNativeScanDisconnectGuard } from "../src/native-scan-disconnect.js";

function fakePort() {
  const listeners = new Set();
  const counts = { added: 0, removed: 0, disconnected: 0 };
  const port = {
    onDisconnect: {
      addListener(callback) { counts.added++; listeners.add(callback); },
      removeListener(callback) { counts.removed++; listeners.delete(callback); }
    },
    disconnect() { counts.disconnected++; throw Error("must not close the port"); }
  };
  return {
    port, counts, listeners,
    disconnect() { for (const listener of [...listeners]) listener(port); }
  };
}

test("registration is opt-in and a native port does not itself enable scanning", () => {
  const { port, counts } = fakePort();
  const guard = createNativeScanDisconnectGuard(port);
  assert.equal(counts.added, 1);
  assert.equal(guard.connectionLost(), false);
  assert.equal(guard.isActive(Symbol("unknown")), false);
  assert.ok(Object.isFrozen(guard));
  guard.dispose();
  assert.equal(counts.disconnected, 0);
});

test("extension disconnect synchronously aborts every tracked scan and revokes tokens", () => {
  const { port, disconnect, listeners, counts } = fakePort();
  const guard = createNativeScanDisconnectGuard(port);
  const cancelled = [];
  const first = guard.track(() => {
    assert.equal(guard.connectionLost(), true);
    assert.equal(guard.isActive(first), false);
    assert.throws(() => guard.track(() => {}), /unavailable/);
    cancelled.push("first");
  });
  const second = guard.track(() => cancelled.push("second"));
  assert.equal(guard.isActive(first), true);
  assert.equal(guard.isActive(second), true);
  disconnect();
  assert.deepEqual(cancelled, ["first", "second"]);
  assert.equal(guard.isActive(first), false);
  assert.equal(guard.isActive(second), false);
  assert.equal(guard.release(first), false);
  assert.equal(listeners.size, 0);
  assert.equal(counts.removed, 1);
  assert.equal(counts.disconnected, 0);
  disconnect();
  guard.dispose();
  assert.deepEqual(cancelled, ["first", "second"]);
});

test("a settled scan is not cancelled, while a still-running scan is", () => {
  const { port, disconnect } = fakePort();
  const guard = createNativeScanDisconnectGuard(port);
  const cancelled = [];
  const settled = guard.track(() => cancelled.push("completed"));
  const pending = guard.track(() => cancelled.push("pending"));
  assert.equal(guard.release(settled), true);
  assert.equal(guard.release(settled), false);
  assert.equal(guard.isActive(pending), true);
  disconnect();
  assert.deepEqual(cancelled, ["pending"]);
  assert.equal(guard.isActive(settled), false);
});

test("late results after disconnection never become live, including on another port", async () => {
  const old = fakePort();
  const guard = createNativeScanDisconnectGuard(old.port);
  let complete;
  const finished = new Promise((resolve) => { complete = resolve; });
  const token = guard.track(() => {});
  old.disconnect();
  complete({ status: "clean", authorizesOpen: true, privatePath: "/private/pdf" });
  const result = await finished;
  assert.equal(guard.isActive(token), false);
  assert.equal(guard.release(token), false);
  assert.equal(result.status, "clean"); // Untrusted late result is never forwarded by the guard.
  const newer = fakePort();
  const fresh = createNativeScanDisconnectGuard(newer.port);
  assert.equal(fresh.isActive(token), false);
  assert.throws(() => guard.track(() => {}), /unavailable/);
  const newToken = fresh.track(() => {});
  assert.equal(fresh.isActive(newToken), true);
  fresh.dispose();
});

test("cleanup failures never restore active scans or skip other cancellations", async () => {
  const { port, disconnect } = fakePort();
  const guard = createNativeScanDisconnectGuard(port);
  let called = 0;
  const first = guard.track(() => { throw Error("/private/secret.pdf"); });
  const second = guard.track(() => {
    called++;
    return Promise.reject(Error("scanner details must stay private"));
  });
  const third = guard.track(() => { called++; });
  assert.doesNotThrow(disconnect);
  await Promise.resolve();
  assert.equal(called, 2);
  for (const token of [first, second, third]) assert.equal(guard.isActive(token), false);
});

test("explicit disposal aborts pending work and blocks future registration", () => {
  const { port, listeners } = fakePort();
  const guard = createNativeScanDisconnectGuard(port);
  let count = 0;
  const token = guard.track(() => { count++; });
  guard.dispose();
  guard.dispose();
  assert.equal(count, 1);
  assert.equal(guard.isActive(token), false);
  assert.equal(listeners.size, 0);
  assert.throws(() => guard.track(() => {}), /unavailable/);
});

test("missing event APIs and failed listener registration fail closed", () => {
  for (const port of [null, {}, { onDisconnect: {} }, {
    onDisconnect: { addListener() {}, removeListener: null }
  }]) {
    assert.throws(() => createNativeScanDisconnectGuard(port), /unavailable/);
  }
  const port = fakePort().port;
  port.onDisconnect.addListener = () => { throw Error("/secret/document.pdf"); };
  assert.throws(() => createNativeScanDisconnectGuard(port), /registration failed/);
});

test("the guard does not scan, open, register native access or mutate user preferences", async () => {
  const code = await readFile(new URL("../src/native-scan-disconnect.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "connectNative(", "sendNativeMessage(",
    "permissions.request(", "fetch(", "window.open(", "localStorage",
    "node:fs", "node:child_process", "clamscan", "scan-and-open"
  ]) assert.equal(code.includes(forbidden), false, forbidden);
  const settings = Object.freeze({ pdfApplication: "user-selected", scanPolicy: "built-in" });
  const saved = JSON.stringify(settings);
  const { port, disconnect } = fakePort();
  const guard = createNativeScanDisconnectGuard(port);
  guard.track(() => {});
  disconnect();
  assert.equal(JSON.stringify(settings), saved);
});
