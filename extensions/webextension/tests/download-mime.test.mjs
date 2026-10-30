import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { retrieveCompletedDownloadMime as getMime } from "../src/download-mime.js";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(callback) { listeners.add(callback); },
    removeListener(callback) { listeners.delete(callback); },
    emit(value) { for (const callback of [...listeners]) callback(value); },
    get size() { return listeners.size; }
  };
}
function fixture() {
  const searches = [], checks = [];
  const downloads = {
    onCreated: eventSource(), onChanged: eventSource(), onErased: eventSource(),
    search(query) {
      searches.push(query);
      return Promise.resolve([{ id: query.id, state: "complete", mime: "application/pdf",
        filename: "/private/example.pdf", url: "https://private.invalid/",
        referrer: "private", danger: "safe", cookies: "secret", scanVerified: true }]);
    }
  };
  const permissions = {
    onRemoved: eventSource(),
    contains(query) { checks.push(query); return Promise.resolve(true); },
    request() { throw Error("must not request a permission"); }
  };
  return { downloads, permissions, searches, checks };
}
const completion = (id = 7) => Object.freeze({ kind: "completed", id });
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("retrieves only the declared MIME for the exact completed ID after a current grant", async () => {
  const f = fixture();
  const result = await getMime(f.downloads, f.permissions, completion());
  assert.deepEqual(f.checks, [{ permissions: ["downloads"] }]);
  assert.deepEqual(f.searches, [{ id: 7 }]);
  assert.deepEqual(result, { id: 7, mime: "application/pdf" });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(f.permissions.onRemoved.size, 0);
  assert.equal(JSON.stringify(result).includes("private"), false);
  assert.equal("filename" in result, false);
  assert.equal("scanVerified" in result, false);
});

test("preserves valid browser MIME declarations without interpreting them as file safety", async () => {
  const f = fixture();
  for (const mime of ["application/octet-stream", "text/plain; charset=UTF-8",
    "application/vnd.example+json", "IMAGE/PNG"]) {
    f.downloads.search = () => Promise.resolve([{ id: 7, state: "complete", mime,
      danger: "dangerous", filename: "/private/document" }]);
    assert.deepEqual(await getMime(f.downloads, f.permissions, completion()), { id: 7, mime });
  }
});

test("rejects invalid completion notices before any browser API call", async () => {
  const f = fixture();
  let calls = 0;
  const accessor = { kind: "completed" };
  Object.defineProperty(accessor, "id", { get() { calls++; throw Error("private"); } });
  const symbol = { kind: "completed", id: 7 };
  symbol[Symbol("private")] = true;
  for (const notice of [null, undefined, {}, "completed", [],
    { kind: "changed", id: 7 }, { kind: "interrupted", id: 7 },
    { kind: "completed", id: -1 }, { kind: "completed", id: 1.5 },
    { kind: "completed", id: "7" },
    { kind: "completed", id: Number.MAX_SAFE_INTEGER + 1 },
    { kind: "completed", id: 7, url: "https://private.invalid" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 }),
    accessor, symbol]) assert.equal(await getMime(f.downloads, f.permissions, notice), null);
  assert.equal(calls, 0);
  assert.deepEqual(f.searches, []);
  assert.deepEqual(f.checks, []);
});

test("denied or missing permission, unsupported APIs and search errors fail closed", async () => {
  for (const check of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => Promise.reject(Error("private")), () => true,
    () => undefined, () => { throw Error("secret"); }
  ]) {
    const f = fixture();
    f.permissions.contains = check;
    assert.equal(await getMime(f.downloads, f.permissions, completion()), null);
    assert.deepEqual(f.searches, []);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
  const f = fixture();
  delete f.permissions.onRemoved;
  assert.equal(await getMime(f.downloads, f.permissions, completion()), null);
  delete f.downloads.search;
  assert.equal(await getMime(f.downloads, f.permissions, completion()), null);
  assert.deepEqual(f.searches, []);
});

