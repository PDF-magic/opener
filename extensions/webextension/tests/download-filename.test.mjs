import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { retrieveCompletedDownloadFilename as getFilename } from "../src/download-filename.js";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";

function event() {
  const listeners = new Set();
  return {
    addListener(fn) { listeners.add(fn); },
    removeListener(fn) { listeners.delete(fn); },
    emit(value) { for (const fn of [...listeners]) fn(value); },
    get size() { return listeners.size; }
  };
}
function fixture() {
  const searched = [], checked = [];
  const onRemoved = event();
  const downloads = {
    onCreated: event(), onChanged: event(), onErased: event(),
    search(query) {
      searched.push(query);
      return Promise.resolve([{ id: query.id, state: "complete",
        filename: "/tmp/completed.pdf", url: "https://private.invalid",
        referrer: "private", cookies: "secret", scanVerified: true }]);
    }
  };
  const permissions = {
    onRemoved,
    contains(query) { checked.push(query); return Promise.resolve(true); },
    request() { throw Error("must not request permissions"); }
  };
  return { downloads, permissions, onRemoved, searched, checked };
}
const completion = (id = 7) => Object.freeze({ kind: "completed", id });
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("queries only the completed ID under a verified downloads grant", async () => {
  const f = fixture();
  const result = await getFilename(f.downloads, f.permissions, completion());
  assert.deepEqual(f.checked, [{ permissions: ["downloads"] }]);
  assert.deepEqual(f.searched, [{ id: 7 }]);
  assert.deepEqual(result, { id: 7, filename: "/tmp/completed.pdf" });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(f.onRemoved.size, 0);
  assert.equal(JSON.stringify(result).includes("private"), false);
  assert.equal("scanVerified" in result, false);
});

test("incomplete, forged and malformed completion notices do not reach browser APIs", async () => {
  const f = fixture();
  let getterCalls = 0;
  const accessor = { kind: "completed" };
  Object.defineProperty(accessor, "id", { get() { getterCalls++; throw Error("secret"); } });
  for (const value of [
    null, {}, "completed", { kind: "created", id: 7 },
    { kind: "changed", id: 7 }, { kind: "completed", id: "7" },
    { kind: "completed", id: -1 }, { kind: "completed", id: 1.4 },
    { kind: "completed", id: Number.MAX_SAFE_INTEGER + 1 },
    { kind: "completed", id: 7, url: "https://private.invalid" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 }), accessor
  ]) assert.equal(await getFilename(f.downloads, f.permissions, value), null);
  assert.equal(getterCalls, 0);
  assert.deepEqual(f.searched, []);
  assert.deepEqual(f.checked, []);
});

test("no grant, unsupported permission checks and rejected browser calls fail closed", async () => {
  for (const check of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => Promise.reject(Error("/private/browser-profile")), () => false,
    () => undefined, () => { throw Error("private"); }
  ]) {
    const f = fixture();
    f.permissions.contains = check;
    assert.equal(await getFilename(f.downloads, f.permissions, completion()), null);
    assert.deepEqual(f.searched, []);
    assert.equal(f.onRemoved.size, 0);
  }
  const f = fixture();
  delete f.permissions.onRemoved;
  assert.equal(await getFilename(f.downloads, f.permissions, completion()), null);
  assert.deepEqual(f.searched, []);
});

test("revocation during pending permission verification prevents filename search", async () => {
  const f = fixture();
  let grant;
  f.permissions.contains = () => new Promise((resolve) => { grant = resolve; });
  const pending = getFilename(f.downloads, f.permissions, completion());
  assert.equal(f.onRemoved.size, 1);
  f.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  grant(true);
  assert.equal(await pending, null);
  assert.deepEqual(f.searched, []);
  assert.equal(f.onRemoved.size, 0);
});

test("revocation during a pending search drops the private filename", async () => {
  const f = fixture();
  let reply;
  f.downloads.search = (query) => {
    f.searched.push(query);
    return new Promise((resolve) => { reply = resolve; });
  };
  const pending = getFilename(f.downloads, f.permissions, completion());
  await tick();
  assert.deepEqual(f.searched, [{ id: 7 }]);
  f.onRemoved.emit({ permissions: ["tabs"], origins: [] });
  assert.equal(f.onRemoved.size, 1);
  f.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  reply([{ id: 7, state: "complete", filename: "/private/too-late.pdf" }]);
  assert.equal(await pending, null);
  assert.equal(f.onRemoved.size, 0);
});

test("mismatched, interrupted, absent, ambiguous or unsafe filenames are rejected", async () => {
  for (const items of [
    [], {}, null, [null],
    [{ id: 8, state: "complete", filename: "wrong.pdf" }],
    [{ id: 7, state: "interrupted", filename: "incomplete.pdf" }],
    [{ id: 7, state: "in_progress", filename: "pending.pdf" }],
    [{ id: 7, state: "complete" }],
    [{ id: 7, state: "complete", filename: "" }],
    [{ id: 7, state: "complete", filename: "bad\u0000file.pdf" }],
    [{ id: 7, state: "complete", filename: "bad\nfile.pdf" }],
    [{ id: 7, state: "complete", filename: "x".repeat(4097) }],
    [{ id: 7, state: "complete", filename: 123 }],
    [{ id: 7, state: "complete", filename: "a.pdf" },
      { id: 7, state: "complete", filename: "b.pdf" }]
  ]) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve(items);
    assert.equal(await getFilename(f.downloads, f.permissions, completion()), null);
    assert.equal(f.onRemoved.size, 0);
  }
});

test("malicious getters and array indices are never evaluated", async () => {
  const f = fixture();
  let reads = 0;
  const item = { id: 7, state: "complete" };
  Object.defineProperty(item, "filename", { get() { reads++; throw Error("secret"); } });
  f.downloads.search = () => Promise.resolve([item]);
  assert.equal(await getFilename(f.downloads, f.permissions, completion()), null);
  const arr = [null];
  Object.defineProperty(arr, "0", { get() { reads++; throw Error("secret"); } });
  f.downloads.search = () => Promise.resolve(arr);
  assert.equal(await getFilename(f.downloads, f.permissions, completion()), null);
  assert.equal(reads, 0);
  f.downloads.search = () => Promise.reject(Error("private browser error"));
  assert.equal(await getFilename(f.downloads, f.permissions, completion()), null);
});

test("actual completion events can be correlated with an exact-ID filename lookup", async () => {
  const f = fixture(), notices = [], tasks = [];
  const stop = subscribeToDownloadCompletions(f.downloads, (notice) => {
    tasks.push(getFilename(f.downloads, f.permissions, notice).then((value) => notices.push(value)));
  });
  f.downloads.onChanged.emit({ id: 23, state: { previous: "in_progress", current: "complete" } });
  await Promise.all(tasks);
  assert.deepEqual(f.searched, [{ id: 23 }]);
  assert.deepEqual(notices, [{ id: 23, filename: "/tmp/completed.pdf" }]);
  stop();
});

test("module never enables background monitoring, native access or PDF opening", async () => {
  const source = await readFile(new URL("../src/download-filename.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["globalThis.browser", "globalThis.chrome", "nativeMessaging",
    "sendNativeMessage(", "connectNative(", "scan_and_open", "clamscan",
    "fetch(", "downloads.open(", "cookies.get", "storage.local"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
