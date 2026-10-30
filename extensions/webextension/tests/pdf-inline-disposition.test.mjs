import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectInlinePdfResponse as detect } from "../src/pdf-inline-disposition.js";

const none = Object.freeze({
  isInlineResponse: false, isPdfCandidate: false,
  evidence: "none", authorizesOpen: false
});
const inline = Object.freeze({
  isInlineResponse: true, isPdfCandidate: false,
  evidence: "content-disposition", authorizesOpen: false
});
const pdf = Object.freeze({
  isInlineResponse: true, isPdfCandidate: true,
  evidence: "content-disposition+mime-type", authorizesOpen: false
});
const response = (metadata = {}) =>
  detect({ type: "main_frame", frameId: 0, tabId: 8, ...metadata });
const header = (name, value) => ({ name, value });

test("detects inline response headers alongside independent PDF MIME evidence", () => {
  for (const disposition of [
    "inline", "INLINE", " Inline ", 'inline; filename="example.pdf"',
    'inline; filename="a;b.pdf"',
    'inline; filename="escaped \\" quote.pdf"',
    "inline; filename*=UTF-8''report.pdf",
    "inline; filename=test.pdf; size=33"
  ]) {
    assert.deepEqual(response({ responseHeaders: [
      header("Content-Disposition", disposition),
      header("Content-Type", "application/pdf")
    ] }), pdf);
    assert.deepEqual(response({ contentDisposition: disposition,
      mimeType: "application/x-pdf" }), pdf);
  }
  assert.deepEqual(response({ responseHeaders: [
    header("Server", "private"),
    header("content-disposition", "inline"),
    header("CONTENT-TYPE", "application/pdf; charset=UTF-8")
  ] }), pdf);
});

test("inline is observable without proving PDF content", () => {
  assert.deepEqual(response({ responseHeaders: [
    header("Content-Disposition", "inline")
  ] }), inline);
  assert.deepEqual(response({ contentDisposition: "inline" }), inline);
  for (const mimeType of ["text/html", "image/png", "application/octet-stream"]) {
    assert.deepEqual(response({ contentDisposition: "inline", mimeType }), inline);
  }
  assert.deepEqual(response({ contentDisposition: "inline",
    mimeType: "text/html", url: "https://private.test/report.pdf" }), inline);
  assert.deepEqual(response({ contentDisposition: "inline",
    responseHeaders: [header("Content-Type", "application/pdf")] }), pdf);
  assert.deepEqual(response({ contentDisposition: "inline",
    responseHeaders: [header("Content-Type", "text/html")] }), inline);
});

test("attachment, absent and unsupported dispositions fail closed", () => {
  for (const value of [
    undefined, "", "attachment", "ATTACHMENT; filename=x.pdf",
    "form-data", "inline-attachment", "inlinex", "xinline",
    "attachment, inline", "inline, attachment",
    "inline; broken", "inline; filename=", "inline; =value",
    "inline; filename=\"missing", "inline; filename=unquoted space",
    "inline; filename=a; filename=b", "inline; filename=a;",
    "inline; filename=a\r\nX-Secret: leak", "inline\n",
    "inline\t; filename=a", 3, null, {}
  ]) {
    assert.deepEqual(response({ contentDisposition: value,
      mimeType: "application/pdf" }), none);
  }
  assert.deepEqual(response({ mimeType: "application/pdf" }), none);
  assert.deepEqual(response({ responseHeaders: [
    header("Content-Type", "application/pdf")
  ] }), none);
});

