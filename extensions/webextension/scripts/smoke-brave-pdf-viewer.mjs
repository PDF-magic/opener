// opener-0801: live Brave Stable BUILT-IN PDF viewer verification.
// Headed browser on a virtual display is intentional: browser PDF viewers
// can behave differently in headless automation. Do not use Chromium as a
// substitute. The only document is a generated PDF served from loopback.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createBraveViewerTestPdf } from "./brave-pdf-viewer-fixture.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const binary = process.env.BRAVE_BROWSER_PATH || "/usr/bin/brave-browser";
const extensionPath = resolve(root, "dist");
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-brave-viewer-"));
const pdf = createBraveViewerTestPdf();
const requests = [];
const server = createServer((request, response) => {
  requests.push(request.url);
  if (request.url !== "/inline.pdf") {
    response.writeHead(404, { "Cache-Control": "no-store" });
    response.end();
    return;
  }
  response.writeHead(200, {
    "Content-Type": "application/pdf",
    "Content-Disposition": "inline; filename=\"brave-viewer-test.pdf\"",
    "Content-Length": String(pdf.length),
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  response.end(pdf);
});
let context;
let listening = false;
try {
  const manifest = JSON.parse(await readFile(join(extensionPath, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(0, "127.0.0.1", resolveListen);
  });
  listening = true;
  const origin = "http://127.0.0.1:" + String(server.address().port);
  context = await chromium.launchPersistentContext(profile, {
    executablePath: binary,
    headless: false,
    acceptDownloads: false,
    args: [
      "--disable-extensions-except=" + extensionPath,
      "--load-extension=" + extensionPath,
      "--no-first-run", "--no-default-browser-check",
      "--disable-background-networking"
    ],
    timeout: 45000
  });

  const page = await context.newPage();
  const errors = [];
  const downloads = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("download", download => downloads.push(download.suggestedFilename()));

  // Content-Type and Content-Disposition, not a URL suffix or extension UI,
  // choose the inline rendering path. Browser PDF preferences are untouched.
  const pdfUrl = origin + "/inline.pdf";
  const response = await page.goto(pdfUrl, {
    waitUntil: "commit", timeout: 30000
  });
  assert.equal(response?.status(), 200, "Brave must load the local synthetic PDF");
  assert.match(response.headers()["content-type"] ?? "", /^application\/pdf\b/i);
  assert.match(response.headers()["content-disposition"] ?? "", /^inline\b/i);

  // Brave's built-in Chromium-family PDF viewer exposes a browser-owned
  // application/pdf embed. Checking the real DOM distinguishes this test from
  // merely fetching a PDF or loading the PDF Magic Opener extension popup.
  const viewer = page.locator('embed[type="application/pdf"]').first();
  await viewer.waitFor({ state: "attached", timeout: 20000 });
  assert.equal(await viewer.getAttribute("type"), "application/pdf");
  assert.equal(new URL(page.url()).origin, origin);
  assert.ok(requests.includes("/inline.pdf"), "Brave must request the PDF from localhost");
  assert.deepEqual(downloads, [], "The default clean-profile inline PDF must not download");
  assert.deepEqual(errors, [], "Brave's viewer should not raise document script errors");

  // A browser viewer is not a native scanner verdict or an interception gate.
  const worker = context.serviceWorkers().find(
    candidate => candidate.url().startsWith("chrome-extension://")
  ) ?? await context.waitForEvent("serviceworker", {
    predicate: candidate => candidate.url().startsWith("chrome-extension://"),
    timeout: 30000
  });
  assert.equal(await worker.evaluate(async () =>
    chrome.permissions.contains({ permissions: ["downloads"] })), false);
  console.log("Brave Stable built-in PDF viewer verified with local inline PDF; no download or scanner permissions.");
} finally {
  try { await context?.close(); } finally {
    if (listening) await new Promise(resolveClose => server.close(resolveClose));
    else server.close();
    await rm(profile, { recursive: true, force: true });
  }
}
