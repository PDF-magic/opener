import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  detectPdfCandidate, recognizeUnsupportedDataUrl
} from "../src/pdf-detection.js";

const unsupported = {
  isUnsupportedDataUrl: true, reason: "data-url-unsupported", authorizesOpen: false
};
const notDataUrl = {
  isUnsupportedDataUrl: false, reason: "none", authorizesOpen: false
};
const noCandidate = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };

test("recognizes unsupported PDF, generic and malformed data URL forms without inspecting payloads", () => {
  for (const url of [
    "data:application/pdf;base64,JVBERi0xLjQ=",
    "DATA:APPLICATION/PDF,%25PDF-1.7",
    "data:application/x-pdf,private-content",
    "data:;base64,JVBERi0xLjQ=",
    "data:text/plain,report.pdf",
    "data:application/pdf",
    "data:",
    "data:application/pdf;base64," + "A".repeat(1024 * 1024)
  ]) {
    const result = recognizeUnsupportedDataUrl(url);
    assert.deepEqual(result, unsupported);
    assert.equal(Object.isFrozen(result), true);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("JVBER"), false);
  }
});

test("does not confuse paths, query strings, non-data schemes or malformed values with data URLs", () => {
  for (const url of [
    "https://example.test/report.pdf?src=data:application/pdf",
    "file:///home/example/report.pdf",
    "blob:https://example.test/file.pdf",
    "javascript:data:application/pdf",
    "https://example.test/data:application/pdf",
    "data%3Aapplication/pdf,anything",
    " data:application/pdf,anything",
    "data :application/pdf,anything",
    "", null, undefined, 42, {}, new URL("data:application/pdf,anything"),
    new Proxy({}, { get() { throw Error("should not access properties"); } })
  ]) assert.deepEqual(recognizeUnsupportedDataUrl(url), notDataUrl);
});

test("an unsupported data URL cannot become a candidate from MIME or filename hints", () => {
  for (const url of [
    "data:application/pdf;base64,JVBERi0xLjQ=",
    "DATA:application/pdf,%PDF-1.7",
    "data:text/plain,document.pdf",
    "data:application/pdf,",
    "data:application/pdf;base64," + "A".repeat(8193)
  ]) {
    for (const metadata of [
      { url },
      { url, mimeType: "application/pdf" },
      { url, mimeType: "application/x-pdf", filename: "report.pdf" },
      { url, mimeType: "application/octet-stream", filename: "report.pdf" },
      { url, filename: "report.pdf" }
    ]) assert.deepEqual(detectPdfCandidate(metadata), noCandidate);
  }
  assert.deepEqual(detectPdfCandidate({ url: "https://example.test/report.pdf", mimeType: "application/pdf" }),
    { isPdfCandidate: true, evidence: "mime-type", authorizesOpen: false });
});

test("URL accessors and invalid metadata cannot influence candidate detection", () => {
  let getterCalls = 0;
  const malicious = { mimeType: "application/pdf" };
  Object.defineProperty(malicious, "url", { get() {
    getterCalls++;
    return "data:application/pdf,secret";
  } });
  assert.deepEqual(detectPdfCandidate(malicious), noCandidate);
  assert.equal(getterCalls, 0);
});

test("data URL detection is passive, private and never activates browser interception", async () => {
  const source = await readFile(new URL("../src/pdf-detection.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "addListener(", "sendNativeMessage", "connectNative",
    "fetch(", "XMLHttpRequest", "WebSocket", "window.open", "downloads.open",
    "scan-and-open", "node:fs", "ClamAV", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
