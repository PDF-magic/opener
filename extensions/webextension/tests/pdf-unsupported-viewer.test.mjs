import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { assessUnsupportedPdfViewer as assess } from "../src/pdf-unsupported-viewer.js";
import {
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX
} from "../src/automatic-interception-capability-matrix.js";

const chromium = "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html";
const firefox = "resource://pdf.js/web/viewer.html";
const pdfjs = "https://reader.example/pdfjs/web/viewer.html?file=%2Freport.pdf";
const context = (url = chromium, patch = {}) => ({
  tabId: 14, frameId: 0, url,
  viewerKind: "browser-owned", trustedBrowserEvent: true, ...patch
});

function safe(report) {
  assert.ok(Object.isFrozen(report));
  for (const field of [
    "browserPreviewBlocked", "interceptionVerified", "pdfBytesVerified",
    "scanVerified", "mayRedirectToHoldingScreen", "mayFetchViewerDocument",
    "mayInitiateAutomaticScan", "mayAutomaticallyOpen",
    "authorizesScan", "authorizesOpen"
  ]) assert.equal(report[field], false, field);
  assert.doesNotMatch(JSON.stringify(report),
    /reader\.example|secret|report\.pdf|mhjfbmdgcfjbbpaeojofohoefgiehjai|pdf\.js\/web/);
}

test("Chromium-owned PDF viewer shells remain outside automatic scanner control", () => {
  for (const browser of ["chrome", "chromium", "brave", "edge", "vivaldi", "opera", "arc"]) {
    const report = assess(browser, context(chromium + "?src=secret#page=3"));
    assert.equal(report.status, "unsupported-viewer", browser);
    assert.equal(report.viewerType, "browser-owned");
    assert.equal(report.reason, "browser-owned-shell");
    safe(report);
  }
});

test("Firefox built-in PDF.js shell is unsupported despite known URL", () => {
  const report = assess("firefox", context(firefox, { viewerKind: "document" }));
  assert.equal(report.status, "unsupported-viewer");
  assert.equal(report.viewerType, "browser-owned");
  safe(report);
});

test("do not misattribute one browser's privileged viewer to another", () => {
  for (const [browser, url] of [
    ["firefox", chromium], ["chrome", firefox], ["safari", firefox],
    ["safari", chromium], ["edge", firefox]
  ]) {
    const report = assess(browser, context(url));
    assert.equal(report.status, "unverified-viewer", browser);
    assert.equal(report.reason, "viewer-browser-mismatch");
    safe(report);
  }
});

test("site-hosted PDF.js is a viewer hint, never a permission or scan verdict", () => {
  const report = assess("chrome", context(pdfjs, { viewerKind: "document" }));
  assert.equal(report.status, "unsupported-viewer");
  assert.equal(report.reason, "site-pdfjs-rendering");
  assert.equal(report.viewerType, "site-scripted");
  assert.equal(report.nextStep, "offer-explicit-scan-after-eligibility-check");
  safe(report);
});

test("arbitrary same-origin and cross-origin PDF.js claims remain unsupported", () => {
  for (const url of [
    "https://reader.example/pdfjs/web/viewer.html?file=https%3A%2F%2Fevil.example%2Fx.pdf",
    "https://reader.example/pdfjs/web/viewer.html?file=blob%3Ahttps%3A%2F%2Freader.example%2Fabc",
    "https://reader.example/custom-viewer#page=5",
    "https://reader.example/viewer?file=report.pdf"
  ]) {
    const report = assess("firefox", context(url, { viewerKind: "site-scripted" }));
    assert.equal(report.status, "unsupported-viewer");
    assert.equal(report.reason, "uncontrolled-viewer-rendering");
    safe(report);
  }
});

test("embedded frame, plugin and scripted viewers never imply an interlock", () => {
  for (const kind of ["embedded", "plugin", "site-scripted"]) {
    for (const frameId of [0, 2]) {
      const report = assess("edge", context("https://example.test/viewer", {
        viewerKind: kind, frameId
      }));
      assert.equal(report.status, "unsupported-viewer", kind);
      assert.equal(report.viewerType, kind);
      safe(report);
    }
  }
});

