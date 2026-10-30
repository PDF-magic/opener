import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  submitCompletedPdfDownloadToNative as submit
} from "../src/download-native-submit.js";
import { createCompletedDownloadScanRequestGate } from "../src/download-scan-once.js";

const notice = (id = 7) => Object.freeze({ kind: "completed", id });
const unavailable = {
  status: "unavailable", scanSubmitted: false,
  scanVerified: false, authorizesOpen: false
};
const tick = () => new Promise((resolve) => setImmediate(resolve));

function events() {
  const listeners = new Set();
  return {
    addListener(fn) { listeners.add(fn); },
    removeListener(fn) { listeners.delete(fn); },
    emit(change) { for (const fn of [...listeners]) fn(change); },
    get size() { return listeners.size; }
  };
}

function fixture(options = {}) {
  const filename = Object.hasOwn(options, "filename") ? options.filename : "/home/user/report.PDF";
  const mime = Object.hasOwn(options, "mime") ? options.mime : "application/pdf";
  const lookups = [], grants = [], submitted = [];
  const downloads = {
    onCreated: events(), onChanged: events(), onErased: events(),
    search(query) {
      lookups.push(query);
      return Promise.resolve([{
        id: query.id, state: "complete", exists: true, paused: false,
        canResume: false, bytesReceived: 1024, totalBytes: 1024,
        filename, mime, danger: "safe", url: "https://private.invalid/secret",
        cookies: "secret", scanVerified: true, authorizesOpen: true
      }]);
    }
  };
  const permissions = {
    onRemoved: events(),
    contains(query) { grants.push(query); return Promise.resolve(true); },
    request() { throw Error("must not request permissions"); }
  };
  const coordinator = {
    nativeScannerReady: true,
    async submitCompletedPdfDownload(request) {
      submitted.push(request);
      return { accepted: true, scanVerified: true, authorizesOpen: true };
    }
  };
  const scanGate = createCompletedDownloadScanRequestGate(downloads);
  return { downloads, permissions, coordinator, scanGate, lookups, grants, submitted };
}

function call(f, completion = notice()) {
  return submit({
    downloadsApi: f.downloads, permissionsApi: f.permissions,
    completion, coordinator: f.coordinator, scanGate: f.scanGate
  });
}

function noListeners(f) {
  f.scanGate.dispose();
  assert.deepEqual([
    f.downloads.onCreated.size, f.downloads.onChanged.size,
    f.downloads.onErased.size, f.permissions.onRemoved.size
  ], [0, 0, 0, 0]);
}

