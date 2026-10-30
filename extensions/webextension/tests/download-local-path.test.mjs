import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { retrieveCompletedDownloadLocalPath as getLocalPath } from "../src/download-local-path.js";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}

const completed = (id = 7) => Object.freeze({ kind: "completed", id });

function fixture(filename = "/Users/alice/Downloads/document.pdf") {
  const searches = [];
  const checks = [];
  const onRemoved = eventSource();
  const downloads = {
    search(query) {
      searches.push(query);
      return Promise.resolve([{ id: query.id, state: "complete", filename,
        url: "https://private.invalid", cookies: "secret",
        scanVerified: true, authorizesOpen: true }]);
    }
  };
  const permissions = {
    onRemoved,
    contains(query) {
      checks.push(query);
      return Promise.resolve(true);
    },
    request() { throw Error("must never request permission"); }
  };
  return { downloads, permissions, searches, checks, onRemoved };
}

test("returns only an immutable absolute local path after exact-ID permission check", async () => {
  const f = fixture();
  const result = await getLocalPath(f.downloads, f.permissions, completed());
  assert.deepEqual(f.checks, [{ permissions: ["downloads"] }]);
  assert.deepEqual(f.searches, [{ id: 7 }]);
  assert.deepEqual(result, {
    id: 7, localPath: "/Users/alice/Downloads/document.pdf"
  });
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(Object.keys(result), ["id", "localPath"]);
  assert.equal(f.onRemoved.size, 0);
  assert.equal("scanVerified" in result, false);
  assert.equal("url" in result, false);
});

test("accepts an absolute Windows drive path with either separator", async () => {
  for (const path of [
    "C:\\Users\\Alice\\Downloads\\document.pdf",
    "D:/Downloads/document.PDF"
  ]) {
    const f = fixture(path);
    assert.deepEqual(await getLocalPath(f.downloads, f.permissions, completed()), {
      id: 7, localPath: path
    });
    assert.equal(f.onRemoved.size, 0);
  }
});

test("missing, relative, URL-shaped and network/device paths are unavailable", async () => {
  for (const filename of [
    undefined, null, "", "document.pdf", "Downloads/document.pdf",
    "./document.pdf", "../Downloads/document.pdf", "~/Downloads/document.pdf",
    "C:Downloads\\document.pdf", "file:///Users/alice/document.pdf",
    "https://example.invalid/document.pdf", "\\\\server\\share\\document.pdf",
    "\\\\?\\C:\\Downloads\\document.pdf", "//server/share/document.pdf",
    "/", "C:\\", "/tmp//document.pdf", "C:\\temp\\\\document.pdf",
    "/Users/alice/../Downloads/document.pdf", "C:\\Users\\..\\document.pdf",
    "/tmp/./document.pdf", "C:\\Users\\ .\\document.pdf:stream",
    "/tmp/document\u0000.pdf", "/tmp/doc\nument.pdf", "/tmp/" + "x".repeat(4097)
  ]) {
    const f = fixture(filename);
    assert.equal(await getLocalPath(f.downloads, f.permissions, completed()), null,
      JSON.stringify(filename));
    assert.equal(f.onRemoved.size, 0);
  }
});

test("denied, unverifiable or absent permissions never search browser downloads", async () => {
  for (const contains of [
    () => Promise.resolve(false), () => false,
    () => undefined, () => Promise.reject(Error("private path")),
    () => { throw Error("private path"); }
  ]) {
    const f = fixture();
    f.permissions.contains = contains;
    assert.equal(await getLocalPath(f.downloads, f.permissions, completed()), null);
    assert.deepEqual(f.searches, []);
    assert.equal(f.onRemoved.size, 0);
  }
  const f = fixture();
  delete f.permissions.onRemoved;
  assert.equal(await getLocalPath(f.downloads, f.permissions, completed()), null);
  assert.deepEqual(f.searches, []);
});

test("untrusted or forged completion notices do not access browser metadata", async () => {
  const f = fixture();
  for (const notice of [
    null, {}, { kind: "interrupted", id: 7 }, { kind: "completed", id: "7" },
    { kind: "completed", id: -1 }, { kind: "completed", id: 7, filename: "private" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 })
  ]) assert.equal(await getLocalPath(f.downloads, f.permissions, notice), null);
  assert.deepEqual(f.checks, []);
  assert.deepEqual(f.searches, []);
});

test("revocation during permission verification suppresses the lookup", async () => {
  const f = fixture();
  let finish;
  f.permissions.contains = () => new Promise((resolve) => { finish = resolve; });
  const pending = getLocalPath(f.downloads, f.permissions, completed());
  assert.equal(f.onRemoved.size, 1);
  f.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  finish(true);
  assert.equal(await pending, null);
  assert.deepEqual(f.searches, []);
  assert.equal(f.onRemoved.size, 0);
});

test("revocation while the download lookup is pending drops the private path", async () => {
  const f = fixture();
  let finish;
  f.downloads.search = (query) => {
    f.searches.push(query);
    return new Promise((resolve) => { finish = resolve; });
  };
  const pending = getLocalPath(f.downloads, f.permissions, completed());
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(f.searches, [{ id: 7 }]);
  f.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  finish([{ id: 7, state: "complete", filename: "/private/late.pdf" }]);
  assert.equal(await pending, null);
  assert.equal(f.onRemoved.size, 0);
});

test("missing or mismatched finished download records fail closed", async () => {
  for (const records of [
    [], null, [{ id: 7, state: "interrupted",
      filename: "/tmp/incomplete.pdf" }],
    [{ id: 8, state: "complete", filename: "/tmp/other.pdf" }],
    [{ id: 7, state: "complete", filename: "/tmp/file.pdf" },
      { id: 7, state: "complete", filename: "/tmp/file2.pdf" }]
  ]) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve(records);
    assert.equal(await getLocalPath(f.downloads, f.permissions, completed()), null);
  }
});

test("browser failures never leak errors containing sensitive paths", async () => {
  const f = fixture();
  f.downloads.search = () => Promise.reject(Error("/Users/secret/private.pdf"));
  assert.equal(await getLocalPath(f.downloads, f.permissions, completed()), null);
  assert.equal(f.onRemoved.size, 0);
});

test("module import does not activate downloads, scanners or native messaging", async () => {
  const source = await readFile(new URL("../src/download-local-path.js", import.meta.url),
    "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "globalThis.chrome", "globalThis.browser", "downloads.open(",
    "permissions.request", "nativeMessaging", "sendNativeMessage(",
    "scan_and_open", "clamscan", "fetch(", "storage.local", "console.log("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
