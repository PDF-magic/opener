import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfNavigation } from "../src/pdf-navigation.js";

const none = {
  isPdfCandidate: false, evidence: "none", authorizesOpen: false
};
const match = {
  isPdfCandidate: true, evidence: "url-path", authorizesOpen: false
};
const navigate = (url, extra = {}) =>
  detectPdfNavigation({ tabId: 7, frameId: 0, url, ...extra });

test("identifies top-level PDF URL-path navigations without fetching the URL", () => {
  for (const url of [
    "https://example.test/document.pdf",
    "http://example.test/path/financial.report.PDF",
    "https://example.test/a/report.pdf?download=1#page=3",
    "https://example.test/a/%72eport%2ePdF?name=other.txt",
    "file:///Users/example/Downloads/report.pdf"
  ]) {
    assert.deepEqual(navigate(url), match, url);
  }
  assert.deepEqual(navigate("https://example.test/file.pdf", {
    timeStamp: 1234, transitionType: "link", mimeType: "text/html",
    filename: "not-a-pdf.txt", authorizesOpen: true
  }), match);
});

test("rejects misleading suffixes, queries, fragments and unsupported schemes", () => {
  for (const url of [
    "https://example.test/report.pdf.exe",
    "https://example.test/report.pdf/preview",
    "https://example.test/view?file=report.pdf",
    "https://example.test/index.html#report.pdf",
    "https://example.test/report%2F.pdf",
    "https://example.test/report%5C.pdf",
    "https://example.test/report%00.pdf",
    "https://example.test/report%ZZ.pdf",
    "https://example.test/.pdf",
    "https://example.test/",
    "data:application/pdf,base64",
    "blob:https://example.test/report.pdf",
    "javascript:alert('report.pdf')",
    "ftp://example.test/report.pdf",
    "chrome-extension://abc/report.pdf"
  ]) assert.deepEqual(navigate(url), none, url);
});

test("only valid top-frame tab navigation events can be candidates", () => {
  for (const options of [
    { frameId: 1 }, { frameId: -1 }, { frameId: undefined },
    { frameId: "0" }, { tabId: -1 }, { tabId: undefined },
    { tabId: 1.5 }, { tabId: "7" }, { tabId: Number.MAX_SAFE_INTEGER + 1 }
  ]) assert.deepEqual(navigate("https://example.test/report.pdf", options), none);

  assert.deepEqual(detectPdfNavigation({ url: "https://example.test/file.pdf" }), none);
  assert.deepEqual(detectPdfNavigation("https://example.test/file.pdf"), none);
  assert.deepEqual(detectPdfNavigation({ tabId: 1, frameId: 0, url: 3 }), none);
});

test("malformed browser events and inherited or accessor values fail closed", () => {
  const getter = Object.create(null);
  Object.defineProperty(getter, "url", { get() { throw Error("must not run"); } });
  getter.tabId = 3;
  getter.frameId = 0;
  const inherited = Object.create({ url: "https://example.test/file.pdf" });
  inherited.tabId = 3;
  inherited.frameId = 0;
  for (const details of [
    undefined, null, [], 42, getter, inherited,
    new URL("https://example.test/file.pdf"),
    new Proxy({}, { getPrototypeOf() { throw Error("must not escape"); } }),
    { tabId: 1, frameId: 0, url: "https://example.test/a".repeat(8193) + ".pdf" }
  ]) assert.deepEqual(detectPdfNavigation(details), none);
});

test("returns only immutable, URL-free candidate flags and never opening approval", () => {
  for (const url of [
    "https://user:password@example.test/private.pdf?token=secret",
    "https://example.test/not-a-pdf"
  ]) {
    const result = navigate(url);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("secret"), false);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes("password"), false);
  }
});

test("navigation detection is passive and CI does not activate browser interception", async () => {
  const load = (path) => readFile(new URL(path, import.meta.url), "utf8");
  const [source, background, manifestSource, safariSource, ci] = await Promise.all([
    load("../src/pdf-navigation.js"),
    load("../src/background.js"),
    load("../manifest.json"),
    load("../../safari/manifest.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  for (const forbidden of [
    "addListener(", "permissions.request", "connectNative", "sendNativeMessage",
    "window.open", "downloads.open", "fetch(", "XMLHttpRequest", "WebSocket",
    "node:fs", "scan-and-open", "ClamAV", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  const manifest = JSON.parse(manifestSource);
  const safari = JSON.parse(safariSource);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.equal(manifest.permissions.includes("webNavigation"), false);
  assert.match(ci, /node --test tests\/pdf-navigation\.test\.mjs/);
});
