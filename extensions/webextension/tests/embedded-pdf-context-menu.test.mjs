import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  EMBEDDED_PDF_MENU_ID, EMBEDDED_PDF_MENU_TITLE,
  EMBEDDED_PDF_UNAVAILABLE_MESSAGE, embeddedPdfContextMenuState as state,
  activateEmbeddedPdfContextMenu as activate
} from "../src/embedded-pdf-context-menu.js";

const iframe = (src, more = {}) => ({
  source: "iframe", tabId: 17, frameId: 2,
  element: { tagName: "IFRAME", src, ...more }
});
const embed = (src, more = {}) => ({
  source: "embed", tabId: 17, frameId: 0,
  element: { tagName: "EMBED", src, ...more }
});

test("describes a distinct disabled Scan This Embedded PDF context action", () => {
  assert.equal(EMBEDDED_PDF_MENU_ID, "scan-supported-embedded-pdf");
  assert.equal(EMBEDDED_PDF_MENU_TITLE, "Scan This Embedded PDF");
  assert.match(EMBEDDED_PDF_UNAVAILABLE_MESSAGE, /verified native scanner/);
  const result = state(iframe("https://example.test/doc.pdf"));
  assert.deepEqual(result, {
    menuItemId: EMBEDDED_PDF_MENU_ID, title: EMBEDDED_PDF_MENU_TITLE,
    supported: true, enabled: false, evidence: "iframe-src",
    unavailableMessage: EMBEDDED_PDF_UNAVAILABLE_MESSAGE,
    authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
});

test("recognizes only supported iframe PDF sources in a non-top frame", () => {
  for (const metadata of [
    iframe("https://example.test/statement.pdf"),
    iframe("/reports/statement.PDF?dl=1#page=2",
      { documentUrl: "https://example.test/portal" }),
    iframe("../report%2epdf", { documentUrl: "https://example.test/page/index.html" })
  ]) assert.equal(state(metadata).evidence, "iframe-src");
  for (const metadata of [
    iframe("https://example.test/index.html?file=report.pdf"),
    iframe("https://example.test/report.pdf.exe"),
    iframe("blob:https://example.test/id"),
    iframe("data:application/pdf,abc"),
    iframe("javascript:alert(1)"),
    iframe("file:///private/report.pdf"),
    iframe("https://example.test/report.pdf", { srcdoc: "" }),
    { ...iframe("https://example.test/report.pdf"), frameId: 0 },
    { ...iframe("https://example.test/report.pdf"), frameId: -1 },
    { ...iframe("https://example.test/report.pdf"), frameId: "2" }
  ]) assert.equal(state(metadata).supported, false);
});

test("recognizes supported embed PDFs, including declared PDF type", () => {
  for (const metadata of [
    embed("https://example.test/document.pdf"),
    embed("https://example.test/download", { type: "application/pdf" }),
    embed("../docs/statement.PDF", { baseUrl: "https://example.test/view/page.html" })
  ]) {
    const result = state(metadata);
    assert.equal(result.supported, true);
    assert.equal(result.evidence, "embed-element");
    assert.equal(result.enabled, false);
  }
  for (const metadata of [
    embed("https://example.test/document.pdf", { type: "text/html" }),
    embed("https://example.test/report.pdf.js"),
    embed("https://example.test/report.pdf", { type: "image/png" }),
    embed("https://user:secret@example.test/report.pdf"),
    embed("blob:https://example.test/id", { type: "application/pdf" }),
    embed("data:application/pdf,secret"),
    embed("file:///tmp/statement.pdf")
  ]) assert.equal(state(metadata).supported, false);
});

test("rejects arbitrary links, object elements and mislabeled contexts", () => {
  for (const record of [
    { ...iframe("https://example.test/doc.pdf"), source: "link" },
    { ...iframe("https://example.test/doc.pdf"), source: "embed" },
    { ...embed("https://example.test/doc.pdf"), source: "iframe", frameId: 2 },
    { ...embed("https://example.test/doc.pdf"), source: "object" },
    { ...embed("https://example.test/doc.pdf"), tabId: -1 },
    { ...embed("https://example.test/doc.pdf"), tabId: "17" },
    { ...embed("https://example.test/doc.pdf"), frameId: 1.5 },
    { ...embed("https://example.test/doc.pdf"), element: {
      tagName: "OBJECT", data: "https://example.test/doc.pdf", type: "application/pdf"
    } }
  ]) assert.equal(state(record).supported, false);
});

test("rejects extra fields, accessors, inherited data and proxy traps", () => {
  let getterReads = 0;
  const getter = iframe("https://example.test/doc.pdf");
  Object.defineProperty(getter, "element", { get() {
    getterReads++;
    throw Error("private URL");
  } });
  const inherited = Object.create(iframe("https://example.test/doc.pdf"));
  const symbol = iframe("https://example.test/doc.pdf");
  symbol[Symbol("private")] = "sensitive";
  const proxy = new Proxy(iframe("https://example.test/doc.pdf"), {
    getPrototypeOf() { throw Error("private"); }
  });
  for (const record of [
    null, undefined, 5, [], "", getter, inherited, symbol, proxy,
    { ...embed("https://example.test/doc.pdf"), browserMessage: "trusted" },
    { ...iframe("https://example.test/doc.pdf"), documentHtml: "secret" }
  ]) assert.equal(state(record).supported, false);
  assert.equal(getterReads, 0);
});

test("click requests remain unavailable without reviewed native integration", () => {
  const yes = iframe("https://example.test/private.pdf?token=secret");
  const no = iframe("https://example.test/preview.html");
  for (const value of [undefined, false, "true", 1, null]) {
    assert.deepEqual(activate(yes, value), {
      status: "not-requested", scanVerified: false, authorizesScan: false,
      authorizesOpen: false
    });
  }
  assert.deepEqual(activate(yes, true), {
    status: "unavailable", scanVerified: false, authorizesScan: false,
    authorizesOpen: false
  });
  assert.deepEqual(activate(no, true), {
    status: "unsupported", scanVerified: false, authorizesScan: false,
    authorizesOpen: false
  });
});

test("menu states never expose private PDF URLs or scanner authorization", () => {
  for (const record of [
    iframe("https://example.test/private.pdf?token=secret"),
    embed("https://example.test/private.pdf?token=secret"),
    embed("https://example.test/private.txt")
  ]) {
    for (const result of [state(record), activate(record, true)]) {
      assert.equal(Object.isFrozen(result), true);
      assert.equal(result.authorizesScan, false);
      assert.equal(result.authorizesOpen, false);
      assert.doesNotMatch(JSON.stringify(result), /private|secret|example|token/);
    }
  }
});

test("context-menu contract does not register browser menus or weaken scan gates", async () => {
  const load = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifestJson, safariJson, background, pkg, ci] = await Promise.all([
    load("../src/embedded-pdf-context-menu.js"),
    load("../manifest.json"),
    load("../../safari/manifest.json"),
    load("../src/background.js"),
    load("../package.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  const manifest = JSON.parse(manifestJson);
  const safari = JSON.parse(safariJson);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(manifest.incognito, "not_allowed");
  assert.deepEqual(safari.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(pkg).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const forbidden of [
    "chrome.", "browser.", "contextMenus.create", "addListener(",
    "sendNativeMessage(", "connectNative(", "fetch(", "XMLHttpRequest",
    "WebSocket", "window.open(", "downloads.open(", "node:fs",
    "scan-and-open", "clamscan(", "document.", "querySelector("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
