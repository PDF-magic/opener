import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";

function source() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(message) { for (const listener of [...listeners]) listener(message); },
    get size() { return listeners.size; }
  };
}

function downloads() {
  return { onCreated: source(), onChanged: source(), onErased: source() };
}

test("recognizes only a current completed state from a download update", () => {
  const api = downloads();
  const notices = [];
  const stop = subscribeToDownloadCompletions(api, (notice) => notices.push(notice));
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [1, 1, 1]);
  api.onCreated.emit({ id: 4, state: "complete" }); // not a completion transition
  api.onChanged.emit({ id: 4, filename: { current: "/home/user/a.pdf" } });
  api.onChanged.emit({ id: 4, state: { previous: "complete" } });
  api.onChanged.emit({ id: 4, state: { current: "in_progress" } });
  api.onChanged.emit({ id: 4, state: { current: "interrupted" } });
  assert.deepEqual(notices, []);
  api.onChanged.emit({ id: 4, state: { previous: "in_progress", current: "complete" } });
  assert.deepEqual(notices, [{ kind: "completed", id: 4 }]);
  assert.equal(Object.isFrozen(notices[0]), true);
  stop();
});

test("ignores repeated completion updates and tracks independent download IDs", () => {
  const api = downloads();
  const ids = [];
  const stop = subscribeToDownloadCompletions(api, (notice) => ids.push(notice.id));
  for (const id of [0, 1, 0, 1, 2, 2]) {
    api.onChanged.emit({ id, state: { current: "complete" } });
  }
  api.onChanged.emit({ id: 2, state: { current: "complete" },
    danger: { current: "dangerous" } });
  assert.deepEqual(ids, [0, 1, 2]);
  stop();
});

test("created and erased events release old IDs for safe reuse", () => {
  const api = downloads();
  const ids = [];
  const stop = subscribeToDownloadCompletions(api, ({ id }) => ids.push(id));
  api.onChanged.emit({ id: 7, state: { current: "complete" } });
  api.onCreated.emit({ id: 7, state: "in_progress" });
  api.onChanged.emit({ id: 7, state: { current: "complete" } });
  api.onErased.emit(7);
  api.onChanged.emit({ id: 7, state: { current: "complete" } });
  assert.deepEqual(ids, [7, 7, 7]);
  stop();
});

test("completion notifications omit URLs, cookies, filenames and dangerous scan claims", () => {
  const api = downloads();
  const notices = [];
  const stop = subscribeToDownloadCompletions(api, (notice) => notices.push(notice));
  api.onChanged.emit({
    id: 9, state: { current: "complete" },
    url: { current: "https://private.example/report.pdf" },
    filename: { current: "/private/report.pdf" },
    cookies: { current: "secret" },
    danger: { current: "dangerous" },
    scanVerified: true, authorizesOpen: true
  });
  assert.deepEqual(notices, [{ kind: "completed", id: 9 }]);
  assert.equal(JSON.stringify(notices).includes("private"), false);
  assert.equal("scanVerified" in notices[0], false);
  assert.equal("authorizesOpen" in notices[0], false);
  stop();
});

test("rejects malformed current states and invalid download identifiers", () => {
  const api = downloads();
  const ids = [];
  const stop = subscribeToDownloadCompletions(api, ({ id }) => ids.push(id));
  for (const id of [-1, 2.5, Number.MAX_SAFE_INTEGER + 1, "3", null]) {
    api.onChanged.emit({ id, state: { current: "complete" } });
  }
  for (const state of [{ previous: "complete" }, { current: "Complete" },
    { current: true }, { current: "com\0plete" }, { current: "interrupted" },
    { current: "in_progress" }, {}, null]) {
    api.onChanged.emit({ id: 3, state });
  }
  assert.deepEqual(ids, []);
  stop();
});

test("suppression memory stays bounded and disconnect tears down every listener", () => {
  const api = downloads();
  const ids = [];
  const stop = subscribeToDownloadCompletions(api, ({ id }) => ids.push(id));
  for (let id = 0; id < 280; id++) {
    api.onChanged.emit({ id, state: { current: "complete" } });
  }
  assert.equal(ids.length, 280);
  api.onChanged.emit({ id: 279, state: { current: "complete" } });
  assert.equal(ids.length, 280, "recent completion must stay suppressed");
  stop();
  stop();
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [0, 0, 0]);
  api.onChanged.emit({ id: 300, state: { current: "complete" } });
  assert.equal(ids.length, 280);
});

test("explicit opt-in requires complete downloads API and callback; failure rolls back", () => {
  const api = downloads();
  assert.throws(() => subscribeToDownloadCompletions(api, null), TypeError);
  assert.throws(() => subscribeToDownloadCompletions({}, () => {}), TypeError);
  assert.deepEqual([api.onCreated.size, api.onChanged.size, api.onErased.size], [0, 0, 0]);
  api.onChanged.addListener = () => { throw new Error("registration unavailable"); };
  assert.throws(() => subscribeToDownloadCompletions(api, () => {}), /registration unavailable/);
  assert.equal(api.onCreated.size, 0);
  assert.equal(api.onErased.size, 0);
});

test("callback exceptions are isolated through existing monitoring error handling", () => {
  const api = downloads();
  const problems = [];
  const stop = subscribeToDownloadCompletions(api, () => { throw Error("test failure"); }, {
    onError(error) { problems.push(error.message); }
  });
  api.onChanged.emit({ id: 1, state: { current: "complete" } });
  api.onChanged.emit({ id: 2, state: { current: "complete" } });
  assert.deepEqual(problems, ["test failure", "test failure"]);
  stop();
});

test("module never activates background access, native messaging, scanner or PDF opening", async () => {
  const code = await readFile(new URL("../src/download-completion.js", import.meta.url), "utf8");
  for (const forbidden of ["globalThis.chrome", "browser.downloads", "chrome.downloads",
    "fetch(", "nativeMessaging", "sendNativeMessage(", "scan_and_open", "clamscan"])
    assert.equal(code.includes(forbidden), false, forbidden);
});
