import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectAttachmentResponse as detect } from "../src/pdf-response-attachment.js";

const NONE = { isAttachmentResponse: false, evidence: "none", authorizesOpen: false };
const YES = { isAttachmentResponse: true, evidence: "content-disposition", authorizesOpen: false };
const header = (value) => [{ name: "Content-Disposition", value }];
const response = (metadata = {}) =>
  detect({ tabId: 5, frameId: 0, type: "main_frame", ...metadata });

test("recognizes explicit attachment dispositions in observable main-frame headers", () => {
  for (const disposition of [
    "attachment", "ATTACHMENT", " attachment \t",
    'attachment; filename="report.pdf"',
    "attachment; filename=report.pdf",
    "Attachment; filename*=UTF-8''report%20final.pdf",
    'attachment; filename="report; private.pdf"; size=25',
    'attachment; filename="report\\\"final.pdf"'
  ]) {
    assert.deepEqual(response({ responseHeaders: header(disposition) }), YES, disposition);
  }
  assert.deepEqual(response({ responseHeaders: [
    { name: "Server", value: "private" },
    { name: "content-disposition", value: "attachment; filename=report.pdf" }
  ] }), YES);
});

test("inline, absent and nonattachment declarations are not attachment evidence", () => {
  for (const metadata of [
    {}, { responseHeaders: [] }, { responseHeaders: [{ name: "X-Disposition", value: "attachment" }] },
    { responseHeaders: header("inline; filename=report.pdf") },
    { responseHeaders: header("form-data; name=file") },
    { responseHeaders: header("attachment-not") },
    { responseHeaders: header("attachmentFake") },
    { responseHeaders: header("attachment",), mimeType: "application/pdf", frameId: 1 },
    { url: "https://private.test/attachment.pdf", mimeType: "application/pdf" },
    { filename: "attachment.pdf", mimeType: "application/pdf" }
  ]) assert.deepEqual(response(metadata), NONE);
});

test("rejects duplicate, malformed, injected and oversized attachment headers", () => {
  for (const headers of [
    [...header("attachment"), ...header("inline")],
    [...header("attachment"), ...header("attachment")],
    header("attachment;"), header("attachment; filename"),
    header("attachment; filename="), header("attachment; filename=one two"),
    header('attachment; filename="unclosed'),
    header('attachment; filename="file.pdf" garbage'),
    header("attachment; filename=a; FILENAME=b"),
    header("attachment; filename=a;; size=1"),
    header("attachment\r\nX-Secret: true"), header("attachment\u0000"),
    header("attachment" + " ".repeat(4096)),
    [{ name: "Content-Disposition", binaryValue: [1, 2] }],
    [{ name: "Content-Disposition", value: 42 }],
    [{ name: "Content-Disposition ", value: "attachment" }],
    [{ name: "Content-Disposition\nX-Foo", value: "attachment" }],
    Array(2), Array.from({ length: 129 }, () => ({ name: "X-Other" }))
  ]) assert.deepEqual(response({ responseHeaders: headers }), NONE);
  for (const responseHeaders of [null, undefined, "attachment", {}]) {
    assert.deepEqual(response({ responseHeaders }), NONE);
  }
});

test("only valid trusted browser main-frame response context can be classified", () => {
  for (const patch of [
    { type: "sub_frame" }, { type: "xmlhttprequest" }, { type: undefined },
    { frameId: 1 }, { frameId: -1 }, { frameId: "0" }, { frameId: null },
    { tabId: -1 }, { tabId: 2.5 }, { tabId: "5" }, { tabId: Number.MAX_SAFE_INTEGER + 1 }
  ]) assert.deepEqual(response({ responseHeaders: header("attachment"), ...patch }), NONE);
  for (const event of [null, undefined, [], 1, "attachment", new Date(),
    { responseHeaders: header("attachment") }]) assert.deepEqual(detect(event), NONE);
});

test("ignores getters and proxy traps without leaking response metadata", () => {
  let called = 0;
  const accessorHeader = { name: "Content-Disposition" };
  Object.defineProperty(accessorHeader, "value", { get() { called++; return "attachment"; } });
  assert.deepEqual(response({ responseHeaders: [accessorHeader] }), NONE);
  const accessorEvent = { type: "main_frame", frameId: 0, tabId: 5 };
  Object.defineProperty(accessorEvent, "responseHeaders", {
    get() { called++; return header("attachment"); }
  });
  assert.deepEqual(detect(accessorEvent), NONE);
  assert.deepEqual(detect(Object.create({
    type: "main_frame", frameId: 0, tabId: 5, responseHeaders: header("attachment")
  })), NONE);
  assert.deepEqual(detect(new Proxy({}, {
    getPrototypeOf() { throw Error("secret private navigation"); }
  })), NONE);
  assert.equal(called, 0);
});

test("returns frozen flags without URLs, filenames, MIME identity or opening grants", () => {
  for (const metadata of [
    { responseHeaders: header('attachment; filename="secret.pdf"'),
      url: "https://private.test/secret.pdf", mimeType: "text/plain" },
    { responseHeaders: header("inline; filename=secret.pdf") }
  ]) {
    const result = response(metadata);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isAttachmentResponse"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("secret"), false);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal("isPdfCandidate" in result, false);
  }
});

test("remains passive with no permission or scanner change and a dedicated CI test", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, ci, manifestText, background] = await Promise.all([
    read("../src/pdf-response-attachment.js"),
    read("../../../.github/workflows/ci.yml"),
    read("../manifest.json"),
    read("../src/background.js")
  ]);
  assert.match(ci, /node --test tests\/pdf-response-attachment\.test\.mjs/);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  for (const forbidden of [
    "addListener(", "permissions.request", "sendNativeMessage", "connectNative(",
    "fetch(", "XMLHttpRequest", "WebSocket", "window.open", "downloads.open",
    "scan-and-open", "clamscan(", "node:fs", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