test("revocation during the permission check prevents subsequent searches", async () => {
  const f = fixture();
  let resolveGrant;
  f.permissions.contains = () => new Promise((resolve) => { resolveGrant = resolve; });
  const pending = getMime(f.downloads, f.permissions, completion());
  assert.equal(f.permissions.onRemoved.size, 1);
  f.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  resolveGrant(true);
  assert.equal(await pending, null);
  assert.deepEqual(f.searches, []);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("revocation while an ID lookup is pending discards the MIME response", async () => {
  const f = fixture();
  let resolveSearch;
  f.downloads.search = (query) => {
    f.searches.push(query);
    return new Promise((resolve) => { resolveSearch = resolve; });
  };
  const pending = getMime(f.downloads, f.permissions, completion());
  await tick();
  assert.deepEqual(f.searches, [{ id: 7 }]);
  f.permissions.onRemoved.emit({ permissions: ["tabs"], origins: [] });
  assert.equal(f.permissions.onRemoved.size, 1);
  f.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  resolveSearch([{ id: 7, state: "complete", mime: "application/pdf" }]);
  assert.equal(await pending, null);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("rejects missing, ambiguous, mismatched, interrupted or malformed MIME results", async () => {
  for (const response of [
    [], {}, null, [null],
    [{ id: 8, state: "complete", mime: "application/pdf" }],
    [{ id: 7, state: "in_progress", mime: "application/pdf" }],
    [{ id: 7, state: "interrupted", mime: "application/pdf" }],
    [{ id: 7, state: "complete" }],
    [{ id: 7, state: "complete", mime: "" }],
    [{ id: 7, state: "complete", mime: 3 }],
    [{ id: 7, state: "complete", mime: "application" }],
    [{ id: 7, state: "complete", mime: "https://private.invalid/" }],
    [{ id: 7, state: "complete", mime: "application/pdf\nCookie: secret" }],
    [{ id: 7, state: "complete", mime: "x".repeat(256) }],
    [{ id: 7, state: "complete", mime: "application/pdf" },
      { id: 7, state: "complete", mime: "text/plain" }]
  ]) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve(response);
    assert.equal(await getMime(f.downloads, f.permissions, completion()), null);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
});

test("hostile browser result accessors and errors cannot expose other fields", async () => {
  const f = fixture();
  let getterCalls = 0;
  const row = { id: 7, state: "complete" };
  Object.defineProperty(row, "mime", { get() { getterCalls++; throw Error("secret"); } });
  f.downloads.search = () => Promise.resolve([row]);
  assert.equal(await getMime(f.downloads, f.permissions, completion()), null);
  const array = [null];
  Object.defineProperty(array, "0", { get() { getterCalls++; throw Error("secret"); } });
  f.downloads.search = () => Promise.resolve(array);
  assert.equal(await getMime(f.downloads, f.permissions, completion()), null);
  assert.equal(getterCalls, 0);
  f.downloads.search = () => Promise.reject(Error("/private/browser-profile"));
  assert.equal(await getMime(f.downloads, f.permissions, completion()), null);
});

test("a real normalized completion can trigger an ID-only MIME lookup", async () => {
  const f = fixture(), seen = [], tasks = [];
  const stop = subscribeToDownloadCompletions(f.downloads, (notice) => {
    tasks.push(getMime(f.downloads, f.permissions, notice).then((value) => seen.push(value)));
  });
  f.downloads.onChanged.emit({ id: 23, state: { previous: "in_progress", current: "complete" } });
  await Promise.all(tasks);
  assert.deepEqual(f.searches, [{ id: 23 }]);
  assert.deepEqual(seen, [{ id: 23, mime: "application/pdf" }]);
  stop();
});

test("the imported module never activates the worker, native host or scanning", async () => {
  const module = await readFile(new URL("../src/download-mime.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["globalThis.chrome", "globalThis.browser",
    "nativeMessaging", "sendNativeMessage(", "connectNative(",
    "downloads.open(", "clamscan", "scan_and_open", "fetch("]) {
    assert.equal(module.includes(forbidden), false, forbidden);
  }
});
