import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { recheckCompletedDownloadLocation as recheck } from "../src/download-postmove.js";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(callback) { listeners.add(callback); },
    removeListener(callback) { listeners.delete(callback); },
    emit(value) { for (const callback of [...listeners]) callback(value); },
    get size() { return listeners.size; }
  };
}

const prior = (id = 7, localPath = "/Users/alice/Downloads/report.pdf") =>
  Object.freeze({ id, localPath });
const completed = (id = 7) => Object.freeze({ kind: "completed", id });
const tick = () => new Promise(resolve => setImmediate(resolve));

function fixture(filename = "/Users/alice/Downloads/report.pdf") {
  const searches = [], checks = [];
  const permissions = {
    onRemoved: eventSource(),
    contains(query) {
      checks.push(query);
      return Promise.resolve(true);
    },
    request() { throw Error("must not request permissions"); }
  };
  const downloads = {
    search(query) {
      searches.push(query);
      return Promise.resolve([{
        id: query.id, state: "complete", paused: false, canResume: false,
        exists: true, error: undefined, bytesReceived: 1024, totalBytes: 1024,
        filename, url: "https://private.invalid/report.pdf",
        cookies: "secret", scanVerified: true
      }]);
    }
  };
  return { permissions, downloads, searches, checks };
}

