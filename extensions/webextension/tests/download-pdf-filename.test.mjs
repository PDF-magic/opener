import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectCompletedPdfFilename as detect } from "../src/download-pdf-filename.js";

const record = (filename, id = 7) => Object.freeze({ id, filename });
const expected = (id, isPdfFilename) => ({ id, isPdfFilename, authorizesOpen: false });

test("recognizes case-insensitive .pdf suffixes for downloaded filenames", () => {
  for (const filename of ["report.pdf", "report.PDF", "archive.final.PdF", "a.pdf"]) {
    assert.deepEqual(detect(record(filename)), expected(7, true), filename);
  }
});

test("recognizes final filename components in POSIX, Windows and UNC paths", () => {
  for (const filename of [
    "/Users/example/Downloads/report.pdf", "/var/tmp/my notes.PDF",
    "C:\\Users\\example\\Downloads\\report.pdf", "C:/Users/example/report.PDF",
    "\\\\fileserver\\share\\contract.final.pdf", "folder\\report.pdf"
  ]) assert.deepEqual(detect(record(filename, 0)), expected(0, true), filename);
});

test("does not confuse .pdf directory names, extensions, queries or suffixes", () => {
  for (const filename of [
    "report.pdf.exe", "report.pdf.download", "report.pdf ", "report.pdf.",
    "/tmp/report.pdf/preview.txt", "C:\\reports.pdf\\invoice.docx",
    "report.pdf/", "C:\\reports\\", ".pdf", "a/.pdf",
    "report.pdf?download=1", "report.pdf#page=2", "report%2Epdf", "report-pdf"
  ]) assert.deepEqual(detect(record(filename)), expected(7, false), filename);
});

test("never treats arbitrary URLs as downloaded filenames", () => {
  for (const filename of ["https://private.example/report.pdf", "file:///private/report.pdf",
    "ftp://files.example/report.pdf", "blob:https://example/test.pdf"]) {
    assert.equal(detect(record(filename)), null, filename);
  }
});

test("rejects malformed, too-long and control-character paths", () => {
  for (const filename of ["", "name\u0000.pdf", "name\n.pdf", "x".repeat(4097) + ".pdf", 4, null]) {
    assert.equal(detect(record(filename)), null);
  }
  assert.deepEqual(detect(record("x".repeat(513) + ".pdf")), expected(7, false));
  assert.deepEqual(detect(record("/")), expected(7, false));
});

test("rejects incomplete, forged, extra-field and invalid-ID records", () => {
  for (const data of [
    null, undefined, "report.pdf", [], 3, {}, { filename: "a.pdf" },
    { id: 7 }, { id: -1, filename: "a.pdf" },
    { id: "7", filename: "a.pdf" }, { id: 1.4, filename: "a.pdf" },
    { id: Number.MAX_SAFE_INTEGER + 1, filename: "a.pdf" },
    { id: 7, filename: "a.pdf", authorizesOpen: true },
    { id: 7, filename: "a.pdf", mime: "application/pdf" },
    Object.assign(Object.create({ id: 7 }), { filename: "a.pdf" })
  ]) assert.equal(detect(data), null);
});

test("never invokes hostile record getters or symbols", () => {
  let read = 0;
  const getter = { id: 7 };
  Object.defineProperty(getter, "filename", { get() { read++; throw Error("private file path"); } });
  const symbol = { id: 7, filename: "report.pdf" };
  symbol[Symbol("secret")] = "private";
  const proxy = new Proxy({ id: 7, filename: "report.pdf" }, {
    ownKeys() { throw Error("private path"); }
  });
  for (const input of [getter, symbol, proxy]) assert.equal(detect(input), null);
  assert.equal(read, 0);
});

test("returns path-free frozen classification and cannot authorize opening", () => {
  for (const filename of ["/private/confidential.pdf", "/private/confidential.exe"]) {
    const original = record(filename);
    const outcome = detect(original);
    assert.equal(Object.isFrozen(outcome), true);
    assert.deepEqual(Object.keys(outcome).sort(), ["authorizesOpen", "id", "isPdfFilename"]);
    assert.equal(outcome.authorizesOpen, false);
    assert.equal(JSON.stringify(outcome).includes("private"), false);
    assert.equal(original.filename, filename);
  }
});

test("does not enable permissions, native messaging, scanning or background access", async () => {
  const source = await readFile(new URL("../src/download-pdf-filename.js", import.meta.url), "utf8");
  for (const forbidden of ["fetch(", "node:fs", "chrome.", "browser.", "sendNativeMessage(",
    "nativeMessaging", "scan_and_open", "clamscan", "downloads.open(", "localStorage"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
