import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { subscribeToDownloadCancellations } from "../src/download-cancellation.js";

function source() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}
function downloads() {
  return { onCreated: source(), onChanged: source(), onErased: source() };
}

test("only a current USER_CANCELED error identifies cancellation", () => {
  const api = downloads();
  const notices = [];
  const stop = subscribeToDownloadCancellations(api, (event) => notices.push(event));
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [1, 1, 1]);
  api.onCreated.emit({ id: 4, error: "USER_CANCELED", state: "interrupted" });
  api.onChanged.emit({ id: 4, state: { current: "interrupted" } });
  api.onChanged.emit({ id: 4, error: { previous: "USER_CANCELED" } });
  for (const reason of ["NETWORK_FAILED", "SERVER_FAILED", "FILE_FAILED",
                        "USER_SHUTDOWN", "CRASH"]) {
    api.onChanged.emit({ id: 4, error: { current: reason },
      state: { current: "interrupted" } });
  }
  api.onErased.emit(4);
  assert.deepEqual(notices, []);
  api.onChanged.emit({ id: 4, error: { previous: "", current: "USER_CANCELED" } });
  assert.deepEqual(notices, [{ kind: "cancelled", id: 4 }]);
  assert.equal(Object.isFrozen(notices[0]), true);
  stop();
});

test("independent cancellation and interrupted state deltas emit only one notice", () => {
  const api = downloads();
  const ids = [];
  const stop = subscribeToDownloadCancellations(api, (event) => ids.push(event.id));
  api.onChanged.emit({ id: 0, error: { current: "USER_CANCELED" } });
  api.onChanged.emit({ id: 0, state: { previous: "in_progress", current: "interrupted" } });
  api.onChanged.emit({ id: 0, error: { current: "USER_CANCELED" } });
  api.onChanged.emit({ id: 1, state: { current: "interrupted" },
    error: { current: "USER_CANCELED" } });
  api.onChanged.emit({ id: 1, error: { current: "USER_CANCELED" } });
  assert.deepEqual(ids, [0, 1]);
  stop();
});

test("created downloads and erased history clear old IDs for reuse", () => {
  const api = downloads();
  const ids = [];
  const stop = subscribeToDownloadCancellations(api, ({ id }) => ids.push(id));
  api.onChanged.emit({ id: 7, error: { current: "USER_CANCELED" } });
  api.onCreated.emit({ id: 7 });
  api.onChanged.emit({ id: 7, error: { current: "USER_CANCELED" } });
  api.onErased.emit(7);
  api.onChanged.emit({ id: 7, error: { current: "USER_CANCELED" } });
  assert.deepEqual(ids, [7, 7, 7]);
  stop();
});

test("malformed browser errors and invalid download IDs fail closed", () => {
  const api = downloads();
  const notices = [];
  const stop = subscribeToDownloadCancellations(api, (notice) => notices.push(notice));
  for (const id of [-1, 1.1, "3", null, undefined, Number.MAX_SAFE_INTEGER + 1]) {
    api.onChanged.emit({ id, error: { current: "USER_CANCELED" } });
  }
  for (const error of [null, undefined, {}, { previous: "USER_CANCELED" },
    { current: "user_canceled" }, { current: "USER_CANCELLED" },
    { current: "USER_CANCELED\0" }, { current: true },
    { current: ["USER_CANCELED"] }, { current: "NETWORK_FAILED" }]) {
    api.onChanged.emit({ id: 3, error });
  }
  assert.deepEqual(notices, []);
  stop();
});

test("reports only frozen ID and never private download or scanner metadata", () => {
  const api = downloads();
  const notices = [];
  const stop = subscribeToDownloadCancellations(api, (notice) => notices.push(notice));
  api.onChanged.emit({ id: 9, error: { current: "USER_CANCELED" },
    url: { current: "https://secret.example/private.pdf" },
    filename: { current: "/private/secret.pdf" },
    referrer: "private", cookies: "secret", headers: ["private"],
    bytes: new Uint8Array([1, 2]), scanVerified: true,
    authorizesOpen: true, danger: { current: "safe" } });
  assert.deepEqual(notices, [{ kind: "cancelled", id: 9 }]);
  assert.equal(JSON.stringify(notices).includes("private"), false);
  assert.equal(Object.hasOwn(notices[0], "authorizesOpen"), false);
  stop();
});

test("bounded deduplication and idempotent teardown stop all events", () => {
  const api = downloads();
  const ids = [];
  const stop = subscribeToDownloadCancellations(api, ({ id }) => ids.push(id));
  for (let id = 0; id < 280; id++) {
    api.onChanged.emit({ id, error: { current: "USER_CANCELED" } });
  }
  assert.equal(ids.length, 280);
  api.onChanged.emit({ id: 279, error: { current: "USER_CANCELED" } });
  assert.equal(ids.length, 280);
  stop();
  stop();
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [0, 0, 0]);
  api.onChanged.emit({ id: 300, error: { current: "USER_CANCELED" } });
  assert.equal(ids.length, 280);
});

test("invalid subscription fails and partial event registration rolls back", () => {
  const api = downloads();
  assert.throws(() => subscribeToDownloadCancellations(api, null), TypeError);
  assert.throws(() => subscribeToDownloadCancellations({}, () => {}), TypeError);
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [0, 0, 0]);
  api.onChanged.addListener = () => { throw Error("registration unavailable"); };
  assert.throws(() => subscribeToDownloadCancellations(api, () => {}),
    /registration unavailable/);
  assert.equal(api.onCreated.size, 0);
  assert.equal(api.onErased.size, 0);
});

test("consumer exceptions report only generic errors and do not prevent later events", () => {
  const api = downloads();
  const failures = [];
  const stop = subscribeToDownloadCancellations(api, () => {
    throw Error("/private/file.pdf");
  }, { onError(error) { failures.push(error.message); } });
  api.onChanged.emit({ id: 1, error: { current: "USER_CANCELED" } });
  api.onChanged.emit({ id: 2, error: { current: "USER_CANCELED" } });
  assert.deepEqual(failures, [
    "Download cancellation callback failed", "Download cancellation callback failed"
  ]);
  stop();
});

test("import never activates background, native scans or PDF opening", async () => {
  const code = await readFile(new URL("../src/download-cancellation.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "globalThis.chrome", "browser.downloads", "chrome.downloads",
    "fetch(", "nativeMessaging", "sendNativeMessage(", "scan_and_open",
    "clamscan", "downloads.cancel(", "downloads.open("
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