test("refreshes the browser-reported location when a file moves immediately after completion", async () => {
  const f = fixture("/Users/alice/Documents/renamed.pdf");
  const result = await recheck(f.downloads, f.permissions, completed(), prior());
  assert.deepEqual(result, {
    id: 7, currentLocalPath: "/Users/alice/Documents/renamed.pdf",
    browserPathChanged: true, requiresNativeRevalidation: true,
    authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(f.searches, [{ id: 7 }, { id: 7 }]);
  assert.deepEqual(f.checks, [
    { permissions: ["downloads"] }, { permissions: ["downloads"] }
  ]);
  assert.equal(f.permissions.onRemoved.size, 0);
  for (const field of ["url", "cookies", "filename", "scanVerified"]) {
    assert.equal(field in result, false);
  }
});

test("unchanged browser paths still require native filesystem identity verification", async () => {
  const f = fixture();
  const result = await recheck(f.downloads, f.permissions, completed(), prior());
  assert.equal(result.browserPathChanged, false);
  assert.equal(result.requiresNativeRevalidation, true);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
});

test("a moved, deleted, interrupted or partially written file has no usable stale-path fallback", async () => {
  for (const override of [
    null, [], [{ id: 8, state: "complete", filename: "/tmp/other.pdf" }],
    [{ id: 7, state: "interrupted", filename: "/tmp/moved.pdf" }],
    [{ id: 7, state: "complete", filename: "/tmp/moved.pdf",
      exists: false, paused: false, canResume: false, bytesReceived: 1024, totalBytes: 1024 }],
    [{ id: 7, state: "complete", filename: "/tmp/moved.pdf",
      exists: true, paused: true, canResume: false, bytesReceived: 1024, totalBytes: 1024 }],
    [{ id: 7, state: "complete", filename: "/tmp/moved.pdf",
      exists: true, paused: false, canResume: false, bytesReceived: 100, totalBytes: 1024 }],
    [{ id: 7, state: "complete", filename: "/tmp/moved.pdf.crdownload",
      exists: true, paused: false, canResume: false, bytesReceived: 1024, totalBytes: 1024 }]
  ]) {
    const f = fixture();
    f.downloads.search = (query) => {
      f.searches.push(query);
      return Promise.resolve(override);
    };
    assert.equal(await recheck(f.downloads, f.permissions, completed(), prior()), null);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
});

test("a move or deletion between path lookup and completed-transfer recheck fails closed", async () => {
  for (const change of [
    { exists: false },
    { state: "interrupted" },
    { bytesReceived: 512 },
    { filename: "/Users/alice/Documents/report.pdf.part" }
  ]) {
    const f = fixture();
    let queries = 0;
    f.downloads.search = () => {
      queries++;
      const item = {
        id: 7, state: "complete", paused: false, canResume: false,
        exists: true, filename: "/Users/alice/Documents/report.pdf",
        bytesReceived: 1024, totalBytes: 1024
      };
      return Promise.resolve([{ ...item, ...(queries === 2 ? change : {}) }]);
    };
    assert.equal(await recheck(f.downloads, f.permissions, completed(), prior()), null);
    assert.equal(queries, 2);
  }
});

test("invalid or mismatched prior path snapshots cannot cause a privileged download lookup", async () => {
  const f = fixture();
  let getterReads = 0;
  const getter = { id: 7 };
  Object.defineProperty(getter, "localPath", {
    get() { getterReads++; throw Error("secret path"); }
  });
  const proxy = new Proxy({ id: 7, localPath: "/tmp/a.pdf" }, {
    ownKeys() { throw Error("secret"); }
  });
  const symbol = { id: 7, localPath: "/tmp/a.pdf" };
  symbol[Symbol("secret")] = true;
  for (const snapshot of [
    null, undefined, {}, [], getter, proxy, symbol,
    { id: 8, localPath: "/tmp/a.pdf" },
    { id: 7, localPath: 12 },
    { id: 7, localPath: "relative.pdf" },
    { id: 7, localPath: "//host/share.pdf" },
    { id: 7, localPath: "/tmp/../a.pdf" },
    { id: 7, localPath: "/tmp//a.pdf" },
    { id: 7, localPath: "C:\\dir\\..\\a.pdf" },
    { id: 7, localPath: "C:\\dir\\a.pdf:stream" },
    { id: 7, localPath: "/tmp/a.pdf", additional: true },
    Object.assign(Object.create({ id: 7 }), { localPath: "/tmp/a.pdf" })
  ]) {
    assert.equal(await recheck(f.downloads, f.permissions, completed(), snapshot), null);
  }
  assert.equal(getterReads, 0);
  assert.deepEqual(f.searches, []);
  assert.deepEqual(f.checks, []);
});

test("malformed completion events never access browser APIs or expose older locations", async () => {
  const f = fixture();
  for (const completion of [
    null, undefined, { kind: "complete", id: 7 },
    { kind: "completed", id: 8 }, { kind: "completed", id: "7" },
    { kind: "completed", id: 7, url: "https://private.invalid" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 })
  ]) {
    assert.equal(await recheck(f.downloads, f.permissions, completion, prior()), null);
  }
  assert.equal(f.searches.length, 0);
  assert.equal(f.checks.length, 0);
});

test("denied or revoked downloads permission drops the rechecked location", async () => {
  const f = fixture("/Users/alice/Documents/updated.pdf");
  f.permissions.contains = () => Promise.resolve(false);
  assert.equal(await recheck(f.downloads, f.permissions, completed(), prior()), null);
  assert.deepEqual(f.searches, []);
  assert.equal(f.permissions.onRemoved.size, 0);

  const after = fixture();
  let resolveSearch, calls = 0;
  after.downloads.search = query => {
    after.searches.push(query);
    calls++;
    if (calls === 2) return new Promise(resolve => { resolveSearch = resolve; });
    return Promise.resolve([{
      id: 7, state: "complete", filename: "/tmp/report.pdf"
    }]);
  };
  const pending = recheck(after.downloads, after.permissions, completed(), prior());
  await tick();
  assert.equal(calls, 2);
  after.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  resolveSearch([{ id: 7, state: "complete", paused: false, canResume: false,
    exists: true, filename: "/tmp/report.pdf", bytesReceived: 1024, totalBytes: 1024 }]);
  assert.equal(await pending, null);
  assert.equal(after.permissions.onRemoved.size, 0);
});

test("module remains passive and does not scan, move, open, or persist files", async () => {
  const code = await readFile(new URL("../src/download-postmove.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "globalThis.chrome", "globalThis.browser", "downloads.open(",
    "permissions.request(", "sendNativeMessage(", "connectNative(",
    "scan_and_open", "node:fs", "fetch(", "storage.local", "console.log("
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
