import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createCompletedDownloadScanRequestGate as gate } from "../src/download-scan-once.js";
import { preflightCompletedDownloadForScan } from "../src/download-scan-preflight.js";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(callback) { listeners.add(callback); },
    removeListener(callback) { listeners.delete(callback); },
    emit(payload) { for (const callback of [...listeners]) callback(payload); },
    get size() { return listeners.size; }
  };
}

function downloads() {
  return { onCreated: eventSource(), onChanged: eventSource(), onErased: eventSource() };
}

const verified = (id = 7) => Object.freeze({
  id, transferComplete: true, scanVerified: false,
  authorizesScan: false, authorizesOpen: false
});
const accepted = () => Promise.resolve({ accepted: true });

test("one completed download invokes the callback at most once", async () => {
  const api = downloads();
  const requestGate = gate(api);
  let requests = 0;
  const submit = () => { requests++; return accepted(); };
  assert.deepEqual(await requestGate.submitOnce(verified(), submit), {
    status: "request-submitted", scanVerified: false, authorizesOpen: false
  });
  assert.equal((await requestGate.submitOnce(verified(), submit)).status, "duplicate");
  assert.equal((await requestGate.submitOnce(verified(), submit)).status, "duplicate");
  assert.equal(requests, 1);
  requestGate.dispose();
});

test("concurrent and reentrant requests reserve the ID before any callback", async () => {
  const api = downloads();
  const requestGate = gate(api);
  let complete;
  let calls = 0;
  const first = requestGate.submitOnce(verified(4), () => {
    calls++;
    return new Promise((resolve) => { complete = resolve; });
  });
  const second = requestGate.submitOnce(verified(4), () => {
    calls++; return accepted();
  });
  assert.equal((await second).status, "duplicate");
  assert.equal(calls, 1);
  complete({ accepted: true });
  assert.equal((await first).status, "request-submitted");

  let reentrant;
  reentrant = requestGate.submitOnce(verified(5), () => {
    calls++;
    const duplicate = requestGate.submitOnce(verified(5), () => {
      calls++; return accepted();
    });
    return duplicate.then((outcome) => {
      assert.equal(outcome.status, "duplicate");
      return { accepted: true };
    });
  });
  assert.equal((await reentrant).status, "request-submitted");
  assert.equal(calls, 2);
  requestGate.dispose();
});

test("failure, rejected acknowledgment and completion never release a reservation", async () => {
  const api = downloads(), requestGate = gate(api);
  let count = 0;
  const fail = () => { count++; throw Error("sensitive local path"); };
  assert.equal((await requestGate.submitOnce(verified(1), fail)).status, "submission-rejected");
  assert.equal((await requestGate.submitOnce(verified(1), fail)).status, "duplicate");
  const reject = () => { count++; return Promise.resolve({ accepted: false }); };
  assert.equal((await requestGate.submitOnce(verified(2), reject)).status, "submission-rejected");
  assert.equal((await requestGate.submitOnce(verified(2), reject)).status, "duplicate");
  const badAck = { accepted: false };
  Object.defineProperty(badAck, "accepted", {
    get() { throw Error("private browser error"); }
  });
  assert.equal((await requestGate.submitOnce(verified(3), () => badAck)).status, "submission-rejected");
  assert.equal((await requestGate.submitOnce(verified(3), accepted)).status, "duplicate");
  assert.equal(count, 2);
  requestGate.dispose();
});

test("independent download IDs are allowed and trusted lifecycle events permit ID reuse", async () => {
  const api = downloads(), requestGate = gate(api);
  let count = 0;
  const callback = () => { count++; return accepted(); };
  for (const id of [2, 3, 4]) {
    assert.equal((await requestGate.submitOnce(verified(id), callback)).status, "request-submitted");
  }
  api.onChanged.emit({ id: 2, state: { current: "complete" } });
  assert.equal((await requestGate.submitOnce(verified(2), callback)).status, "duplicate");
  api.onCreated.emit({ id: 2, state: "in_progress" });
  assert.equal((await requestGate.submitOnce(verified(2), callback)).status, "request-submitted");
  api.onErased.emit(3);
  assert.equal((await requestGate.submitOnce(verified(3), callback)).status, "request-submitted");
  assert.equal(count, 5);
  requestGate.dispose();
});

