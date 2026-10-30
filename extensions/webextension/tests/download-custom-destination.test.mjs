import assert from "node:assert/strict";
import test from "node:test";
import { retrieveCompletedDownloadLocalPath } from "../src/download-local-path.js";
import { recheckCompletedDownloadLocation } from "../src/download-postmove.js";
import { submitCompletedPdfDownloadToNative } from "../src/download-native-submit.js";
import { createCompletedDownloadScanRequestGate } from "../src/download-scan-once.js";

// Browser-supplied paths are untrusted even when the user chooses a custom
// save directory. These fixtures never read local files or invoke an opener.
const completion = Object.freeze({ kind: "completed", id: 25 });

function events() {
  const listeners = new Set();
  return {
    addListener(callback) { listeners.add(callback); },
    removeListener(callback) { listeners.delete(callback); },
    emit(value) { for (const callback of [...listeners]) callback(value); },
    get size() { return listeners.size; }
  };
}

function fixture(filename, overrides = {}) {
  const lookups = [], checks = [], submissions = [];
  const downloads = {
    onCreated: events(), onChanged: events(), onErased: events(),
    search(query) {
      lookups.push(query);
      return Promise.resolve([{
        id: query.id, state: "complete", exists: true, paused: false,
        canResume: false, bytesReceived: 512, totalBytes: 512,
        filename, mime: "application/pdf", danger: "safe",
        url: "https://private.invalid/receipt", scanVerified: true,
        authorizesOpen: true, ...overrides
      }]);
    },
    open() { throw Error("browser opening is forbidden"); },
    acceptDanger() { throw Error("warning dismissal is forbidden"); }
  };
  const permissions = {
    onRemoved: events(),
    contains(query) { checks.push(query); return Promise.resolve(true); },
    request() { throw Error("optional permission must not be requested"); }
  };
  const coordinator = {
    nativeScannerReady: true,
    async submitCompletedPdfDownload(request) {
      submissions.push(request);
      return { accepted: true, scanVerified: true, authorizesOpen: true };
    }
  };
  const scanGate = createCompletedDownloadScanRequestGate(downloads);
  return { downloads, permissions, coordinator, scanGate, lookups, checks, submissions };
}

function dispose(f) {
  f.scanGate.dispose();
  assert.deepEqual([
    f.downloads.onCreated.size, f.downloads.onChanged.size,
    f.downloads.onErased.size, f.permissions.onRemoved.size
  ], [0, 0, 0, 0]);
}

function submit(f) {
  return submitCompletedPdfDownloadToNative({
    downloadsApi: f.downloads, permissionsApi: f.permissions,
    completion, coordinator: f.coordinator, scanGate: f.scanGate
  });
}

test("custom POSIX and Windows save locations resolve by exact browser download ID", async () => {
  for (const path of [
    "/Users/alice/Documents/Invoices 2026/receipt.pdf",
    "/Users/alice/Desktop/旅行/receipt.pdf",
    "/Volumes/External Drive/Archive/receipt.pdf",
    "/tmp/pdf-magic-custom/receipt.pdf",
    String.raw`D:\Work Files\Reports\receipt.pdf`,
    "E:/Shared/PDF Library/receipt.pdf"
  ]) {
    const f = fixture(path);
    const located = await retrieveCompletedDownloadLocalPath(
      f.downloads, f.permissions, completion
    );
    assert.deepEqual(located, { id: 25, localPath: path });
    assert.equal(Object.isFrozen(located), true);
    assert.deepEqual(f.lookups, [{ id: 25 }]);
    assert.deepEqual(f.checks, [{ permissions: ["downloads"] }]);
    assert.equal("scanVerified" in located, false);
    assert.equal("authorizesOpen" in located, false);
    dispose(f);
  }
});

test("a PDF saved outside Downloads reaches only the trusted native scan queue", async () => {
  for (const path of [
    "/Users/alice/Documents/Client PDFs/receipt.pdf",
    "/Volumes/Backup/PDF Archive/receipt.PDF",
    String.raw`D:\Documents\Receipts\receipt.pdf`
  ]) {
    const f = fixture(path);
    const result = await submit(f);
    assert.deepEqual(result, {
      status: "submitted", id: 25, scanSubmitted: true,
      scanVerified: false, authorizesOpen: false
    });
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(f.submissions, [{ id: 25, localPath: path }]);
    assert.equal(Object.isFrozen(f.submissions[0]), true);
    assert.deepEqual(f.lookups, Array.from({ length: 6 }, () => ({ id: 25 })));
    assert.deepEqual(f.checks, Array.from({ length: 6 },
      () => ({ permissions: ["downloads"] })));
    assert.equal(JSON.stringify(result).includes(path), false);
    dispose(f);
  }
});

test("rechecking a custom destination never falls back to the original Downloads path", async () => {
  const current = "/Users/alice/Documents/PDF Library/receipt.pdf";
  const f = fixture(current);
  const result = await recheckCompletedDownloadLocation(
    f.downloads, f.permissions, completion,
    Object.freeze({ id: 25, localPath: "/Users/alice/Downloads/receipt.pdf" })
  );
  assert.deepEqual(result, {
    id: 25, currentLocalPath: current, browserPathChanged: true,
    requiresNativeRevalidation: true, authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(f.lookups, [{ id: 25 }, { id: 25 }]);
  dispose(f);
});

test("a custom destination changing during the scan handoff fails closed", async () => {
  const path = "/Users/alice/Documents/receipt.pdf";
  const f = fixture(path);
  const search = f.downloads.search;
  let count = 0;
  f.downloads.search = (query) => {
    count += 1;
    if (count === 5) {
      return Promise.resolve([{
        id: 25, state: "complete", exists: true, paused: false,
        canResume: false, bytesReceived: 512, totalBytes: 512,
        filename: "/Volumes/External/receipt.pdf", mime: "application/pdf",
        danger: "safe"
      }]);
    }
    return search(query);
  };
  assert.deepEqual(await submit(f), {
    status: "unavailable", scanSubmitted: false,
    scanVerified: false, authorizesOpen: false
  });
  assert.deepEqual(f.submissions, []);
  dispose(f);
});

test("custom locations cannot bypass permission, transfer or malware gates", async () => {
  const path = "/Users/alice/Documents/receipt.pdf";
  for (const [overrides, expected] of [
    [{ danger: "dangerous" }, "warning"],
    [{ exists: false }, "missing"],
    [{ state: "in_progress" }, "partial"],
    [{ bytesReceived: 100 }, "incomplete"]
  ]) {
    const f = fixture(path, overrides);
    assert.equal((await submit(f)).scanSubmitted, false, expected);
    assert.deepEqual(f.submissions, []);
    dispose(f);
  }

  for (const path of ["Documents/receipt.pdf", "//server/share/receipt.pdf",
    "/Users/alice/Documents/../receipt.pdf"]) {
    const f = fixture(path);
    assert.equal((await submit(f)).scanSubmitted, false, path);
    assert.deepEqual(f.submissions, []);
    dispose(f);
  }

  const f = fixture(path);
  f.permissions.contains = () => Promise.resolve(false);
  assert.equal((await submit(f)).scanSubmitted, false);
  assert.deepEqual(f.lookups, []);
  assert.deepEqual(f.submissions, []);
  dispose(f);
});
