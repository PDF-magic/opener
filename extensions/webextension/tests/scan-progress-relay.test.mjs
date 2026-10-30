import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { parseMessage, MAX_MESSAGE_BYTES } from "../src/messaging.js";
import { relayTrustedScanProgress as relay } from "../src/scan-progress-relay.js";

function fixture() {
  const observed = [], received = [], errors = [];
  let listener = null, disposed = 0, registrations = 0;
  const coordinator = {
    nativeScannerReady: true,
    subscribeScanProgress(id, callback) {
      registrations++;
      observed.push(id);
      listener = callback;
      return () => { disposed++; listener = null; };
    }
  };
  const receiver = (event) => { received.push(event); };
  return {
    coordinator, observed, received, errors, receiver,
    relay: (id = "scan_123") => relay(coordinator, id, receiver, {
      onError: (error) => errors.push(error)
    }),
    emit: (event) => listener?.(event),
    get registrations() { return registrations; },
    get disposed() { return disposed; },
    get hasListener() { return !!listener; }
  };
}
const progress = (stage, percent, scanRequestId = "scan_123") =>
  percent === undefined ? { scanRequestId, stage } :
    { scanRequestId, stage, percent };

test("emits real native progress in bounded, ID-correlated extension event envelopes", () => {
  const f = fixture();
  const stop = f.relay();
  f.emit(progress("queued"));
  f.emit(progress("starting"));
  f.emit(progress("scanning", 47));
  f.emit(progress("verifying", 98));
  assert.deepEqual(f.observed, ["scan_123"]);
  assert.equal(f.received.length, 4);
  for (const message of f.received) {
    assert.deepEqual(Object.keys(message).sort(),
      ["kind", "payload", "requestId", "topic", "version"]);
    assert.equal(message.kind, "event");
    assert.equal(message.topic, "scan.progress");
    assert.equal(message.requestId, "scan_123");
    assert.equal(Object.isFrozen(message), true);
    assert.equal(Object.isFrozen(message.payload), true);
    assert.deepEqual(parseMessage(message), message);
    assert.ok(new TextEncoder().encode(JSON.stringify(message)).length <= MAX_MESSAGE_BYTES);
  }
  assert.deepEqual(f.received.map(x => x.payload.stage),
    ["queued", "starting", "scanning", "verifying"]);
  assert.equal("percent" in f.received[0].payload, false);
  assert.equal(f.received[2].payload.percent, 47);
  stop();
  stop();
  assert.equal(f.disposed, 1);
  assert.equal(f.hasListener, false);
});

test("no trusted native coordinator or missing readiness never starts a subscription", () => {
  for (const coordinator of [null, {}, { nativeScannerReady: false },
    { nativeScannerReady: true },
    { nativeScannerReady: "true", subscribeScanProgress() { throw Error("called"); } },
    Object.create({ nativeScannerReady: true, subscribeScanProgress() { throw Error("called"); } })]) {
    const received = [];
    const stop = relay(coordinator, "scan_123", event => received.push(event));
    assert.equal(typeof stop, "function");
    stop();
    assert.deepEqual(received, []);
  }
});

test("invalid request IDs fail before subscribing or invoking native methods", () => {
  const f = fixture();
  for (const id of ["", "a/b", "a b", "a.b", "x".repeat(81), null, 1, {}, "é"]) {
    const stop = f.relay(id);
    stop();
  }
  assert.equal(f.registrations, 0);
});

test("other jobs, extra untrusted fields and claimed verdicts are never reported", () => {
  const f = fixture();
  f.relay();
  for (const event of [
    progress("scanning", 20, "other_job"),
    { ...progress("scanning", 20), localPath: "/private/secret.pdf" },
    { ...progress("scanning", 20), scanVerified: true },
    { ...progress("scanning", 20), authorizesOpen: true },
    { ...progress("scanning", 20), status: "clean" },
    { ...progress("scanning", 20), message: "private native stderr" },
    { ...progress("scanning", 20), bytes: "PDF contents" },
    { scanRequestId: "scan_123", stage: "complete" },
    { scanRequestId: "scan_123", stage: "clean" },
    { scanRequestId: "scan_123", stage: "error" }
  ]) f.emit(event);
  assert.deepEqual(f.received, []);
});

