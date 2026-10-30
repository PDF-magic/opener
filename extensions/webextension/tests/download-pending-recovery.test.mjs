import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createPendingDownloadScanRecovery as createRecovery
} from "../src/download-pending-recovery.js";

function events() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}

function fixture() {
  const downloads = {
    onCreated: events(), onChanged: events(), onErased: events()
  };
  const nativePort = { onDisconnect: events() };
  const recovery = createRecovery(downloads, nativePort);
  const cancelled = [];
  const track = (id = 7, scanRequestId = "scan_7") =>
    recovery.track(submission(id), scanRequestId, () => {
      cancelled.push([id, scanRequestId]);
    });
  return { downloads, nativePort, recovery, cancelled, track };
}

function submission(id = 7) {
  return Object.freeze({
    status: "submitted", id, scanSubmitted: true,
    scanVerified: false, authorizesOpen: false
  });
}
const unavailable = {
  status: "unavailable", scanVerified: false, authorizesOpen: false
};
const pending = {
  status: "pending", scanVerified: false, authorizesOpen: false
};

test("tracks an accepted download request by opaque token without opening or scanning", () => {
  const f = fixture();
  const token = f.track();
  assert.equal(typeof token, "symbol");
  assert.deepEqual(f.recovery.state(token), pending);
  assert.equal(Object.isFrozen(f.recovery.state(token)), true);
  assert.deepEqual(f.cancelled, []);
  assert.equal(f.nativePort.onDisconnect.size, 1);
  assert.deepEqual([
    f.downloads.onCreated.size, f.downloads.onChanged.size,
    f.downloads.onErased.size
  ], [1, 1, 1]);
  f.recovery.dispose();
});

test("an interrupted browser download cancels exactly its accepted native request", () => {
  const f = fixture();
  const a = f.track(7, "scan_7");
  const b = f.track(8, "scan_8");
  f.downloads.onChanged.emit({ id: 7, state: { current: "interrupted" } });
  assert.deepEqual(f.cancelled, [[7, "scan_7"]]);
  assert.deepEqual(f.recovery.state(a), unavailable);
  assert.deepEqual(f.recovery.state(b), pending);
  assert.equal(f.recovery.release(a), false);
  assert.equal(f.recovery.abandon(a), false);
  assert.equal(f.track(7, "scan_again"), null, "interrupted ID stays blocked");
  f.recovery.dispose();
  assert.deepEqual(f.cancelled, [[7, "scan_7"], [8, "scan_8"]]);
});

test("erased or replaced downloads abandon pending work and require new lifecycle", () => {
  const f = fixture();
  const old = f.track();
  f.downloads.onErased.emit(7);
  assert.deepEqual(f.cancelled, [[7, "scan_7"]]);
  assert.deepEqual(f.recovery.state(old), unavailable);
  assert.equal(f.track(7, "scan_erased"), null);
  f.downloads.onCreated.emit({ id: 7, filename: "/private/new.pdf" });
  const fresh = f.track(7, "scan_new");
  assert.equal(typeof fresh, "symbol");
  f.downloads.onCreated.emit({ id: 7, filename: "/private/reused.pdf" });
  assert.deepEqual(f.cancelled, [[7, "scan_7"], [7, "scan_new"]]);
  assert.deepEqual(f.recovery.state(fresh), unavailable);
  assert.equal(typeof f.track(7, "scan_latest"), "symbol");
  f.recovery.dispose();
});

test("renames, errors, unsafe classifications, and regressions from complete abandon", () => {
  const changes = [
    { filename: { current: "/private/moved.pdf" } },
    { error: { current: "FILE_FAILED" } },
    { danger: { current: "dangerous" } },
    { danger: { current: "safe" } },
    { state: { current: "in_progress" } },
    { state: { current: "interrupted" } },
    { state: { current: "cancelled" } }
  ];
  for (const change of changes) {
    const f = fixture();
    const token = f.track();
    f.downloads.onChanged.emit({ id: 7, ...change });
    assert.deepEqual(f.recovery.state(token), unavailable, JSON.stringify(change));
    assert.deepEqual(f.cancelled, [[7, "scan_7"]], JSON.stringify(change));
    assert.equal(f.track(7, "scan_again"), null);
    f.recovery.dispose();
  }
});

test("unrelated download events and harmless repeated complete snapshots do not cancel", () => {
  const f = fixture();
  const a = f.track();
  f.downloads.onChanged.emit({ id: 8, state: { current: "interrupted" } });
  f.downloads.onErased.emit(9);
  f.downloads.onChanged.emit({ id: 7, state: { current: "complete" } });
  assert.deepEqual(f.recovery.state(a), pending);
  assert.deepEqual(f.cancelled, []);
  f.recovery.dispose();
});

test("native Port disconnection cancels all pending requests exactly once and disallows replay", () => {
  const f = fixture();
  const a = f.track(7, "scan_7");
  const b = f.track(8, "scan_8");
  f.nativePort.onDisconnect.emit();
  assert.deepEqual(f.cancelled, [[7, "scan_7"], [8, "scan_8"]]);
  assert.deepEqual(f.recovery.state(a), unavailable);
  assert.deepEqual(f.recovery.state(b), unavailable);
  assert.equal(f.track(9, "scan_9"), null);
  f.nativePort.onDisconnect.emit();
  f.recovery.dispose();
  assert.deepEqual(f.cancelled, [[7, "scan_7"], [8, "scan_8"]]);
});

