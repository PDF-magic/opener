import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { retrieveDownloadSourceUrl as sourceUrl } from "../src/download-source-url.js";
import { registerDownloadCreatedEvents } from "../src/download-created-events.js";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";

function event() {
  const listeners = new Set();
  return {
    addListener(callback) { listeners.add(callback); },
    removeListener(callback) { listeners.delete(callback); },
    emit(payload) { for (const callback of [...listeners]) callback(payload); },
    get size() { return listeners.size; }
  };
}

function fixture() {
  const searches = [], checks = [];
  const downloads = {
    onCreated: event(), onChanged: event(), onErased: event(),
    search(request) {
      searches.push(request);
      return Promise.resolve([{
        id: request.id, state: "complete",
        url: "https://source.example/download.pdf?token=private",
        finalUrl: "https://cdn.example/final.pdf", filename: "/private/report.pdf",
        referrer: "https://unrelated.example/", cookies: "secret",
        danger: "safe", authorizesOpen: true, scanVerified: true
      }]);
    }
  };
  const permissions = {
    onRemoved: event(),
    contains(request) { checks.push(request); return Promise.resolve(true); },
    request() { throw Error("never request a permission"); }
  };
  return { downloads, permissions, searches, checks };
}
const completed = (id = 7) => Object.freeze({ kind: "completed", id });
const created = (id = 7) => Object.freeze({
  kind: "created", id, filename: "/private/report.pdf", mime: "application/pdf",
  state: "in_progress"
});
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("queries only the matching ID after a fresh grant and returns only its original URL", async () => {
  const f = fixture();
  const result = await sourceUrl(f.downloads, f.permissions, completed());
  assert.deepEqual(f.checks, [{ permissions: ["downloads"] }]);
  assert.deepEqual(f.searches, [{ id: 7 }]);
  assert.deepEqual(result, { id: 7, url: "https://source.example/download.pdf?token=private" });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(f.permissions.onRemoved.size, 0);
  assert.equal(Object.hasOwn(result, "finalUrl"), false);
  assert.equal(Object.hasOwn(result, "referrer"), false);
  assert.equal(Object.hasOwn(result, "filename"), false);
  assert.equal(Object.hasOwn(result, "scanVerified"), false);
});

test("created events may resolve in-progress or completed browser download sources", async () => {
  const f = fixture();
  for (const state of ["in_progress", "complete"]) {
    f.downloads.search = () => Promise.resolve([{
      id: 7, state, url: "http://downloads.example/file.pdf"
    }]);
    assert.deepEqual(await sourceUrl(f.downloads, f.permissions, created()), {
      id: 7, url: "http://downloads.example/file.pdf"
    });
  }
  f.downloads.search = () => Promise.resolve([{
    id: 7, state: "in_progress", url: "https://source.example/start.pdf"
  }]);
  assert.equal(await sourceUrl(f.downloads, f.permissions, completed()), null);
});

test("missing or unavailable source URLs are not invented from finalUrl or referrer", async () => {
  const responses = [
    [], {}, null, [null],
    [{ id: 7, state: "complete", finalUrl: "https://cdn.example/final.pdf" }],
    [{ id: 7, state: "complete", url: "" }],
    [{ id: 7, state: "complete", url: null }],
    [{ id: 7, state: "complete", url: 32 }],
    [{ id: 8, state: "complete", url: "https://source.example" }],
    [{ id: 7, state: "interrupted", url: "https://source.example" }],
    [{ id: 7, state: "complete", url: "https://source.example" },
      { id: 7, state: "complete", url: "https://other.example" }]
  ];
  for (const response of responses) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve(response);
    assert.equal(await sourceUrl(f.downloads, f.permissions, completed()), null);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
});

test("rejects non-network URLs, credentials, malformed syntax and oversized URL fields", async () => {
  const unsafe = [
    "file:///private/report.pdf", "blob:https://source.example/id",
    "data:application/pdf;base64,AAAA", "javascript:alert(1)",
    "ftp://downloads.example/file.pdf", "//source.example/file.pdf",
    "https://user:password@source.example/file.pdf",
    "https://user@source.example/path",
    "https://source.example/file.pdf\nAuthorization: Bearer secret",
    "https://source.example/file.pdf\tbad",
    "https://source.example/file.pdf\0bad",
    "https://source.example/" + "a".repeat(8193),
    "https://", "not-a-url"
  ];
  for (const url of unsafe) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve([{ id: 7, state: "complete", url }]);
    assert.equal(await sourceUrl(f.downloads, f.permissions, completed()), null, url.slice(0, 60));
  }
});

