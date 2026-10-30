import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { subscribeToDownloadInterruptions } from "../src/download-interruption.js";

function source() {
  const listeners = new Set();
  return {
    addListener(fn) { listeners.add(fn); },
    removeListener(fn) { listeners.delete(fn); },
    emit(x) { for (const fn of [...listeners]) fn(x); },
    get size() { return listeners.size; }
  };
}
function api() { return { onCreated: source(), onChanged: source(), onErased: source() }; }
function change(d, id, current) { d.onChanged.emit({ id, state: { current } }); }

test("only current interrupted onChanged signals an immutable transfer notice", () => {
  const d = api(), notices = [];
  const stop = subscribeToDownloadInterruptions(d, n => notices.push(n));
  assert.deepEqual([d.onCreated.size, d.onChanged.size, d.onErased.size], [1, 1, 1]);
  d.onCreated.emit({ id: 4, state: "interrupted" });
  d.onChanged.emit({ id: 4, state: { previous: "interrupted" } });
  d.onChanged.emit({ id: 4, error: { current: "FILE_FAILED" } });
  change(d, 4, "complete"); change(d, 4, "in_progress");
  assert.deepEqual(notices, []);
  change(d, 4, "interrupted");
  assert.deepEqual(notices, [{ kind: "interrupted", id: 4 }]);
  assert.equal(Object.isFrozen(notices[0]), true);
  stop();
});

test("duplicates are suppressed, but a resumed or reused ID may interrupt again", () => {
  const d = api(), ids = [], stop = subscribeToDownloadInterruptions(d, n => ids.push(n.id));
  change(d, 0, "interrupted"); change(d, 0, "interrupted");
  change(d, 1, "interrupted"); change(d, 0, "complete");
  d.onChanged.emit({ id: 0, filename: { current: "private.pdf" } });
  change(d, 0, "interrupted");
  assert.deepEqual(ids, [0, 1]);
  change(d, 0, "in_progress"); change(d, 0, "interrupted");
  d.onCreated.emit({ id: 1 }); change(d, 1, "interrupted");
  d.onErased.emit(0); change(d, 0, "interrupted");
  assert.deepEqual(ids, [0, 1, 0, 1, 0]);
  stop();
});

test("notifications exclude paths, URLs, errors, cookies and scanner claims", () => {
  const d = api(), notices = [], stop = subscribeToDownloadInterruptions(d, n => notices.push(n));
  d.onChanged.emit({ id: 9, state: { current: "interrupted" },
    error: { current: "FILE_FAILED /secret/report.pdf" },
    filename: { current: "/secret/report.pdf" }, url: { current: "https://private/" },
    cookies: { current: "secret" }, scanVerified: true, authorizesOpen: true });
  assert.deepEqual(notices, [{ kind: "interrupted", id: 9 }]);
  assert.deepEqual(Object.keys(notices[0]), ["kind", "id"]);
  stop();
});

test("invalid states and IDs never trigger an interruption", () => {
  const d = api(), ids = [], stop = subscribeToDownloadInterruptions(d, n => ids.push(n.id));
  for (const id of [-1, 1.2, Number.MAX_SAFE_INTEGER + 1, "2", null, NaN]) {
    change(d, id, "interrupted");
  }
  for (const state of [{ previous: "interrupted" }, { current: "Interrupted" },
    { current: true }, { current: "complete" }, { current: "in_progress" }, {}, null]) {
    d.onChanged.emit({ id: 5, state });
  }
  assert.deepEqual(ids, []);
  stop();
});

test("recent-ID cache remains bounded to 256 entries", () => {
  const d = api(), ids = [], stop = subscribeToDownloadInterruptions(d, n => ids.push(n.id));
  for (let id = 0; id < 280; id++) change(d, id, "interrupted");
  change(d, 279, "interrupted"); assert.equal(ids.length, 280);
  change(d, 0, "interrupted"); assert.equal(ids.length, 281);
  stop();
});

test("invalid or failing registration rolls back all listeners", () => {
  const d = api();
  assert.throws(() => subscribeToDownloadInterruptions(d, null), TypeError);
  assert.throws(() => subscribeToDownloadInterruptions({}, () => {}), TypeError);
  assert.throws(() => subscribeToDownloadInterruptions(d, () => {}, { onError: true }), TypeError);
  d.onChanged.addListener = () => { throw Error("registration failed"); };
  assert.throws(() => subscribeToDownloadInterruptions(d, () => {}), /registration failed/);
  assert.deepEqual([d.onCreated.size, d.onChanged.size, d.onErased.size], [0, 0, 0]);
});

test("consumer exceptions are isolated and teardown is idempotent", () => {
  const d = api(), problems = [];
  const stop = subscribeToDownloadInterruptions(d, () => { throw Error("bad callback"); },
    { onError(e) { problems.push(e.message); } });
  change(d, 1, "interrupted"); change(d, 2, "interrupted");
  assert.deepEqual(problems, ["bad callback", "bad callback"]);
  stop(); stop(); change(d, 3, "interrupted");
  assert.deepEqual(problems, ["bad callback", "bad callback"]);
  assert.deepEqual([d.onCreated.size, d.onChanged.size, d.onErased.size], [0, 0, 0]);
});

test("source does not auto-request permission, retry, scan or launch PDFs", async () => {
  const code = await readFile(new URL("../src/download-interruption.js", import.meta.url), "utf8");
  for (const forbidden of ["globalThis.chrome", "browser.downloads", "chrome.downloads",
    "permissions.request", "fetch(", "nativeMessaging", "sendNativeMessage(",
    "clamscan", "downloads.open(", "downloads.resume(", "downloads.cancel("]) {
    assert.equal(code.includes(forbidden), false, forbidden);
  }
});
