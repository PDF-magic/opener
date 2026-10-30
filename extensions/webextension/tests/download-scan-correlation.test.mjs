import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { associateDownloadIdentifierWithScanCandidate as associate } from "../src/download-scan-correlation.js";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";

function emitter() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}
const completion = (id = 7) => Object.freeze({ kind: "completed", id });
const tick = () => new Promise((resolve) => setImmediate(resolve));

function fixture(id = 7) {
  const searches = [], permissionsChecked = [];
  const record = {
    id, filename: "/tmp/finished.pdf", state: "complete",
    paused: false, canResume: false, exists: true,
    bytesReceived: 4096, totalBytes: 4096,
    url: "https://private.example/report.pdf?secret=yes",
    referrer: "https://private.example", scanVerified: true,
    authorizesOpen: true, danger: "safe", cookies: "sensitive"
  };
  const downloads = {
    onCreated: emitter(), onChanged: emitter(), onErased: emitter(),
    search(query) {
      searches.push(query);
      return Promise.resolve([{ ...record }]);
    },
    open() { throw Error("Download must not be opened"); }
  };
  const permissions = {
    onRemoved: emitter(),
    contains(query) { permissionsChecked.push(query); return Promise.resolve(true); },
    request() { throw Error("Never request permission implicitly"); }
  };
  return { downloads, permissions, searches, permissionsChecked, record };
}