test("no old reservation is evicted after more than 256 downloads", async () => {
  const api = downloads(), requestGate = gate(api);
  let count = 0;
  const callback = () => { count++; return accepted(); };
  for (let id = 0; id < 256; id++) {
    assert.equal((await requestGate.submitOnce(verified(id), callback)).status, "request-submitted");
  }
  assert.equal((await requestGate.submitOnce(verified(0), callback)).status, "duplicate");
  assert.equal((await requestGate.submitOnce(verified(999), callback)).status, "capacity-exhausted");
  assert.equal(count, 256);
  api.onErased.emit(5);
  assert.equal((await requestGate.submitOnce(verified(999), callback)).status, "request-submitted");
  assert.equal(count, 257);
  requestGate.dispose();
});

test("reject forged preflights and fail closed without invoking the scanner callback", async () => {
  const api = downloads(), requestGate = gate(api);
  let count = 0, read = 0;
  const callback = () => { count++; return accepted(); };
  const hostile = { id: 7, transferComplete: true, scanVerified: false,
    authorizesScan: false };
  Object.defineProperty(hostile, "authorizesOpen", {
    get() { read++; throw Error("private path"); }
  });
  const symbol = { ...verified() };
  symbol[Symbol("secret")] = true;
  const wrong = [
    null, 7, "completed", [], {}, { kind: "completed", id: 7 },
    { ...verified(), transferComplete: false },
    { ...verified(), authorizesScan: true },
    { ...verified(), scanVerified: true },
    { ...verified(), authorizesOpen: true },
    { ...verified(), id: -1 }, { ...verified(), id: "7" },
    { ...verified(), id: 2.5 }, { ...verified(), id: Number.MAX_SAFE_INTEGER + 1 },
    { ...verified(), filename: "/private/report.pdf" },
    Object.assign(Object.create({ id: 7 }), verified()), hostile, symbol
  ];
  for (const input of wrong) {
    assert.equal((await requestGate.submitOnce(input, callback)).status, "unavailable");
  }
  assert.equal(read, 0);
  assert.equal(count, 0);
  requestGate.dispose();
});

test("missing callback cannot consume reservation or launch a request", async () => {
  const api = downloads(), requestGate = gate(api);
  assert.equal((await requestGate.submitOnce(verified(), null)).status, "unavailable");
  assert.equal((await requestGate.submitOnce(verified(), accepted)).status, "request-submitted");
  requestGate.dispose();
});

test("shutdown detaches all event listeners and prevents late submissions", async () => {
  const api = downloads(), requestGate = gate(api);
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [1, 1, 1]);
  let resolve;
  const inFlight = requestGate.submitOnce(verified(0), () =>
    new Promise(r => { resolve = r; }));
  requestGate.dispose();
  requestGate.dispose();
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [0, 0, 0]);
  resolve({ accepted: true });
  assert.equal((await inFlight).status, "submission-rejected");
  let invoked = false;
  assert.equal((await requestGate.submitOnce(verified(1), () => {
    invoked = true; return accepted();
  })).status, "unavailable");
  assert.equal(invoked, false);
});

test("registration failure rolls back and cannot implicitly start a scan", () => {
  const api = downloads();
  api.onChanged.addListener = () => { throw Error("registration refused"); };
  assert.throws(() => gate(api), /registration refused/);
  assert.deepEqual([api.onCreated.size, api.onErased.size], [0, 0]);
  assert.throws(() => gate({}), TypeError);
});

test("integrates with a permission-checked real download preflight", async () => {
  const api = downloads();
  api.search = ({ id }) => Promise.resolve([{
    id, state: "complete", exists: true, paused: false, canResume: false,
    bytesReceived: 50, totalBytes: 50, filename: "/private/report.pdf"
  }]);
  const permissions = {
    onRemoved: eventSource(),
    contains: async () => true
  };
  const notice = Object.freeze({ kind: "completed", id: 11 });
  const preflight = await preflightCompletedDownloadForScan(api, permissions, notice);
  assert.deepEqual(preflight, verified(11));
  const requestGate = gate(api);
  let calls = 0;
  const send = () => { calls++; return accepted(); };
  assert.equal((await requestGate.submitOnce(preflight, send)).status, "request-submitted");
  assert.equal((await requestGate.submitOnce(preflight, send)).status, "duplicate");
  assert.equal(calls, 1);
  requestGate.dispose();
});

test("never activates browser background, scans, native messaging or automatic opening", async () => {
  const source = await readFile(new URL("../src/download-scan-once.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["globalThis.chrome", "globalThis.browser", "connectNative(",
    "sendNativeMessage(", "scan_and_open", "clamscan", "downloads.open(",
    "fetch(", "localStorage", "storage.local", "node:fs"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
