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

  // A real PDF viewer may create an internal browser-owned PDF frame while
  // the top-level application/pdf document has no ordinary DOM <embed>.
  // Verify the exact Chromium PDF component, not just a successful download
  // response or an arbitrary extension frame.
  const componentId = "mhjfbmdgcfjbbpaeojofohoefgiehjai";
  let viewerFrame = null;
  for (let attempt = 0; attempt < 50; attempt++) {
    viewerFrame = page.frames().find(frame => {
      try {
        const address = new URL(frame.url());
        return address.protocol === "chrome-extension:" &&
          address.hostname === componentId && address.pathname === "/index.html";
      } catch {
        return false;
      }
    });
    if (viewerFrame) break;
    await page.waitForTimeout(100);
  }
  if (!viewerFrame) {
    // Only disclose schemes, component names and paths; never any URL query
    // values, headers, PDF bytes or user-provided navigation information.
    const frames = page.frames().map(frame => {
      try {
        const address = new URL(frame.url());
        return { scheme: address.protocol, host: address.hostname,
          path: address.pathname };
      } catch {
        return { scheme: "unavailable" };
      }
    });
    console.log("Synthetic Brave viewer frame diagnostics:", JSON.stringify(frames));
  }
  assert.ok(viewerFrame, "Brave must attach its browser-owned PDF viewer frame");
  assert.equal(await page.evaluate(() => document.contentType), "application/pdf");
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