test("associates one completed browser ID to the exact candidate path and no scan privilege", async () => {
  const f = fixture();
  const result = await associate(f.downloads, f.permissions, completion());
  assert.deepEqual(f.searches, [{ id: 7 }, { id: 7 }]);
  assert.deepEqual(f.permissionsChecked, [
    { permissions: ["downloads"] }, { permissions: ["downloads"] }
  ]);
  assert.deepEqual(result, {
    kind: "browser-download-scan-candidate",
    downloadId: 7, browserDownloadIdentifier: "7", path: "/tmp/finished.pdf",
    transferComplete: true, scanVerified: false,
    authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(f.permissions.onRemoved.size, 0);
  assert.equal(JSON.stringify(result).includes("private.example"), false);
  assert.equal("sourceUrl" in result, false);
  assert.equal("cookies" in result, false);
});

test("numeric ID zero is preserved exactly for the native string receiving field", async () => {
  const f = fixture(0);
  assert.deepEqual(await associate(f.downloads, f.permissions, completion(0)), {
    kind: "browser-download-scan-candidate",
    downloadId: 0, browserDownloadIdentifier: "0", path: "/tmp/finished.pdf",
    transferComplete: true, scanVerified: false,
    authorizesScan: false, authorizesOpen: false
  });
});

test("preserves safely normalized absolute Windows paths without changing the download ID", async () => {
  const f = fixture(42);
  f.record.filename = "C:\\Users\\Alice\\Downloads\\finished.pdf";
  const result = await associate(f.downloads, f.permissions, completion(42));
  assert.equal(result.browserDownloadIdentifier, "42");
  assert.equal(result.path, "C:\\Users\\Alice\\Downloads\\finished.pdf");
  assert.equal(result.authorizesScan, false);
});

test("rejects invalid, forged or incomplete completion notices before any browser lookup", async () => {
  const f = fixture();
  let accessed = 0;
  const getter = { kind: "completed" };
  Object.defineProperty(getter, "id", { get() {
    accessed++; throw Error("private browser data");
  } });
  const symbol = { kind: "completed", id: 7 };
  symbol[Symbol("hidden")] = true;
  for (const notice of [
    null, undefined, {}, [], "completed",
    { kind: "created", id: 7 }, { kind: "interrupted", id: 7 },
    { kind: "completed", id: -1 }, { kind: "completed", id: 1.5 },
    { kind: "completed", id: "7" },
    { kind: "completed", id: Number.MAX_SAFE_INTEGER + 1 },
    { kind: "completed", id: 7, path: "/tmp/private.pdf" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 }),
    getter, symbol
  ]) assert.equal(await associate(f.downloads, f.permissions, notice), null);
  assert.equal(accessed, 0);
  assert.deepEqual(f.searches, []);
  assert.deepEqual(f.permissionsChecked, []);
});

test("mismatched IDs cannot be coupled to a different scan candidate", async () => {
  const f = fixture(8);
  assert.equal(await associate(f.downloads, f.permissions, completion(7)), null);
  assert.deepEqual(f.searches, [{ id: 7 }]);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("missing, relative and temporary browser paths cannot create scan candidates", async () => {
  for (const path of [null, undefined, "", "file.pdf", "../report.pdf",
    "file:///tmp/report.pdf", "/tmp/../private.pdf", "\\\\server\\share\\private.pdf"]) {
    const f = fixture();
    f.record.filename = path;
    assert.equal(await associate(f.downloads, f.permissions, completion()), null,
      JSON.stringify(path));
    assert.equal(f.searches.length, 1);
  }
});

test("a later interrupted or partial transfer vetoes an earlier complete filename", async () => {
  for (const changed of [
    { state: "in_progress" }, { state: "interrupted" },
    { paused: true }, { canResume: true }, { exists: false },
    { error: "NETWORK_FAILED" }, { bytesReceived: 100 },
    { filename: "/tmp/unfinished.pdf.crdownload" }, { totalBytes: 5000 }
  ]) {
    const f = fixture();
    let calls = 0;
    f.downloads.search = (query) => {
      f.searches.push(query);
      calls++;
      return Promise.resolve([{ ...f.record, ...(calls === 2 ? changed : {}) }]);
    };
    assert.equal(await associate(f.downloads, f.permissions, completion()), null,
      JSON.stringify(changed));
    assert.deepEqual(f.searches, [{ id: 7 }, { id: 7 }]);
  }
});

test("permission denial prevents any browser download lookup and no association is returned", async () => {
  for (const contains of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => undefined, () => true,
    () => Promise.reject(Error("secret browser path"))
  ]) {
    const f = fixture();
    f.permissions.contains = contains;
    assert.equal(await associate(f.downloads, f.permissions, completion()), null);
    assert.deepEqual(f.searches, []);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
});

test("permission revoked during the first lookup discards the candidate", async () => {
  const f = fixture();
  let reply;
  f.downloads.search = (query) => {
    f.searches.push(query);
    return new Promise(resolve => { reply = resolve; });
  };
  const pending = associate(f.downloads, f.permissions, completion());
  await tick();
  assert.deepEqual(f.searches, [{ id: 7 }]);
  f.permissions.onRemoved.emit({ permissions: ["downloads"] });
  reply([{ ...f.record }]);
  assert.equal(await pending, null);
  assert.equal(f.permissions.onRemoved.size, 0);
  assert.equal(f.searches.length, 1);
});

test("permission revoked during final completion recheck discards the candidate", async () => {
  const f = fixture();
  let secondReply;
  f.downloads.search = (query) => {
    f.searches.push(query);
    if (f.searches.length === 1) return Promise.resolve([{ ...f.record }]);
    return new Promise(resolve => { secondReply = resolve; });
  };
  const pending = associate(f.downloads, f.permissions, completion());
  await tick();
  assert.deepEqual(f.searches, [{ id: 7 }, { id: 7 }]);
  f.permissions.onRemoved.emit({ permissions: ["downloads"] });
  secondReply([{ ...f.record }]);
  assert.equal(await pending, null);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("a real completion event may produce a correlation candidate without dispatching a scan", async () => {
  const f = fixture();
  const pending = [];
  const stop = subscribeToDownloadCompletions(f.downloads, notice => {
    pending.push(associate(f.downloads, f.permissions, notice));
  });
  f.downloads.onChanged.emit({ id: 7, state: { current: "in_progress" } });
  f.downloads.onChanged.emit({ id: 7, state: { current: "interrupted" } });
  assert.deepEqual(f.searches, []);
  f.downloads.onChanged.emit({ id: 7, state: { current: "complete" } });
  const results = await Promise.all(pending);
  assert.equal(results.length, 1);
  assert.equal(results[0].browserDownloadIdentifier, "7");
  assert.equal(results[0].authorizesScan, false);
  stop();
});

test("no listener, native message, filesystem, scanner or settings effect occurs on import", async () => {
  const source = await readFile(new URL("../src/download-scan-correlation.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "globalThis.chrome", "globalThis.browser", "nativeMessaging",
    "sendNativeMessage(", "connectNative(", "scan_and_open", "clamscan",
    "fetch(", "node:fs", "storage.local", "downloads.open("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
