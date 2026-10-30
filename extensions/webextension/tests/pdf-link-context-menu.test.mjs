import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  describePdfLinkContextMenu as describe,
  PDF_LINK_CONTEXT_MENU_ID,
  PDF_LINK_CONTEXT_MENU_LABEL
} from "../src/pdf-link-context-menu.js";

const event = (linkUrl, extra = {}) => ({ contexts: ["link"], linkUrl, ...extra });

test("describes a disabled Scan This PDF action for supported HTTP(S) links", () => {
  assert.equal(PDF_LINK_CONTEXT_MENU_ID, "scan-this-pdf-link");
  assert.equal(PDF_LINK_CONTEXT_MENU_LABEL, "Scan This PDF");
  for (const url of [
    "https://example.test/reports/statement.pdf",
    "http://example.test/report.PDF?download=1#page=2",
    "https://example.test/%72eport%2ePdF?name=secret",
    "https://example.test/report.pdf?redirect=https%3A%2F%2Fother.test"
  ]) {
    const result = describe(event(url));
    assert.deepEqual(result, {
      id: "scan-this-pdf-link", title: "Scan This PDF",
      contexts: ["link"], enabled: false, authorizesScan: false,
      authorizesOpen: false
    }, url);
    assert.equal(Object.isFrozen(result), true);
    assert.equal(Object.isFrozen(result.contexts), true);
  }
});

test("rejects misleading query-only PDF hints, double extensions, and malformed paths", () => {
  for (const url of [
    "https://example.test/index.html?file=report.pdf",
    "https://example.test/landing#report.pdf",
    "https://example.test/report.pdf.exe",
    "https://example.test/report.pdf/preview",
    "https://example.test/.pdf",
    "https://example.test/download?filename=report.pdf",
    "https://example.test/report%2F.pdf",
    "https://example.test/report%5C.pdf",
    "https://example.test/report%00.pdf",
    "https://example.test/report%ZZ.pdf",
    "https://example.test/"
  ]) assert.equal(describe(event(url)), null, url);
});

test("requires link context, not page, media or selection contexts", () => {
  for (const contexts of [
    ["page"], ["image"], ["video"], ["selection"],
    ["editable"], [], ["page", "selection"], ["link", "link"], Array(2)
  ]) assert.equal(describe(event("https://example.test/report.pdf", { contexts })), null);
  assert.ok(describe(event("https://example.test/report.pdf", {
    contexts: ["page", "link"]
  })));
});

test("rejects unsupported schemes, credentials and invalid link metadata", () => {
  for (const url of [
    "file:///Users/private/report.pdf",
    "ftp://example.test/report.pdf",
    "blob:https://example.test/report.pdf",
    "data:application/pdf,report.pdf",
    "javascript:alert('report.pdf')",
    "chrome-extension://abc/report.pdf",
    "https://name:secret@example.test/report.pdf",
    "https://example.test/report.pdf\n",
    "https://example.test/report.pdf\t",
    "https://example.test/" + "x".repeat(8193) + ".pdf",
    "/report.pdf", "not a URL"
  ]) assert.equal(describe(event(url)), null);
  for (const linkUrl of [null, undefined, 0, {}, new URL("https://example.test/report.pdf")]) {
    assert.equal(describe(event(linkUrl)), null);
  }
});

test("does not invoke browser-event getters or accept inherited metadata", () => {
  let called = 0;
  const withGetter = event("https://example.test/report.pdf");
  Object.defineProperty(withGetter, "linkUrl", {
    get() { called++; return "https://example.test/report.pdf"; }
  });
  assert.equal(describe(withGetter), null);
  const contexts = ["link"];
  Object.defineProperty(contexts, "0", { get() { called++; return "link"; } });
  assert.equal(describe(event("https://example.test/report.pdf", { contexts })), null);
  const inherited = Object.create(event("https://example.test/report.pdf"));
  assert.equal(describe(inherited), null);
  assert.equal(describe(new Proxy({}, {
    getPrototypeOf() { throw Error("secret"); }
  })), null);
  for (const value of [null, undefined, 4, [], new Date(), "link"]) {
    assert.equal(describe(value), null);
  }
  assert.equal(called, 0);
});

test("never returns a private URL, scanner verdict, or opening grant", () => {
  const result = describe(event("https://private.test/secret.pdf?token=private"));
  assert.ok(result);
  const serialized = JSON.stringify(result);
  for (const word of ["private", "secret", "token", "https://"]) {
    assert.equal(serialized.includes(word), false);
  }
  assert.equal(result.enabled, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
});

test("retains inert background, permissions, and dedicated CI validation", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, manifestText, worker, ci] = await Promise.all([
    read("../src/pdf-link-context-menu.js"),
    read("../manifest.json"),
    read("../src/background.js"),
    read("../../../.github/workflows/ci.yml")
  ]);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.equal(worker.trimEnd(), [
    "// Inactive shared WebExtensions background entry point.",
    "// Do not listen for messages, inspect PDFs or request native access here.",
    "void 0;"
  ].join("\n"));
  assert.match(ci, /node --test tests\/pdf-link-context-menu\.test\.mjs/);
  for (const forbidden of [
    "contextMenus.create(", "addListener(", "permissions.request(",
    "fetch(", "XMLHttpRequest", "sendNativeMessage(", "connectNative(",
    "downloads.open(", "window.open(", "scan-and-open", "clamscan(",
    "console.", "node:fs"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
