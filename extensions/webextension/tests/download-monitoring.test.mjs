import assert from "node:assert/strict";
import test from "node:test";
import {
  normalizeDownloadEvent, subscribeToDownloadEvents
} from "../src/download-monitoring.js";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}

function downloadsApi() {
  return {
    onCreated: eventSource(),
    onChanged: eventSource(),
    onErased: eventSource()
  };
}

test("the shared module registers only after explicit subscription", () => {
  const api = downloadsApi();
  const received = [];
  const stop = subscribeToDownloadEvents(api, (event) => received.push(event));
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [1, 1, 1]);
  api.onCreated.emit({ id: 0, filename: "/tmp/report.pdf", mime: "application/pdf",
    url: "https://private.example/report.pdf", referrer: "private", state: "in_progress",
    danger: "safe", cookies: "secret", bytes: new Uint8Array([1, 2]) });
  assert.deepEqual(received, [{ kind: "created", id: 0, filename: "/tmp/report.pdf",
    mime: "application/pdf", state: "in_progress", danger: "safe" }]);
  assert.equal(Object.isFrozen(received[0]), true);
  assert.equal(Object.hasOwn(received[0], "url"), false);
  stop();
  stop();
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [0, 0, 0]);
  api.onCreated.emit({ id: 1 });
  assert.equal(received.length, 1);
});

test("changes include only current allowlisted values, not old values or URLs", () => {
  const api = downloadsApi();
  const received = [];
  const stop = subscribeToDownloadEvents(api, (event) => received.push(event));
  api.onChanged.emit({ id: 19,
    filename: { previous: "/secret/old.pdf", current: "/tmp/new.pdf" },
    state: { previous: "in_progress", current: "complete" },
    mime: { current: "application/pdf" },
    error: { current: "FILE_FAILED" },
    url: { current: "https://private.example/download" } });
  api.onErased.emit(19); // Browser onErased supplies a number, not an object.
  assert.deepEqual(received, [{ kind: "changed", id: 19, filename: "/tmp/new.pdf",
    mime: "application/pdf", state: "complete", error: "FILE_FAILED" },
    { kind: "erased", id: 19 }]);
  stop();
});

test("browser onErased accepts the numeric download id", () => {
  // onErased's payload is a numeric id; normalization must not silently lose it.
  const api = downloadsApi();
  const results = [];
  const stop = subscribeToDownloadEvents(api, (event) => results.push(event));
  api.onErased.emit(23);
  assert.deepEqual(results, [{ kind: "erased", id: 23 }]);
  stop();
});

test("invalid identifiers and oversized or NUL-bearing metadata are rejected", () => {
  for (const id of [-1, 1.1, Number.MAX_SAFE_INTEGER + 1, "1", undefined, NaN]) {
    assert.equal(normalizeDownloadEvent("created", { id }), null);
  }
  assert.equal(normalizeDownloadEvent("invalid", { id: 1 }), null);
  assert.equal(normalizeDownloadEvent("created", null), null);
  const event = normalizeDownloadEvent("created", { id: 2,
    filename: "x".repeat(4097), mime: "pdf\0evil", state: 1, danger: "unknown" });
  assert.deepEqual(event, { kind: "created", id: 2, danger: "unknown" });
});

test("partial subscriptions are rolled back when a listener registration fails", () => {
  const api = downloadsApi();
  api.onChanged.addListener = () => { throw new Error("registration failed"); };
  assert.throws(() => subscribeToDownloadEvents(api, () => {}), /registration failed/);
  assert.equal(api.onCreated.size, 0);
  assert.equal(api.onErased.size, 0);
});

test("missing browser APIs and callbacks fail before any registration", () => {
  const api = downloadsApi();
  assert.throws(() => subscribeToDownloadEvents(api, null), TypeError);
  assert.throws(() => subscribeToDownloadEvents(api, () => {}, { onError: true }), TypeError);
  assert.throws(() => subscribeToDownloadEvents({}, () => {}), TypeError);
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [0, 0, 0]);
});

test("consumer errors do not disrupt browser event dispatch or leak into later events", () => {
  const api = downloadsApi();
  const caught = [];
  const stop = subscribeToDownloadEvents(api, () => { throw new Error("consumer failed"); }, {
    onError(error) { caught.push(error.message); }
  });
  api.onCreated.emit({ id: 1 });
  api.onChanged.emit({ id: 1, state: { current: "complete" } });
  assert.deepEqual(caught, ["consumer failed", "consumer failed"]);
  stop();
});

test("does not touch browser APIs, native scanners, network or files on module import", async () => {
  const code = await import("node:fs/promises").then((fs) =>
    fs.readFile(new URL("../src/download-monitoring.js", import.meta.url), "utf8"));
  for (const forbidden of ["fetch(", "XMLHttpRequest", "nativeMessaging", "sendNativeMessage",
    "scan_and_open", "clamscan", "browser.downloads", "chrome.downloads", "onDeterminingFilename"]) {
    assert.equal(code.includes(forbidden), false, forbidden + " must not appear in shared source");
  }
});