test("unknown privileged pages and unknown viewer kinds require explicit fallback", () => {
  for (const url of [
    "about:blank", "chrome://pdf-viewer", "edge://pdf",
    "moz-extension://00000000-aaaa-0000-bbbb-000000000000/viewer.html",
    "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/index.html"
  ]) {
    const report = assess("chrome", context(url, { viewerKind: "unknown" }));
    assert.equal(report.status, "unverified-viewer");
    assert.equal(report.reason, "unrecognized-viewer");
    safe(report);
  }
  const report = assess("safari", context("https://reader.example/viewer", {
    viewerKind: "unknown"
  }));
  assert.equal(report.status, "unverified-viewer");
  safe(report);
});

test("ordinary web documents are not falsely labeled as PDF viewers", () => {
  for (const url of ["https://reader.example/index.html",
    "https://reader.example/file.pdf", "file:///tmp/example.pdf"]) {
    const report = assess("firefox", context(url, { viewerKind: "document" }));
    assert.equal(report.status, "not-a-viewer");
    assert.equal(report.viewerType, "none");
    assert.equal(report.nextStep, "none");
    safe(report);
  }
});

test("unsupported browser IDs never gain viewer permission", () => {
  for (const browser of [undefined, null, "", "unknown", "FireFox", {}, []]) {
    const report = assess(browser, context());
    assert.equal(report.status, "untrusted-context");
    assert.equal(report.reason, "unsupported-browser");
    safe(report);
  }
});

test("untrusted and malformed browser events fail closed", () => {
  const invalid = [
    null, {}, [], "pdf", context(chromium, { trustedBrowserEvent: false }),
    context(chromium, { trustedBrowserEvent: "true" }),
    context(chromium, { frameId: -1 }), context(chromium, { tabId: 1.5 }),
    context(chromium, { tabId: -1 }), context(chromium, { viewerKind: "safe" }),
    context(chromium, { url: "https://user:password@example.test/viewer" }),
    context(chromium, { url: "\nhttps://example.test/viewer" }),
    context(chromium, { url: "not a url" }),
    context(chromium, { url: "x".repeat(8193) }),
    { ...context(), scannerVerified: true },
    Object.create(context())
  ];
  const accessor = context();
  Object.defineProperty(accessor, "url", { get() { throw Error("secret"); } });
  invalid.push(accessor, new Proxy(context(), { ownKeys() { throw Error("secret"); } }));
  for (const record of invalid) {
    const report = assess("chrome", record);
    assert.equal(report.status, "untrusted-context");
    safe(report);
  }
});

test("every browser is treated as inactive for every unsupported viewer category", () => {
  for (const browser of AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX) {
    for (const kind of ["site-scripted", "plugin", "embedded", "unknown"]) {
      const report = assess(browser.id, context("https://example.test/viewer", {
        viewerKind: kind
      }));
      assert.equal(report.interceptionVerified, false);
      assert.equal(report.mayInitiateAutomaticScan, false);
      assert.equal(report.authorizesOpen, false);
      safe(report);
    }
  }
});

test("no browser, native scanner, or permission effects are introduced", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, background, manifest, safari, pkg, ci, guide] = await Promise.all([
    read("../src/pdf-unsupported-viewer.js"), read("../src/background.js"),
    read("../manifest.json").then(JSON.parse),
    read("../../safari/manifest.json").then(JSON.parse),
    read("../package.json").then(JSON.parse),
    read("../../../.github/workflows/ci.yml"),
    read("../src/pdf-unsupported-viewer.md")
  ]);
  for (const forbidden of [
    "addListener(", "permissions.request(", "fetch(", "XMLHttpRequest",
    "connectNative(", "sendNativeMessage(", "downloads.open(",
    "tabs.update(", "location.href", "window.open(", "node:fs",
    "localStorage", "sessionStorage", "scan-and-open"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const phrase of ["opener-0796", "unsupported viewer", "PDF.js",
    "ClamAV", "explicit", "browser-owned", "unknown", "permission"]) {
    assert.ok(guide.toLowerCase().includes(phrase.toLowerCase()), phrase);
  }
});
