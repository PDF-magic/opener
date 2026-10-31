import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectPdfIframe } from "../src/pdf-iframe.js";
import { detectPrivilegedPdfViewer } from "../src/pdf-privileged-viewer.js";
import { getPdfInterceptionPointAssessment } from "../src/pdf-interception-point-assessment.js";

const load = path => readFile(new URL(path, import.meta.url), "utf8");
const iframe = src => ({
  tagName: "IFRAME", src, documentUrl: "http://127.0.0.1:33333/embedded-frames.html"
});

test("two independently embedded iframe paths remain candidates, never verified scans", () => {
  const a = detectPdfIframe(iframe("/framed-a.pdf"));
  const b = detectPdfIframe(iframe("/framed-b.pdf"));
  assert.deepEqual(a, { isPdfCandidate: true, evidence: "iframe-src",
    authorizesOpen: false });
  assert.deepEqual(b, a);
  for (const result of [a, b]) assert.ok(Object.isFrozen(result));
  assert.equal(detectPdfIframe(iframe("/ordinary-frame.html")).isPdfCandidate, false);
  assert.equal(detectPdfIframe({ ...iframe("/framed-a.pdf"), srcdoc: "" })
    .isPdfCandidate, false);
  assert.equal(detectPdfIframe(iframe("javascript:alert(1)")).isPdfCandidate, false);
});

test("embedded browser-owned PDF viewer shell is not evidence of clean PDF bytes", () => {
  const detected = detectPrivilegedPdfViewer({
    tabId: 8, frameId: 3,
    url: "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html"
  });
  assert.equal(detected.isPrivilegedPdfViewer, true);
  assert.equal(detected.isPdfCandidate, false);
  assert.equal(detected.authorizesOpen, false);
  for (const browser of ["chrome", "firefox", "edge", "safari", "brave"]) {
    const assessment = getPdfInterceptionPointAssessment(browser);
    assert.equal(assessment.enforceableInCurrentExtension, false);
    assert.equal(assessment.automaticInterceptionEnabled, false);
    assert.equal(assessment.allPdfOpeningPathsBlocked, false);
  }
});

test("real Chrome CI exercise has two PDF iframe children and an HTML control", async () => {
  const [harness, workflow, pkg, doc] = await Promise.all([
    load("../scripts/test-chrome-pdf-viewer.mjs"),
    load("../../../.github/workflows/ci.yml"),
    load("../package.json").then(JSON.parse),
    load("../src/pdf-embedded-frame-verification.md")
  ]);
  assert.match(workflow, /Verify Chrome's built-in PDF viewer with local PDFs/);
  assert.match(workflow, /node scripts\/test-chrome-pdf-viewer\.mjs "\$CHROME_PATH"/);
  assert.equal(workflow.includes("--embedded-only"), false);
  assert.match(harness, /Target\.createTarget/);
  assert.match(harness, /Page\.navigate/);
  assert.match(harness, /Page\.getFrameTree/);
  assert.match(harness, /DOM\.getDocument/);
  assert.match(harness, /hasViewerFrame\(frameTree\)/);
  assert.match(harness, /hasViewerEmbed\(root\)/);
  assert.match(harness, /hasBrowserViewer/);
  for (const path of ["/embedded-frames.html", "/ordinary-frame.html",
    "/framed-a.pdf", "/framed-b.pdf"]) assert.ok(harness.includes(path));
  assert.match(harness, /state\.frames\.filter\(url => pdfUrls\.includes\(url\)\)\.length, 2/);
  assert.match(harness, /counts\.get\(path\) > 0/);
  assert.match(harness, /127\.0\.0\.1/);
  assert.match(harness, /await rm\(profile, \{ recursive: true, force: true \}\)/);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(doc, /opener-0805/);
  assert.match(doc, /not.*scan-before-open/i);
});

test("real browser uses a disposable profile without weakening scanner safety", async () => {
  const [harness, manifest, background] = await Promise.all([
    load("../scripts/test-chrome-pdf-viewer.mjs"),
    load("../manifest.json").then(JSON.parse),
    load("../src/background.js")
  ]);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  for (const forbidden of [
    "--load-extension=", "permissions.request(", "connectNative(",
    "sendNativeMessage(", "scan-and-open", "clamscan(", "downloads.open(",
    "https://", "file:///Users", "file:///home"
  ]) assert.equal(harness.includes(forbidden), false, forbidden);
});
