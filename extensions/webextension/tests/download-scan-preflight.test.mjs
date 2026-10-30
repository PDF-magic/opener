import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { preflightCompletedDownloadForScan as preflight } from "../src/download-scan-preflight.js";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}

function fixture() {
  const searches = [], checks = [];
  const downloads = {
    onCreated: eventSource(), onChanged: eventSource(), onErased: eventSource(),
    search(query) {
      searches.push(query);
      return Promise.resolve([{
        id: query.id, state: "complete", paused: false, canResume: false,
        exists: true, bytesReceived: 1024, totalBytes: 1024,
        filename: "/home/user/report.pdf", url: "https://private.invalid/report.pdf",
        cookies: "secret", scanVerified: true
      }]);
    }
  };
  const permissions = {
    onRemoved: eventSource(),
    contains(query) { checks.push(query); return Promise.resolve(true); },
    request() { throw Error("No implicit permission request"); }
  };
  return { downloads, permissions, searches, checks };
}

const completed = (id = 7) => Object.freeze({ kind: "completed", id });
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("only a fresh completed, unpaused transfer with all bytes received passes", async () => {
  const f = fixture();
  const result = await preflight(f.downloads, f.permissions, completed());
  assert.deepEqual(f.checks, [{ permissions: ["downloads"] }]);
  assert.deepEqual(f.searches, [{ id: 7 }]);
  assert.deepEqual(result, {
    id: 7, transferComplete: true, scanVerified: false,
    authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.equal(JSON.stringify(result).includes("/home/user"), false);
  assert.equal(f.permissions.onRemoved.size, 0);
});

test("incomplete, interrupted, queued and paused items never pass the preflight", async () => {
  const changes = [
    { state: "in_progress" }, { state: "interrupted" },
    { state: "complete", paused: true }, { canResume: true },
    { exists: false }, { error: "NETWORK_FAILED" },
    { bytesReceived: 512 }, { bytesReceived: 1025 },
    { bytesReceived: 0 }, { totalBytes: 0 },
    { totalBytes: 2048 }, { totalBytes: -2 },
    { totalBytes: "1024" }, { bytesReceived: "1024" },
    { bytesReceived: Number.MAX_SAFE_INTEGER + 1 }
  ];
  for (const change of changes) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve([{
      id: 7, state: "complete", paused: false, canResume: false, exists: true,
      filename: "/home/user/report.pdf", bytesReceived: 1024, totalBytes: 1024, ...change
    }]);
    assert.equal(await preflight(f.downloads, f.permissions, completed()), null,
      JSON.stringify(change));
  }
});

test("browser completed unknown-length transfer uses completed state and actual received bytes", async () => {
  const f = fixture();
  f.downloads.search = () => Promise.resolve([{
    id: 7, state: "complete", paused: false, canResume: false, exists: true,
    bytesReceived: 4096, totalBytes: -1, filename: "/home/user/report.pdf"
  }]);
  assert.equal((await preflight(f.downloads, f.permissions, completed())).transferComplete, true);
});

test("partial-download names and disguised temporary extensions fail closed", async () => {
  for (const filename of [
    "report.pdf.crdownload", "/tmp/report.pdf.part", "/tmp/file.partial",
    "/tmp/file.PART", "/tmp/report.pdf.download", "/tmp/report.pdf.tmp",
    "/tmp/report.PDF.icloud", "file:///tmp/report.pdf",
    "https://example.invalid/report.pdf", "", "a\n.pdf",
    "file\u0000.pdf", "x".repeat(4097)
  ]) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve([{
      id: 7, state: "complete", paused: false, canResume: false, exists: true,
      bytesReceived: 50, totalBytes: 50, filename
    }]);
    assert.equal(await preflight(f.downloads, f.permissions, completed()), null, filename);
  }
});

test("invalid completion notices never query privileged browser APIs", async () => {
  const f = fixture();
  let getters = 0;
  const getter = { kind: "completed" };
  Object.defineProperty(getter, "id", { get() { getters++; throw Error("secret"); } });
  const symbol = { kind: "completed", id: 7 };
  symbol[Symbol("private")] = true;
  for (const event of [null, {}, "complete", [], getter, symbol,
    { kind: "interrupted", id: 7 }, { kind: "completed", id: -1 },
    { kind: "completed", id: "7" }, { kind: "completed", id: 1.2 },
    { kind: "completed", id: 7, filename: "/private/document.pdf" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 })]) {
    assert.equal(await preflight(f.downloads, f.permissions, event), null);
  }
  assert.equal(getters, 0);
  assert.deepEqual(f.checks, []);
  assert.deepEqual(f.searches, []);
});

