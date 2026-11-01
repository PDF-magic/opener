// opener-0801: live Brave Stable BUILT-IN PDF viewer verification.
// Headed browser on a virtual display is intentional: browser PDF viewers
// can behave differently in headless automation. Do not use Chromium as a
// substitute. The only document is a generated PDF served from loopback.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { createBraveViewerTestPdf } from "./brave-pdf-viewer-fixture.mjs";
import { dynamicPdfGeneratorPage } from "./dynamic-pdf-webpage-fixture.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const binary = process.env.BRAVE_BROWSER_PATH || "/usr/bin/brave-browser";
const extensionPath = resolve(root, "dist");
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-brave-viewer-"));
const pdf = createBraveViewerTestPdf();
const requests = [];
const server = createServer((request, response) => {
  requests.push(request.url);
  if (request.method === "GET" && request.url === "/generated") {
    const html = dynamicPdfGeneratorPage;
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Length": Buffer.byteLength(html),
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    });
    response.end(html);
    return;
  }
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

  // opener-1051 (§16.4): an actual local file:// PDF opening is separate
  // from an HTTP-served inline PDF or a page-generated Blob PDF. No user's
  // documents, default app associations, or persistent browser profile change.
  const localPdfPath = join(profile, "brave-local-opening.pdf");
  await writeFile(localPdfPath, pdf, { flag: "wx", mode: 0o600 });
  const localPdfUrl = pathToFileURL(localPdfPath).href;
  const localPage = await context.newPage();
  const localDownloads = [];
  localPage.on("download", event => localDownloads.push(event.suggestedFilename()));
  await localPage.goto(localPdfUrl, { waitUntil: "commit", timeout: 30000 });
  assert.equal(localPage.url(), localPdfUrl,
    "Brave must navigate to the actual local PDF, not a browser download");
  let localViewerFrame = null;
  for (let attempt = 0; attempt < 100; attempt++) {
    localViewerFrame = localPage.frames().find(frame => {
      try {
        const address = new URL(frame.url());
        return address.protocol === "chrome-extension:" &&
          address.hostname === componentId && address.pathname === "/index.html";
      } catch {
        return false;
      }
    });
    if (localViewerFrame) break;
    await localPage.waitForTimeout(100);
  }
  assert.ok(localViewerFrame, "Brave must attach its built-in viewer for a file:// PDF");
  assert.equal(await localPage.evaluate(() => document.contentType), "application/pdf");
  assert.deepEqual(localDownloads, [],
    "Brave must display the local PDF instead of downloading it");
  assert.deepEqual(downloads, [], "Opening a local PDF must not download the inline PDF");
  await localPage.close();

  // opener-0807: visit HTML, generate PDF bytes in the webpage's own JS,
  // create a Blob URL there and open the browser-owned viewer from that URL.
  // This does not exercise interception, ClamAV or an extension scan.
  const dynamicPage = await context.newPage();
  const dynamicDownloads = [];
  dynamicPage.on("download", event => dynamicDownloads.push(event.suggestedFilename()));
  const generatorResponse = await dynamicPage.goto(origin + "/generated", {
    waitUntil: "load", timeout: 30000
  });
  assert.equal(generatorResponse?.status(), 200);
  assert.match(generatorResponse.headers()["content-type"] ?? "", /^text\/html\b/i);
  const generated = await dynamicPage.evaluate(() => {
    document.getElementById("generate").click();
    const current = window.generatedPdf;
    return {
      type: current?.blob.type, size: current?.blob.size, url: current?.url,
      prefix: new TextDecoder().decode(current?.bytes.slice(0, 8)),
      ready: document.getElementById("open").disabled === false
    };
  });
  assert.equal(generated.type, "application/pdf");
  assert.equal(generated.prefix, "%PDF-1.4");
  assert.ok(generated.size > 200 && generated.size < 4096);
  assert.equal(generated.ready, true);
  assert.ok(generated.url.startsWith("blob:" + origin + "/"),
    "The webpage must create the PDF object URL, not fetch a PDF");
  await dynamicPage.evaluate(() => document.getElementById("open").click());
  let dynamicViewerFrame = null;
  for (let attempt = 0; attempt < 100; attempt++) {
    dynamicViewerFrame = dynamicPage.frames().find(frame => {
      try {
        const url = new URL(frame.url());
        return url.protocol === "chrome-extension:" &&
          url.hostname === componentId && url.pathname === "/index.html";
      } catch {
        return false;
      }
    });
    if (dynamicViewerFrame && dynamicPage.url() === generated.url) break;
    await dynamicPage.waitForTimeout(100);
  }
  if (!dynamicViewerFrame) {
    // Diagnostics contain only the generated local fixture and frame schemes,
    // never external URLs, user files, headers, or PDF contents.
    console.log("Dynamic PDF local viewer diagnostics:", JSON.stringify({
      frameSchemes: dynamicPage.frames().map(frame => {
        try { return new URL(frame.url()).protocol; } catch { return "invalid"; }
      }),
      documentScheme: (() => {
        try { return new URL(dynamicPage.url()).protocol; } catch { return "invalid"; }
      })()
    }));
  }
  assert.ok(dynamicViewerFrame,
    "Brave must render the PDF generated in webpage JavaScript");
  assert.equal(dynamicPage.url(), generated.url,
    "Brave must navigate to the webpage-created Blob PDF");
  assert.equal(await dynamicPage.evaluate(() => document.contentType), "application/pdf");
  assert.equal(requests.filter(path => path === "/generated").length, 1);
  assert.deepEqual(dynamicDownloads, [], "Generated Blob PDF must not silently download");
  assert.deepEqual(downloads, [], "Existing inline PDF must not download");
  assert.ok(!requests.some(path => path.endsWith("/generated.pdf")),
    "The HTTP server must not supply generated PDF bytes");
  await dynamicPage.close();

  // A browser viewer is not a native scanner verdict or an interception gate.
  const worker = context.serviceWorkers().find(
    candidate => candidate.url().startsWith("chrome-extension://")
  ) ?? await context.waitForEvent("serviceworker", {
    predicate: candidate => candidate.url().startsWith("chrome-extension://"),
    timeout: 30000
  });
  assert.equal(await worker.evaluate(async () =>
    chrome.permissions.contains({ permissions: ["downloads"] })), false);
  console.log("Brave Stable viewer verified for inline HTTP, local file, and generated Blob PDFs; no downloads or scanner permissions.");
} finally {
  try { await context?.close(); } finally {
    if (listening) await new Promise(resolveClose => server.close(resolveClose));
    else server.close();
    await rm(profile, { recursive: true, force: true });
  }
}
