import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectMisleadingPdfExtension as detect } from "../src/download-misleading-extension.js";
import { retrieveCompletedDownloadMime } from "../src/download-mime.js";
import { retrieveCompletedDownloadFilename } from "../src/download-filename.js";

const mime = (value = "application/pdf", id = 7) => Object.freeze({ id, mime: value });
const filename = (value = "/Users/private/report.txt", id = 7) =>
  Object.freeze({ id, filename: value });

function eventSource() {
  const listeners = new Set();
  return {
    addListener(fn) { listeners.add(fn); },
    removeListener(fn) { listeners.delete(fn); },
    emit(value) { for (const fn of [...listeners]) fn(value); },
    get size() { return listeners.size; }
  };
}

test("PDF MIME detects misleading .txt, .bin and double extensions without revealing filenames", () => {
  for (const name of [
    "/home/user/report.txt", "C:\\Users\\Private\\report.bin",
    "/tmp/report.pdf.exe", "report.json", "/tmp/report", ".pdf"
  ]) {
    const result = detect(mime(), filename(name));
    assert.deepEqual(result, {
      id: 7, isPdfCandidate: true, hasMisleadingExtension: true,
      evidence: "browser-pdf-mime", authorizesOpen: false
    });
    assert.equal(Object.isFrozen(result), true);
    assert.equal(JSON.stringify(result).includes("report"), false);
  }
});

test("correct PDF suffixes do not trigger misleading-extension detection", () => {
  for (const name of ["report.pdf", "/home/user/document.PDF",
    "C:\\Downloads\\report.PdF", "reports.archive.pdf"]) {
    assert.deepEqual(detect(mime(), filename(name)), {
      id: 7, isPdfCandidate: true, hasMisleadingExtension: false,
      evidence: "browser-pdf-mime", authorizesOpen: false
    });
  }
});

test("recognized PDF MIME tolerates case and valid parameters but remains untrusted", () => {
  for (const value of ["APPLICATION/PDF", "application/x-pdf",
    "application/pdf; charset=UTF-8", "Application/Pdf; charset=\"binary\""]) {
    const result = detect(mime(value), filename("report.txt"));
    assert.equal(result.isPdfCandidate, true);
    assert.equal(result.hasMisleadingExtension, true);
    assert.equal(result.authorizesOpen, false);
  }
});

test("a suspicious extension cannot override non-PDF or generic MIME", () => {
  for (const value of ["text/plain", "application/json",
    "image/png", "application/octet-stream", "application/pdf+json"]) {
    for (const name of ["report.pdf", "report.txt"]) {
      assert.deepEqual(detect(mime(value), filename(name)), {
        id: 7, isPdfCandidate: false, hasMisleadingExtension: false,
        evidence: "none", authorizesOpen: false
      });
    }
  }
});

test("invalid records, mismatched IDs and extra sensitive fields fail closed", () => {
  const getter = { id: 7 };
  Object.defineProperty(getter, "mime", { get() { throw Error("private"); } });
  for (const args of [
    [null, filename()], [mime(), null], [mime(), filename("report.txt", 8)],
    [mime("application/pdf", -1), filename()],
    [{ id: "7", mime: "application/pdf" }, filename()],
    [{ id: 7, mime: "application/pdf", url: "https://secret.invalid" }, filename()],
    [getter, filename()], [Object.assign(Object.create({ id: 7 }),
      { mime: "application/pdf" }), filename()],
    [mime(), { id: 7, filename: "file.pdf", scanVerified: true }],
    [mime(), { id: 7, filename: 5 }],
    [mime(), Object.freeze({ id: 7, filename: "file.pdf", [Symbol("secret")]: true })]
  ]) assert.equal(detect(...args), null);
});

test("malformed browser MIME and unsafe filename strings fail closed", () => {
  for (const value of ["", "application/pdf\nCookie: private", "application/pdf; bad",
    "application", "not a type", "x".repeat(256)]) {
    assert.equal(detect(mime(value), filename()), null, JSON.stringify(value));
  }
  for (const name of ["", "/", "C:\\Downloads\\", "file:///private/report.txt",
    "https://private.invalid/report.txt", "/private/file\u0000.txt",
    "/private/bad\nfile.txt", "x".repeat(4097)]) {
    assert.equal(detect(mime(), filename(name)), null, JSON.stringify(name));
  }
});

test("hostile proxies do not expose errors or crash the classifier", () => {
  const proxy = new Proxy({}, { getPrototypeOf() { throw Error("private"); } });
  assert.equal(detect(proxy, filename()), null);
  assert.equal(detect(mime(), proxy), null);
});

test("completed-download lookups can supply same-ID records after verified permissions", async () => {
  const queries = [], grants = [], onRemoved = eventSource();
  const downloads = { search(query) {
    queries.push(query);
    return Promise.resolve([{ id: query.id, state: "complete",
      mime: "application/pdf", filename: "/private/report.bin",
      url: "https://private.invalid/", cookies: "private", scanVerified: true }]);
  } };
  const permissions = { onRemoved,
    contains(query) { grants.push(query); return Promise.resolve(true); }
  };
  const completion = Object.freeze({ kind: "completed", id: 23 });
  const [declared, named] = await Promise.all([
    retrieveCompletedDownloadMime(downloads, permissions, completion),
    retrieveCompletedDownloadFilename(downloads, permissions, completion)
  ]);
  assert.deepEqual(queries, [{ id: 23 }, { id: 23 }]);
  assert.deepEqual(grants, [
    { permissions: ["downloads"] }, { permissions: ["downloads"] }
  ]);
  assert.deepEqual(detect(declared, named), {
    id: 23, isPdfCandidate: true, hasMisleadingExtension: true,
    evidence: "browser-pdf-mime", authorizesOpen: false
  });
  assert.equal(onRemoved.size, 0);
});

test("unavailable or revoked lookups never produce a misleading-PDF claim", async () => {
  const downloads = { search() { throw Error("should not query"); } };
  const permissions = { onRemoved: eventSource(),
    contains() { return Promise.resolve(false); }
  };
  const completion = Object.freeze({ kind: "completed", id: 7 });
  const [declared, named] = await Promise.all([
    retrieveCompletedDownloadMime(downloads, permissions, completion),
    retrieveCompletedDownloadFilename(downloads, permissions, completion)
  ]);
  assert.equal(declared, null);
  assert.equal(named, null);
  assert.equal(detect(declared, named), null);
  assert.equal(permissions.onRemoved.size, 0);
});

test("module never reads files, requests browser APIs or authorizes scanning and opening", async () => {
  const code = await readFile(new URL("../src/download-misleading-extension.js", import.meta.url),
    "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["globalThis.chrome", "browser.downloads",
    "downloads.search(", "permissions.request", "fetch(", "node:fs",
    "sendNativeMessage(", "nativeMessaging", "clamscan",
    "scan_and_open", "downloads.open("]) {
    assert.equal(code.includes(forbidden), false, forbidden);
  }
});