test("missing permission or broken browser APIs never initiate scan prerequisites", async () => {
  for (const contains of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => Promise.reject(Error("/private/browser-profile")),
    () => false, () => undefined, () => { throw Error("secret"); }
  ]) {
    const f = fixture();
    f.permissions.contains = contains;
    assert.equal(await preflight(f.downloads, f.permissions, completed()), null);
    assert.deepEqual(f.searches, []);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
  const f = fixture();
  delete f.permissions.onRemoved;
  assert.equal(await preflight(f.downloads, f.permissions, completed()), null);
  delete f.downloads.search;
  assert.equal(await preflight(f.downloads, f.permissions, completed()), null);
});

test("revocation during permission check or download lookup fails closed", async () => {
  let resolveGrant;
  const f = fixture();
  f.permissions.contains = () => new Promise(resolve => { resolveGrant = resolve; });
  const pending = preflight(f.downloads, f.permissions, completed());
  assert.equal(f.permissions.onRemoved.size, 1);
  f.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  resolveGrant(true);
  assert.equal(await pending, null);
  assert.deepEqual(f.searches, []);
  assert.equal(f.permissions.onRemoved.size, 0);

  const next = fixture();
  let resolveLookup;
  next.downloads.search = query => {
    next.searches.push(query);
    return new Promise(resolve => { resolveLookup = resolve; });
  };
  const later = preflight(next.downloads, next.permissions, completed());
  await tick();
  assert.deepEqual(next.searches, [{ id: 7 }]);
  next.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  resolveLookup([{ id: 7, state: "complete", paused: false,
    canResume: false, exists: true, filename: "/secret.pdf",
    bytesReceived: 1024, totalBytes: 1024 }]);
  assert.equal(await later, null);
  assert.equal(next.permissions.onRemoved.size, 0);
});

test("ambiguous, missing or hostile browser result records cannot pass", async () => {
  for (const result of [[], null, {}, [null], [{
    id: 8, state: "complete", paused: false, canResume: false,
    exists: true, bytesReceived: 4, totalBytes: 4, filename: "a.pdf"
  }], [{
    id: 7, state: "complete", paused: false, canResume: false,
    exists: true, bytesReceived: 4, totalBytes: 4, filename: "a.pdf"
  }, {
    id: 7, state: "complete", paused: false, canResume: false,
    exists: true, bytesReceived: 4, totalBytes: 4, filename: "b.pdf"
  }]]) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve(result);
    assert.equal(await preflight(f.downloads, f.permissions, completed()), null);
  }
  let reads = 0;
  const f = fixture();
  const entry = { id: 7, state: "complete" };
  Object.defineProperty(entry, "filename", {
    get() { reads++; throw Error("private filename"); }
  });
  f.downloads.search = () => Promise.resolve([entry]);
  assert.equal(await preflight(f.downloads, f.permissions, completed()), null);
  const array = [null];
  Object.defineProperty(array, "0", {
    get() { reads++; throw Error("secret index"); }
  });
  f.downloads.search = () => Promise.resolve(array);
  assert.equal(await preflight(f.downloads, f.permissions, completed()), null);
  assert.equal(reads, 0);
});

test("a real completion update can be rechecked but earlier state cannot", async () => {
  const f = fixture(), checked = [], operations = [];
  const stop = subscribeToDownloadCompletions(f.downloads, (notice) => {
    operations.push(preflight(f.downloads, f.permissions, notice)
      .then(outcome => checked.push(outcome)));
  });
  f.downloads.onChanged.emit({ id: 7, state: { current: "in_progress" } });
  f.downloads.onChanged.emit({ id: 7, state: { current: "interrupted" } });
  assert.deepEqual(f.searches, []);
  f.downloads.onChanged.emit({ id: 7, state: { current: "complete" } });
  await Promise.all(operations);
  assert.equal(f.searches.length, 1);
  assert.equal(checked[0].transferComplete, true);
  stop();
});

test("source remains inert and never scans, opens, reads files or changes user settings", async () => {
  const code = await readFile(new URL("../src/download-scan-preflight.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "connectNative(", "sendNativeMessage(", "downloads.open(", "scan_and_open",
    "clamscan", "node:fs", "fetch(", "localStorage", "storage.local",
    "chrome.downloads", "browser.downloads"
  ]) assert.equal(code.includes(forbidden), false, forbidden);
});