test("callback throws or rejects without blocking abandonment of other scans", async () => {
  const f = fixture();
  const a = f.recovery.track(submission(7), "scan_7", () => {
    throw Error("/private/path.pdf");
  });
  const b = f.recovery.track(submission(8), "scan_8", () =>
    Promise.reject(Error("secret URL")));
  const c = f.track(9, "scan_9");
  f.nativePort.onDisconnect.emit();
  await Promise.resolve();
  assert.deepEqual(f.recovery.state(a), unavailable);
  assert.deepEqual(f.recovery.state(b), unavailable);
  assert.deepEqual(f.recovery.state(c), unavailable);
  assert.deepEqual(f.cancelled, [[9, "scan_9"]]);
  f.recovery.dispose();
});

test("duplicate browser IDs and duplicate scan IDs are not registered", () => {
  const f = fixture();
  const token = f.track(7, "scan_7");
  assert.equal(f.track(7, "scan_other"), null);
  assert.equal(f.track(8, "scan_7"), null);
  assert.equal(f.cancelled.length, 0);
  assert.deepEqual(f.recovery.state(token), pending);
  f.recovery.dispose();
});

test("release forgets a finished token but never authorizes opening or a duplicate submission", () => {
  const f = fixture();
  const token = f.track();
  assert.equal(f.recovery.release(token), true);
  assert.equal(f.recovery.release(token), false);
  assert.deepEqual(f.recovery.state(token), unavailable);
  assert.deepEqual(f.cancelled, []);
  assert.equal(f.track(7, "scan_7_again"), null);
  f.nativePort.onDisconnect.emit();
  assert.deepEqual(f.cancelled, [], "released scan is not cancelled again");
  f.recovery.dispose();
});

test("explicit abandonment revokes before reentrant cancellation callbacks run", () => {
  const f = fixture();
  let token;
  let observed;
  token = f.recovery.track(submission(), "scan_7", () => {
    observed = f.recovery.state(token);
    assert.equal(f.track(7, "scan_repeat"), null);
  });
  assert.equal(f.recovery.abandon(token), true);
  assert.deepEqual(observed, unavailable);
  assert.equal(f.recovery.abandon(token), false);
  assert.deepEqual(f.recovery.state(token), unavailable);
  f.recovery.dispose();
});

test("strictly validates accepted submission and scan correlation before registration", () => {
  const f = fixture();
  const hostile = new Proxy({}, {
    ownKeys() { throw Error("private"); }
  });
  const badSubmissions = [
    null, {}, [], hostile,
    { ...submission(), scanVerified: true },
    { ...submission(), authorizesOpen: true },
    { ...submission(), status: "submitted", scanSubmitted: false },
    { ...submission(), status: "request-submitted" },
    { ...submission(), id: "7" }, { ...submission(), id: -1 },
    { ...submission(), id: Number.MAX_SAFE_INTEGER + 1 },
    { ...submission(), localPath: "/secret/download.pdf" }
  ];
  for (const bad of badSubmissions) {
    assert.equal(f.recovery.track(bad, "scan_7", () => {}), null);
  }
  for (const id of ["", "../relative", "scan/id", "scan id",
    "scan:7", "x".repeat(81), null, {}, 7]) {
    assert.equal(f.recovery.track(submission(), id, () => {}), null);
  }
  assert.equal(f.recovery.track(submission(), "scan_7", null), null);
  assert.deepEqual(f.cancelled, []);
  assert.equal(typeof f.track(), "symbol", "invalid work does not reserve IDs");
  f.recovery.dispose();
});

test("capacity exhaustion fails closed without evicting older native scan ownership", () => {
  const f = fixture();
  const tokens = [];
  for (let i = 0; i < 256; i += 1) {
    const token = f.track(i, "scan_" + i);
    assert.equal(typeof token, "symbol");
    tokens.push(token);
  }
  assert.equal(f.track(300, "scan_300"), null);
  assert.deepEqual(f.recovery.state(tokens[0]), pending);
  f.recovery.dispose();
  assert.equal(f.cancelled.length, 256);
  assert.deepEqual(f.recovery.state(tokens[0]), unavailable);
});

test("dispose safely cancels pending work, removes listeners and cannot be restarted", () => {
  const f = fixture();
  const token = f.track();
  f.recovery.dispose();
  f.recovery.dispose();
  assert.deepEqual(f.cancelled, [[7, "scan_7"]]);
  assert.deepEqual(f.recovery.state(token), unavailable);
  assert.equal(f.track(9, "scan_new"), null);
  assert.deepEqual([
    f.downloads.onCreated.size, f.downloads.onChanged.size,
    f.downloads.onErased.size, f.nativePort.onDisconnect.size
  ], [0, 0, 0, 0]);
});

test("observer initialization requires valid event sources and rolls back disconnect tracking", () => {
  const port = { onDisconnect: events() };
  assert.throws(() => createRecovery({}, port), TypeError);
  assert.equal(port.onDisconnect.size, 0);
  assert.throws(() => createRecovery(null, { onDisconnect: null }), TypeError);
});

test("abandonment module is dormant and never requests permission, replays, scans or opens", async () => {
  const source = await readFile(
    new URL("../src/download-pending-recovery.js", import.meta.url), "utf8");
  const worker = await readFile(
    new URL("../src/background.js", import.meta.url), "utf8");
  const popup = await readFile(
    new URL("../src/popup.html", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.match(popup, /Not active/);
  assert.match(popup, /disabled aria-disabled="true"/);
  for (const forbidden of [
    "sendNativeMessage(", "connectNative(", "clamscan",
    "scan_and_open", "downloads.open(", "downloads.resume(", "downloads.cancel(",
    "permissions.request(", "chrome.", "browser.", "storage.local",
    "localStorage", "fetch(", "node:fs", "window.open(", "innerHTML"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