test("invalid notices fail before any browser permission or download API access", async () => {
  const f = fixture();
  let getterReads = 0;
  const accessor = { kind: "completed" };
  Object.defineProperty(accessor, "id", { get() {
    getterReads++; throw Error("must not access untrusted getter");
  } });
  const extraSymbol = { kind: "completed", id: 7 };
  extraSymbol[Symbol("secret")] = true;
  const createdGetter = { kind: "created", id: 7 };
  Object.defineProperty(createdGetter, "filename", { get() {
    getterReads++; throw Error("must not access untrusted getter");
  } });
  const notices = [null, undefined, [], "completed", {}, { id: 7 },
    { kind: "changed", id: 7 }, { kind: "interrupted", id: 7 },
    { kind: "completed", id: "7" }, { kind: "completed", id: -1 },
    { kind: "completed", id: Number.MAX_SAFE_INTEGER + 1 },
    { kind: "completed", id: 7, url: "https://secret.example" },
    { kind: "created", id: 7, url: "https://secret.example" },
    { kind: "created", id: 7, filename: "bad\0path" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 }),
    accessor, createdGetter, extraSymbol];
  for (const notice of notices) {
    assert.equal(await sourceUrl(f.downloads, f.permissions, notice), null);
  }
  assert.equal(getterReads, 0);
  assert.deepEqual(f.searches, []);
  assert.deepEqual(f.checks, []);
});

test("permission denial, missing APIs and rejected searches fail closed", async () => {
  for (const check of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => Promise.reject(Error("private URL")),
    () => true, () => undefined, () => { throw Error("secret"); }
  ]) {
    const f = fixture();
    f.permissions.contains = check;
    assert.equal(await sourceUrl(f.downloads, f.permissions, completed()), null);
    assert.deepEqual(f.searches, []);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
  for (const missing of ["contains", "onRemoved", "search"]) {
    const f = fixture();
    delete (missing === "search" ? f.downloads : f.permissions)[missing];
    assert.equal(await sourceUrl(f.downloads, f.permissions, created()), null);
  }
  const f = fixture();
  f.downloads.search = () => Promise.reject(Error("https://private.example/secret"));
  assert.equal(await sourceUrl(f.downloads, f.permissions, completed()), null);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("revocation during a pending grant prevents any URL search", async () => {
  const f = fixture();
  let grant;
  f.permissions.contains = () => new Promise((resolve) => { grant = resolve; });
  const pending = sourceUrl(f.downloads, f.permissions, created());
  assert.equal(f.permissions.onRemoved.size, 1);
  f.permissions.onRemoved.emit({ permissions: ["downloads"] });
  grant(true);
  assert.equal(await pending, null);
  assert.deepEqual(f.searches, []);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("revocation while browser search is pending discards a private URL", async () => {
  const f = fixture();
  let resolveSearch;
  f.downloads.search = (request) => {
    f.searches.push(request);
    return new Promise((resolve) => { resolveSearch = resolve; });
  };
  const pending = sourceUrl(f.downloads, f.permissions, completed());
  await tick();
  assert.deepEqual(f.searches, [{ id: 7 }]);
  f.permissions.onRemoved.emit({ permissions: ["tabs"] });
  f.permissions.onRemoved.emit({ permissions: ["downloads"] });
  resolveSearch([{ id: 7, state: "complete", url: "https://private.example/token" }]);
  assert.equal(await pending, null);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("hostile browser accessors or array elements are never evaluated", async () => {
  const f = fixture();
  let getterReads = 0;
  const row = { id: 7, state: "complete" };
  Object.defineProperty(row, "url", { get() {
    getterReads++; throw Error("private URL");
  } });
  f.downloads.search = () => Promise.resolve([row]);
  assert.equal(await sourceUrl(f.downloads, f.permissions, completed()), null);
  const results = [null];
  Object.defineProperty(results, "0", { get() {
    getterReads++; throw Error("do not inspect private item");
  } });
  f.downloads.search = () => Promise.resolve(results);
  assert.equal(await sourceUrl(f.downloads, f.permissions, completed()), null);
  assert.equal(getterReads, 0);
});

test("actual normalized created events allow an explicit ID-only lookup", async () => {
  const f = fixture();
  const tasks = [];
  const stop = await registerDownloadCreatedEvents(f.downloads, f.permissions,
    (notice) => tasks.push(sourceUrl(f.downloads, f.permissions, notice)),
    { monitoringEnabled: true });
  f.downloads.onCreated.emit({
    id: 23, state: "in_progress", mime: "application/pdf",
    url: "https://private.example/raw", referrer: "private"
  });
  const result = await Promise.all(tasks);
  assert.deepEqual(f.searches, [{ id: 23 }]);
  assert.deepEqual(result, [{
    id: 23, url: "https://source.example/download.pdf?token=private"
  }]);
  stop();
});

test("actual completion transitions can also retrieve the original source URL", async () => {
  const f = fixture();
  const tasks = [];
  const stop = subscribeToDownloadCompletions(f.downloads,
    (notice) => tasks.push(sourceUrl(f.downloads, f.permissions, notice)));
  f.downloads.onChanged.emit({
    id: 30, state: { previous: "in_progress", current: "complete" }
  });
  assert.deepEqual(await Promise.all(tasks), [{
    id: 30, url: "https://source.example/download.pdf?token=private"
  }]);
  assert.deepEqual(f.searches, [{ id: 30 }]);
  stop();
});

test("one-shot lookup never activates the background, scanner or native transport", async () => {
  const module = await readFile(new URL("../src/download-source-url.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "globalThis.chrome", "globalThis.browser", "nativeMessaging",
    "sendNativeMessage(", "connectNative(", "downloads.open(",
    "clamscan", "scan_and_open", "fetch(", "localStorage", "storage.local"
  ]) assert.equal(module.includes(forbidden), false, forbidden);
});
