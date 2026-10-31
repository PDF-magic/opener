import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPrivilegedPdfViewer } from "../src/pdf-privileged-viewer.js";
import { assessUnsupportedPdfViewer } from "../src/pdf-unsupported-viewer.js";
import { getPdfInterceptionPointAssessment } from "../src/pdf-interception-point-assessment.js";

const load = path => readFile(new URL(path, import.meta.url), "utf8");
const chromeViewer = "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html";

test("actual Chrome viewer URL is a browser-owned shell, not verified PDF bytes", () => {
  const detected = detectPrivilegedPdfViewer({
    tabId: 12, frameId: 0, url: chromeViewer
  });
  assert.equal(detected.isPrivilegedPdfViewer, true);
  assert.equal(detected.isPdfCandidate, false);
  assert.equal(detected.authorizesOpen, false);
  const report = assessUnsupportedPdfViewer("chrome", {
    tabId: 12, frameId: 0, url: chromeViewer, viewerKind: "browser-owned",
    trustedBrowserEvent: true
  });
  assert.equal(report.status, "unsupported-viewer");
  assert.equal(report.mayInitiateAutomaticScan, false);
  assert.equal(report.authorizesOpen, false);
  const point = getPdfInterceptionPointAssessment("chrome");
  assert.equal(point.enforceableInCurrentExtension, false);
  assert.equal(point.automaticInterceptionEnabled, false);
});

test("Chrome viewer test must start a real browser and observe PDF rendering", async () => {
  const [ci, harness, packageJson] = await Promise.all([
    load("../../../.github/workflows/ci.yml"),
    load("../scripts/test-chrome-pdf-viewer.mjs"),
    load("../package.json").then(JSON.parse)
  ]);
  assert.match(ci, /name: Verify Chrome's built-in PDF viewer with local PDFs/);
  assert.match(ci, /node scripts\/test-chrome-pdf-viewer\.mjs "\$CHROME_PATH"/);
  assert.match(ci, /browser-actions\/setup-chrome@v2/);
  assert.match(ci, /chrome-version: stable/);
  assert.match(harness, /Target\.createTarget/);
  assert.match(harness, /Page\.navigate/);
  assert.match(harness, /Page\.getFrameTree/);
  assert.match(harness, /DOM\.getDocument/);
  assert.match(harness, /mhjfbmdgcfjbbpaeojofohoefgiehjai/);
  assert.match(harness, /application\/pdf/);
  assert.match(harness, /\/built-in-viewer\.pdf/);
  assert.match(harness, /\/mime-only/);
  assert.match(harness, /assert\.ok\(counts\.get\(route\) > 0/);
  assert.match(harness, /Chrome must retain the original PDF navigation/);
  assert.match(harness, /createServer/);
  assert.match(harness, /"127\.0\.0\.1"/);
  assert.match(harness, /await rm\(profile, \{ recursive: true, force: true \}\)/);
  assert.match(packageJson.scripts.test, /tests\/\*\.test\.mjs/);
});

test("viewer smoke leaves the production extension and scanner disconnected", async () => {
  const [harness, background, manifest] = await Promise.all([
    load("../scripts/test-chrome-pdf-viewer.mjs"),
    load("../src/background.js"),
    load("../manifest.json").then(JSON.parse)
  ]);
  for (const forbidden of [
    "--load-extension=", "chrome.permissions.request",
    "chrome.tabs.create", "scan-and-open",
    "sendNativeMessage(", "connectNative(",
    "downloads.open(", "clamscan(", "https://"
  ]) assert.equal(harness.includes(forbidden), false, forbidden);
  assert.equal(background.trim().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
});
