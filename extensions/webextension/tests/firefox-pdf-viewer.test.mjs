import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPrivilegedPdfViewer } from "../src/pdf-privileged-viewer.js";
import { assessUnsupportedPdfViewer } from "../src/pdf-unsupported-viewer.js";
import { getPdfInterceptionPointAssessment } from "../src/pdf-interception-point-assessment.js";

const read = path => readFile(new URL(path, import.meta.url), "utf8");
const nativeReader = "resource://pdf.js/web/viewer.html";

test("Firefox built-in PDF.js shell cannot authorize any automatic scanning", () => {
  const detected = detectPrivilegedPdfViewer({
    tabId: 1, frameId: 0, url: nativeReader
  });
  assert.equal(detected.isPrivilegedPdfViewer, true);
  assert.equal(detected.isPdfCandidate, false);
  assert.equal(detected.authorizesOpen, false);
  const report = assessUnsupportedPdfViewer("firefox", {
    tabId: 1, frameId: 0, url: nativeReader,
    viewerKind: "browser-owned", trustedBrowserEvent: true
  });
  assert.equal(report.status, "unsupported-viewer");
  assert.equal(report.mayInitiateAutomaticScan, false);
  assert.equal(report.authorizesOpen, false);
  assert.equal(getPdfInterceptionPointAssessment("firefox").automaticInterceptionEnabled, false);
});

test("CI actually launches Firefox and asserts rendered PDF.js page content", async () => {
  const [ci, harness, pkg] = await Promise.all([
    read("../../../.github/workflows/ci.yml"),
    read("../scripts/test-firefox-pdf-viewer.mjs"),
    read("../package.json").then(JSON.parse)
  ]);
  for (const item of [
    "firefox-pdf-viewer-smoke:",
    "name: Firefox built-in PDF viewer smoke test",
    "browser-actions/setup-firefox@v1",
    "browser-actions/setup-geckodriver@latest",
    'node scripts/test-firefox-pdf-viewer.mjs "$FIREFOX_PATH"'
  ]) assert.ok(ci.includes(item), item);
  for (const item of [
    "Mozilla Firefox", "-headless", "-profile", "pdfjs.disabled",
    "browser.download.viewableInternally.enabledTypes",
    "application/pdf", "Content-Disposition", "inline",
    "127.0.0.1", "/built-in-viewer.pdf", "/mime-only",
    "PDFViewerApplication", "#viewerContainer #viewer", "#pageNumber",
    "#numPages", "data-page-number", "firstPageRendered",
    "found.pages", "counts.get(route) > 0", "server.close(resolve)",
    "await rm(profile, { recursive: true, force: true })"
  ]) assert.ok(harness.includes(item), item);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
});

test("the Firefox viewer check cannot change installed browser or native safety policy", async () => {
  const [harness, background, manifest] = await Promise.all([
    read("../scripts/test-firefox-pdf-viewer.mjs"),
    read("../src/background.js"),
    read("../manifest.json").then(JSON.parse)
  ]);
  for (const forbidden of [
    "--load-extension=", "chrome.permissions.request", "browser.permissions.request",
    "scan-and-open", "connectNative(", "sendNativeMessage(",
    "downloads.open(", "clamscan(", "https://"
  ]) assert.ok(!harness.includes(forbidden), forbidden);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
});