test("rejects false percentages, unsupported values and browser-shaped objects", () => {
  const f = fixture();
  f.relay();
  for (const percent of [-1, 100, 101, 1.5, NaN, Infinity, "20", true, null]) {
    f.emit(progress("scanning", percent));
  }
  for (const event of [
    null, [], 7, "scanning", {},
    { scanRequestId: "scan_123" },
    Object.assign(Object.create({ scanRequestId: "scan_123" }), { stage: "scanning" }),
    { scanRequestId: "scan_123", stage: "scanning", percent: undefined }
  ]) f.emit(event);
  assert.deepEqual(f.received, []);
});

test("does not evaluate native getters or proxy traps and never leaks errors", () => {
  const f = fixture();
  f.relay();
  let getterCalls = 0;
  const accessor = { scanRequestId: "scan_123" };
  Object.defineProperty(accessor, "stage", { enumerable: true,
    get() { getterCalls++; throw Error("/private/pdf"); } });
  f.emit(accessor);
  f.emit(new Proxy({}, { ownKeys() { throw Error("/private/pdf"); } }));
  assert.equal(getterCalls, 0);
  assert.deepEqual(f.received, []);
  assert.equal(f.errors.length, 1);
  assert.equal(f.errors[0].message.includes("private"), false);
});

test("stale phase and percentage regressions cannot roll progress backward", () => {
  const f = fixture();
  f.relay();
  f.emit(progress("scanning", 30));
  f.emit(progress("starting", 50));
  f.emit(progress("scanning", 29));
  f.emit(progress("scanning", 35));
  f.emit(progress("verifying", 36));
  f.emit(progress("scanning", 40));
  assert.deepEqual(f.received.map(x => [x.payload.stage, x.payload.percent]),
    [["scanning", 30], ["scanning", 35], ["verifying", 36]]);
});

test("native readiness revocation stops reporting and disposes the observer", () => {
  const f = fixture();
  f.relay();
  const callback = f.emit;
  f.coordinator.nativeScannerReady = false;
  callback(progress("scanning", 20));
  assert.deepEqual(f.received, []);
  assert.equal(f.disposed, 1);
});

test("subscription failures and invalid disposers remain unavailable and sanitized", () => {
  const f = fixture();
  f.coordinator.subscribeScanProgress = () => { throw Error("/private/caller"); };
  f.relay()();
  assert.equal(f.errors.length, 1);
  assert.equal(f.errors[0].message.includes("private"), false);
  f.coordinator.subscribeScanProgress = () => Promise.resolve(() => {});
  f.relay()();
  assert.deepEqual(f.received, []);
});

test("synchronous revocation during subscription removes the registered listener", () => {
  const f = fixture();
  let removed = 0;
  f.coordinator.subscribeScanProgress = (_id, callback) => {
    f.coordinator.nativeScannerReady = false;
    callback(progress("scanning", 20));
    return () => { removed++; };
  };
  f.relay()();
  assert.equal(removed, 1);
  assert.deepEqual(f.received, []);
});

test("receiver errors do not disclose filenames or prevent future progress updates", () => {
  const f = fixture();
  let attempts = 0;
  const stop = relay(f.coordinator, "scan_123", () => {
    attempts++;
    throw Error("/Users/private/report.pdf");
  }, { onError: error => f.errors.push(error) });
  f.emit(progress("starting"));
  f.emit(progress("scanning", 15));
  assert.equal(attempts, 2);
  assert.equal(f.errors.length, 2);
  assert.equal(f.errors[0].message.includes("private"), false);
  stop();
});

test("source is inert: no browser listener, native port, filesystem or PDF opening", async () => {
  const source = await readFile(new URL("../src/scan-progress-relay.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "sendNativeMessage(", "connectNative(", "downloads.open(",
    "globalThis", "node:fs", "clamscan", "scan_and_open", "fetch(",
    "storage.local", "permissions.request(", "addListener("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  assert.throws(() => relay(null, "scan_123", null), TypeError);
});