test("completed PDF submits to injected native scanner only after repeated scoped checks", async () => {
  const f = fixture();
  const result = await call(f);
  assert.deepEqual(result, {
    status: "submitted", id: 7, scanSubmitted: true,
    scanVerified: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(f.lookups, Array.from({ length: 6 }, () => ({ id: 7 })));
  assert.deepEqual(f.grants, Array.from({ length: 6 }, () => ({
    permissions: ["downloads"]
  })));
  assert.deepEqual(f.submitted, [{ id: 7, localPath: "/home/user/report.PDF" }]);
  assert.equal(Object.isFrozen(f.submitted[0]), true);
  assert.deepEqual(Object.keys(result).sort(),
    ["authorizesOpen", "id", "scanSubmitted", "scanVerified", "status"]);
  assert.equal(JSON.stringify(result).includes("private"), false);
  noListeners(f);
});

test("PDF MIME accepts misleading extensions, not just .pdf basenames", async () => {
  for (const filename of ["/tmp/report.txt", "C:\\Downloads\\report.bin",
    "/tmp/document", "/tmp/report.pdf.exe"]) {
    const f = fixture({ filename, mime: "application/pdf" });
    assert.equal((await call(f)).scanSubmitted, true);
    assert.deepEqual(f.submitted, [{ id: 7, localPath: filename }]);
    noListeners(f);
  }
});

test("PDF suffix with generic or missing MIME still submits as an unverified candidate", async () => {
  for (const mime of ["application/octet-stream", "binary/octet-stream", undefined]) {
    const f = fixture({ mime });
    const response = await call(f);
    assert.equal(response.scanSubmitted, true, String(mime));
    assert.equal(f.submitted.length, 1);
    noListeners(f);
  }
});

test("explicit non-PDF MIME vetoes a misleading .pdf suffix", async () => {
  for (const mime of ["text/plain", "image/png", "application/pdf+json"]) {
    const f = fixture({ mime });
    assert.deepEqual(await call(f), unavailable);
    assert.deepEqual(f.submitted, []);
    noListeners(f);
  }
});

test("no trusted native coordinator, malformed completion or unsupported event source fails before access", async () => {
  for (const coordinator of [
    null, {}, { nativeScannerReady: true },
    { nativeScannerReady: false, submitCompletedPdfDownload() { throw Error("called"); } },
    { nativeScannerReady: true, get submitCompletedPdfDownload() {
      throw Error("untrusted accessor");
    } }
  ]) {
    const f = fixture();
    f.coordinator = coordinator;
    assert.deepEqual(await call(f), unavailable);
    assert.deepEqual(f.lookups, []);
    noListeners(f);
  }
  for (const completion of [null, {}, { kind: "interrupted", id: 7 },
    { kind: "completed", id: "7" }, { kind: "completed", id: -1 },
    { kind: "completed", id: 7, filename: "/private/document.pdf" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 })]) {
    const f = fixture();
    assert.deepEqual(await call(f, completion), unavailable);
    assert.deepEqual(f.lookups, []);
    noListeners(f);
  }
  const f = fixture();
  f.scanGate.dispose();
  delete f.downloads.onErased;
  assert.deepEqual(await call(f), unavailable);
  assert.deepEqual(f.lookups, []);
  assert.equal(f.downloads.onCreated.size, 0);
});

test("missing or incomplete file never reaches native scanner", async () => {
  for (const change of [
    { exists: false }, { state: "in_progress" },
    { state: "interrupted" }, { paused: true },
    { canResume: true }, { error: "FILE_FAILED" },
    { bytesReceived: 22 }, { totalBytes: 2048 },
    { filename: "/tmp/report.pdf.crdownload" }
  ]) {
    const f = fixture();
    f.downloads.search = (q) => {
      f.lookups.push(q);
      return Promise.resolve([{ id: q.id, state: "complete", exists: true,
        paused: false, canResume: false, bytesReceived: 1024, totalBytes: 1024,
        filename: "/tmp/report.pdf", mime: "application/pdf", ...change }]);
    };
    assert.deepEqual(await call(f), unavailable, JSON.stringify(change));
    assert.deepEqual(f.submitted, []);
    noListeners(f);
  }
});

test("download permission denial cannot start a native request", async () => {
  const f = fixture();
  f.permissions.contains = () => Promise.resolve(false);
  assert.deepEqual(await call(f), unavailable);
  assert.deepEqual(f.lookups, []);
  assert.deepEqual(f.submitted, []);
  noListeners(f);
});

test("revocation while looking up metadata discards a pending submission", async () => {
  const f = fixture();
  let resolve;
  f.downloads.search = (q) => {
    f.lookups.push(q);
    return new Promise((done) => { resolve = done; });
  };
  const operation = call(f);
  await tick();
  assert.equal(f.lookups.length, 1);
  f.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  resolve([{ id: 7, state: "complete", exists: true,
    paused: false, canResume: false, bytesReceived: 1024, totalBytes: 1024,
    filename: "/private/report.pdf", mime: "application/pdf" }]);
  assert.deepEqual(await operation, unavailable);
  assert.deepEqual(f.submitted, []);
  noListeners(f);
});

test("new, removed or changed downloads invalidate the in-flight exact ID", async () => {
  for (const change of [
    ["onErased", 7],
    ["onCreated", { id: 7, filename: "/private/new.pdf" }],
    ["onChanged", { id: 7, state: { current: "interrupted" } }],
    ["onChanged", { id: 7, filename: { current: "/private/new.pdf" } }],
    ["onChanged", { id: 7, error: { current: "FILE_FAILED" } }]
  ]) {
    const f = fixture();
    const original = f.downloads.search;
    let calls = 0;
    f.downloads.search = (query) => {
      calls++;
      if (calls === 2) f.downloads[change[0]].emit(change[1]);
      return original(query);
    };
    assert.deepEqual(await call(f), unavailable, change[0]);
    assert.deepEqual(f.submitted, []);
    noListeners(f);
  }
});

test("a changing path between metadata fetches and final recheck fails closed", async () => {
  const f = fixture();
  let lookups = 0;
  const original = f.downloads.search;
  f.downloads.search = (query) => {
    lookups++;
    if (lookups === 5) {
      return Promise.resolve([{ id: 7, state: "complete", exists: true,
        paused: false, canResume: false, bytesReceived: 1024,
        totalBytes: 1024, filename: "/tmp/other.pdf", mime: "application/pdf" }]);
    }
    return original(query);
  };
  assert.deepEqual(await call(f), unavailable);
  assert.deepEqual(f.submitted, []);
  noListeners(f);
});

test("native rejection, errors or untrusted acknowledgment cannot forge scan success", async () => {
  for (const result of [
    { accepted: false }, { accepted: "true" },
    { scanVerified: true }, { authorizesOpen: true },
    null, undefined, { get accepted() { throw Error("private path"); } }
  ]) {
    const f = fixture();
    f.coordinator.submitCompletedPdfDownload = async () => result;
    assert.deepEqual(await call(f), unavailable);
    noListeners(f);
  }
  const f = fixture();
  f.coordinator.submitCompletedPdfDownload = async () => {
    throw Error("/private/secret.pdf");
  };
  assert.deepEqual(await call(f), unavailable);
  noListeners(f);
});

test("revocation during the native handoff cannot be reported as accepted", async () => {
  const f = fixture();
  f.coordinator.submitCompletedPdfDownload = async (request) => {
    f.submitted.push(request);
    f.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
    return { accepted: true };
  };
  assert.deepEqual(await call(f), unavailable);
  assert.equal(f.submitted.length, 1);
  noListeners(f);
});

test("session gate prevents duplicate native submissions until download ID reuse is observed", async () => {
  const f = fixture();
  assert.equal((await call(f)).scanSubmitted, true);
  assert.deepEqual(await call(f), unavailable);
  assert.equal(f.submitted.length, 1);
  f.downloads.onErased.emit(7);
  assert.equal((await call(f)).scanSubmitted, true);
  assert.equal(f.submitted.length, 2);
  noListeners(f);
});

test("missing session-owned scan gate rejects handoff before any browser access", async () => {
  const f = fixture();
  f.scanGate.dispose();
  f.scanGate = null;
  assert.deepEqual(await call(f), unavailable);
  assert.deepEqual(f.lookups, []);
  noListeners({ ...f, scanGate: { dispose() {} } });
});

test("module remains inert, does not bypass native host admission or change app settings", async () => {
  const code = await readFile(
    new URL("../src/download-native-submit.js", import.meta.url), "utf8");
  const background = await readFile(
    new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["sendNativeMessage(", "connectNative(",
    "scan_and_open", "clamscan", "downloads.open(", "node:fs",
    "fetch(", "storage.local", "permissions.request(", "nativeHost.startScan("]) {
    assert.equal(code.includes(forbidden), false, forbidden);
  }
});


test("browser's own malware warnings and accepted-danger downloads veto native submission", async () => {
  for (const danger of ["file", "url", "content", "uncommon", "unwanted",
    "accepted", "allowlistedByPolicy", "asyncScanning",
    "sensitiveContentWarning", "sensitiveContentBlock", undefined, "unknown"]) {
    const f = fixture();
    const original = f.downloads.search;
    f.downloads.search = (query) => original(query).then(rows =>
      rows.map(row => ({ ...row, danger })));
    assert.deepEqual(await call(f), unavailable, String(danger));
    assert.deepEqual(f.submitted, []);
    assert.deepEqual(f.lookups, Array.from({ length: 6 }, () => ({ id: 7 })));
    noListeners(f);
  }
});

test("a browser danger change during metadata lookup cancels native handoff", async () => {
  for (const danger of ["file", "accepted", "safe"]) {
    const f = fixture();
    let count = 0;
    const original = f.downloads.search;
    f.downloads.search = query => {
      count++;
      if (count === 2) {
        f.downloads.onChanged.emit({
          id: 7, danger: { previous: "safe", current: danger }
        });
      }
      return original(query);
    };
    assert.deepEqual(await call(f), unavailable);
    assert.deepEqual(f.submitted, []);
    noListeners(f);
  }
});

test("a danger warning arriving during final browser check cancels native handoff", async () => {
  const f = fixture();
  let count = 0;
  const original = f.downloads.search;
  f.downloads.search = query => {
    count++;
    if (count === 6) {
      f.downloads.onChanged.emit({
        id: 7, danger: { previous: "safe", current: "file" }
      });
    }
    return original(query);
  };
  assert.deepEqual(await call(f), unavailable);
  assert.deepEqual(f.submitted, []);
  noListeners(f);
});

test("native handoff never dismisses or changes a browser malware warning", async () => {
  const f = fixture();
  for (const name of ["acceptDanger", "open", "removeFile", "erase"]) {
    f.downloads[name] = () => { throw Error("MUST NOT CALL: " + name); };
  }
  assert.equal((await call(f)).scanSubmitted, true);
  const source = await readFile(
    new URL("../src/download-native-submit.js", import.meta.url), "utf8");
  for (const forbidden of ["acceptDanger(", "downloads.open(",
    "downloads.removeFile(", "downloads.erase("]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
  noListeners(f);
});