test("rejects duplicate, inconsistent and structurally invalid headers", () => {
  const valid = header("Content-Disposition", "inline");
  for (const metadata of [
    { responseHeaders: [valid, header("content-disposition", "inline")] },
    { responseHeaders: [valid, header("content-disposition", "attachment")] },
    { responseHeaders: [header("Content-Disposition", "attachment")],
      contentDisposition: "inline" },
    { responseHeaders: [valid], contentDisposition: "attachment" },
    { responseHeaders: null }, { responseHeaders: "inline" },
    { responseHeaders: Array(2) },
    { responseHeaders: Array.from({ length: 129 }, () => ({ name: "Other" })) },
    { responseHeaders: [header("Content-Disposition", 123)] },
    { responseHeaders: [{ name: "Content-Disposition", binaryValue: [1] }] },
    { responseHeaders: [{ value: "inline" }] }
  ]) assert.deepEqual(response({ mimeType: "application/pdf", ...metadata }), none);
});

test("MIME ambiguity never upgrades inline observation to a PDF candidate", () => {
  for (const metadata of [
    { mimeType: "text/html", responseHeaders: [
      header("Content-Disposition", "inline"),
      header("Content-Type", "application/pdf")
    ] },
    { responseHeaders: [
      header("Content-Disposition", "inline"),
      header("Content-Type", "application/pdf"),
      header("Content-Type", "application/pdf")
    ] },
    { responseHeaders: [
      header("Content-Disposition", "inline"),
      header("Content-Type", "application/pdf\r\nsecret: x")
    ] }
  ]) assert.deepEqual(response(metadata), inline);
});

test("requires browser-provided top-frame context", () => {
  for (const patch of [
    { type: "sub_frame" }, { type: "xmlhttprequest" },
    { frameId: 1 }, { frameId: null }, { tabId: -1 },
    { tabId: 4.5 }, { tabId: "8" }, { tabId: Number.MAX_SAFE_INTEGER + 1 }
  ]) assert.deepEqual(response({
    contentDisposition: "inline", mimeType: "application/pdf", ...patch
  }), none);
  for (const event of [null, undefined, [], new Date(), {},
    { contentDisposition: "inline", mimeType: "application/pdf" }]) {
    assert.deepEqual(detect(event), none);
  }
});

test("never calls getters, returns private information or authorizes opening", () => {
  let getters = 0;
  const event = { type: "main_frame", frameId: 0, tabId: 8 };
  Object.defineProperty(event, "contentDisposition", {
    get() { getters++; return "inline"; }
  });
  assert.deepEqual(detect(event), none);
  const badHeader = { name: "Content-Disposition" };
  Object.defineProperty(badHeader, "value", {
    get() { getters++; return "inline"; }
  });
  assert.deepEqual(response({ responseHeaders: [badHeader] }), none);
  assert.deepEqual(response({ responseHeaders: new Proxy([], {
    getPrototypeOf() { throw Error("private header"); }
  }) }), none);
  assert.equal(getters, 0);
  for (const metadata of [
    { contentDisposition: 'inline; filename="private-statement.pdf"',
      mimeType: "application/pdf", url: "https://private.invalid/secret" },
    { contentDisposition: "attachment", mimeType: "application/pdf" }
  ]) {
    const result = response(metadata);
    assert.equal(Object.isFrozen(result), true);
    assert.equal(result.authorizesOpen, false);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isInlineResponse", "isPdfCandidate"]);
    assert.equal(JSON.stringify(result).includes("private"), false);
  }
});

test("extension privileges and scanner safety remain unchanged", async () => {
  const [source, background, manifest] = await Promise.all([
    readFile(new URL("../src/pdf-inline-disposition.js", import.meta.url), "utf8"),
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8")
  ]);
  assert.equal(background.trim(), [
    "// Inactive shared WebExtensions background entry point.",
    "// Do not listen for messages, inspect PDFs or request native access here.",
    "void 0;"
  ].join("\n"));
  const permissions = JSON.parse(manifest);
  assert.deepEqual(permissions.permissions, []);
  assert.deepEqual(permissions.host_permissions, []);
  for (const forbidden of ["addListener(", "sendNativeMessage(", "connectNative(",
    "fetch(", "XMLHttpRequest", "window.open(", "requestPermission(",
    "downloads.open(", "scan-and-open", "clamscan("]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
