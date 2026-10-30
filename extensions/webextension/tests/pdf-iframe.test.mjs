import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfIframe as detect } from "../src/pdf-iframe.js";

const none = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const yes = { isPdfCandidate: true, evidence: "iframe-src", authorizesOpen: false };
const iframe = (src, extra = {}) => ({ tagName: "IFRAME", src, ...extra });

test("identifies absolute and relative PDF iframe src paths, not query text", () => {
  for (const record of [
    iframe("https://example.test/report.pdf"),
    iframe("https://example.test/a/report.PDF?download=1#page=2"),
    iframe("/docs/report%2ePdF", { documentUrl: "https://example.test/portal" }),
    iframe("../file.pdf", { documentUrl: "https://example.test/account/index.html" }),
    iframe("//cdn.test/scan.pdf", { documentUrl: "https://example.test/view" }),
    { tagName: "iframe", src: "./report.pdf", documentUrl: "http://example.test/sub/" }
  ]) assert.deepEqual(detect(record), yes);

  for (const src of [
    "https://example.test/?file=report.pdf", "https://example.test/report.pdf.exe",
    "https://example.test/report.pdf/view", "https://example.test/.pdf",
    "https://example.test/report%2F.pdf", "https://example.test/report%00.pdf",
    "https://example.test/report%ZZ.pdf", "https://example.test/document.html#report.pdf",
    "data:application/pdf;base64,JVBERi0", "blob:https://example.test/file.pdf",
    "javascript:alert(1)", "file:///private/report.pdf", "ftp://test.invalid/file.pdf"
  ]) assert.deepEqual(detect(iframe(src)), none, src);
});

test("rejects srcdoc, non-iframe elements and unsafe or missing attributes", () => {
  for (const record of [
    iframe("https://example.test/report.pdf", { srcdoc: "" }),
    iframe("https://example.test/report.pdf", { srcdoc: "<p>HTML</p>" }),
    { tagName: "OBJECT", src: "https://example.test/report.pdf" },
    { tagName: "EMBED", src: "https://example.test/report.pdf" },
    { tagName: "iframe", src: "https://example.test/report.pdf", type: "application/pdf" },
    { tagName: "iframe", src: "https://example.test/report.pdf", html: "secret" },
    iframe("/report.pdf"), iframe(""), iframe("\n/report.pdf", { documentUrl: "https://example.test" }),
    iframe("/report.pdf", { documentUrl: "file:///private/page.html" }),
    iframe("/report.pdf", { documentUrl: "data:text/html,a" }),
    iframe("/report.pdf", { documentUrl: "not-a-url" }),
    iframe("/report.pdf", { documentUrl: "https://example.test/page", srcdoc: undefined }),
    iframe("x".repeat(8193) + ".pdf", { documentUrl: "https://example.test" }),
    iframe(123), { tagName: "iframe" }, {}, null, undefined, 1, [],
    new URL("https://example.test/report.pdf")
  ]) assert.deepEqual(detect(record), none);
});

test("does not consult getters, inherited properties, symbols or proxy traps", () => {
  let reads = 0;
  const getter = iframe("https://example.test/report.pdf");
  Object.defineProperty(getter, "src", { get() { reads++; return "https://example.test/report.pdf"; } });
  const inherited = Object.create({ tagName: "IFRAME" });
  inherited.src = "https://example.test/report.pdf";
  const symbol = iframe("https://example.test/report.pdf");
  symbol[Symbol("secret")] = "private";
  const proxy = new Proxy(iframe("https://example.test/report.pdf"), {
    getPrototypeOf() { throw Error("no access"); }
  });
  for (const record of [getter, inherited, symbol, proxy])
    assert.deepEqual(detect(record), none);
  assert.equal(reads, 0);
});

test("only returns frozen, privacy-safe metadata and never authorizes opening", () => {
  for (const record of [
    iframe("https://example.test/private.pdf?token=secret"),
    iframe("https://example.test/home.html"),
    iframe("/private.pdf", { documentUrl: "https://secret.example.test/page" })
  ]) {
    const result = detect(record);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("iframe detection remains passive and existing browser permissions unchanged", async () => {
  const [source, manifest, background] = await Promise.all([
    readFile(new URL("../src/pdf-iframe.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8"),
    readFile(new URL("../src/background.js", import.meta.url), "utf8")
  ]);
  const parsed = JSON.parse(manifest);
  assert.deepEqual(parsed.permissions, []);
  assert.deepEqual(parsed.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "querySelector(", "getElementsByTagName(", "contentDocument", "innerHTML",
    "chrome.", "browser.", "addListener(", "sendNativeMessage(",
    "connectNative(", "fetch(", "XMLHttpRequest", "window.open(",
    "downloads.open(", "node:fs", "scan-and-open"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
