// End-to-end verification of Firefox's built-in PDF.js viewer (opener-0803).
// Only loopback-generated PDFs and a disposable headless Firefox profile.
// No production extension, scanner, native host, or user PDF is accessed.
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { createServer as createTcpServer } from "node:net";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const firefox = process.argv[2] || process.env.FIREFOX_PATH;
const driverBinary = process.argv[3] || process.env.GECKODRIVER_PATH || "geckodriver";
assert.ok(firefox, "Usage: node scripts/test-firefox-pdf-viewer.mjs FIREFOX_BINARY [GECKODRIVER_BINARY]");
const version = execFileSync(firefox, ["--version"], {
  encoding: "utf8", timeout: 8_000
}).trim();
assert.match(version, /Mozilla Firefox/i, "The real Mozilla Firefox binary is required");

function makePdf() {
  const content = "BT /F1 18 Tf 60 730 Td (PDF Magic Firefox Viewer Smoke Test) Tj ET\n";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
      "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    "<< /Length " + Buffer.byteLength(content) + " >>\nstream\n" + content + "endstream",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
  ];
  let source = "%PDF-1.4\n";
  const offsets = [0];
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(source));
    source += (index + 1) + " 0 obj\n" + object + "\nendobj\n";
  }
  const crossReference = Buffer.byteLength(source);
  source += "xref\n0 " + (objects.length + 1) + "\n0000000000 65535 f \n" +
    offsets.slice(1).map(position =>
      String(position).padStart(10, "0") + " 00000 n \n").join("") +
    "trailer\n<< /Size " + (objects.length + 1) +
    " /Root 1 0 R >>\nstartxref\n" + crossReference + "\n%%EOF\n";
  return Buffer.from(source, "ascii");
}

const pdf = makePdf();
const routes = ["/built-in-viewer.pdf", "/mime-only"];
const counts = new Map(routes.map(route => [route, 0]));
const server = createServer((request, response) => {
  if (request.method !== "GET" || !counts.has(request.url)) {
    response.writeHead(404, { "Cache-Control": "no-store" });
    response.end();
    return;
  }
  counts.set(request.url, counts.get(request.url) + 1);
  response.writeHead(200, {
    "Content-Type": "application/pdf", "Content-Disposition": "inline",
    "Content-Length": pdf.length, "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  response.end(pdf);
});

const profile = await mkdtemp(join(tmpdir(), "pdfmagic-firefox-viewer-"));
let driver;
let sessionId;
let driverUrl;
let serverStarted = false;
let stderrTail = "";

async function until(fn, label, timeout = 40_000) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    try {
      const value = await fn();
      if (value) return value;
    } catch (error) {
      last = error;
    }
    await delay(250);
  }
  throw new Error("Firefox viewer smoke timed out: " + label +
    (last ? " (" + last.message + ")" : ""));
}

async function freeLoopbackPort() {
  const reservation = createTcpServer();
  await new Promise((resolve, reject) => {
    reservation.once("error", reject);
    reservation.listen(0, "127.0.0.1", resolve);
  });
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  return port;
}

async function webdriver(method, endpoint, data, timeout = 30_000) {
  const response = await fetch(driverUrl + endpoint, {
    method, headers: { "Content-Type": "application/json" },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    signal: AbortSignal.timeout(timeout)
  });
  const result = await response.json();
  if (!response.ok || result.value?.error) {
    // Never include browser documents or user data in exception messages.
    throw new Error("WebDriver failed: " + endpoint + " (" +
      (result.value?.error || response.status) + ")");
  }
  return result.value;
}

// Checks actual PDF.js reader UI and a fully loaded/rendered one-page PDF.
// HTTP success, a download, an empty viewer shell or a normal web page fails.
const viewerProbe = [
  "return (() => {",
  "const app = window.PDFViewerApplication;",
  "const viewer = document.querySelector('#viewerContainer #viewer');",
  "const firstPage = viewer?.querySelector('.page[data-page-number=\"1\"]');",
  "return {",
  "readerControls: !!document.querySelector('#pageNumber') &&",
  "  !!document.querySelector('#numPages') && !!viewer,",
  "pages: app?.pdfDocument?.numPages ?? null,",
  "firstPageRendered: firstPage?.getAttribute('data-loaded') === 'true' ||",
  "  !!firstPage?.querySelector('canvas') ||",
  "  !!firstPage?.querySelector('.textLayer span'),",
  "ready: app?.initialized === true && !!app?.pdfDocument",
  "};",
  "})();"
].join("\n");

try {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.removeListener("error", reject);
      serverStarted = true;
      resolve();
    });
  });
  const pdfPort = server.address().port;
  const driverPort = await freeLoopbackPort();
  driverUrl = "http://127.0.0.1:" + driverPort;
  driver = spawn(driverBinary, ["--host", "127.0.0.1", "--port", String(driverPort),
    "--log", "error"], { stdio: ["ignore", "ignore", "pipe"] });
  driver.stderr.on("data", bytes => {
    stderrTail = (stderrTail + bytes.toString("utf8")).slice(-1500);
  });
  await until(async () => {
    if (driver.exitCode !== null || driver.signalCode !== null) {
      throw new Error("geckodriver exited before startup");
    }
    const status = await webdriver("GET", "/status", undefined, 3_000);
    return status.ready === true;
  }, "local geckodriver startup", 30_000);

  const session = await webdriver("POST", "/session", {
    capabilities: { alwaysMatch: {
      browserName: "firefox", pageLoadStrategy: "eager",
      "moz:firefoxOptions": {
        binary: firefox, args: ["-headless", "-profile", profile],
        prefs: {
          "pdfjs.disabled": false,
          "browser.download.viewableInternally.enabledTypes": "application/pdf",
          "browser.helperApps.alwaysAsk.force": false,
          "browser.shell.checkDefaultBrowser": false,
          "app.update.enabled": false
        }
      },
      timeouts: { pageLoad: 30_000, script: 15_000 }
    } }
  }, 45_000);
  assert.equal(session.capabilities.browserName, "firefox");
  sessionId = session.sessionId;
  assert.ok(sessionId, "Firefox must create an isolated WebDriver session");

  for (const route of routes) {
    const url = "http://127.0.0.1:" + pdfPort + route;
    await webdriver("POST", "/session/" + sessionId + "/url", { url }, 40_000);
    const found = await until(async () => {
      const evidence = await webdriver("POST", "/session/" + sessionId + "/execute/sync", {
        script: viewerProbe, args: []
      }, 12_000);
      return evidence.readerControls && evidence.pages === 1 &&
        evidence.ready && evidence.firstPageRendered ? evidence : null;
    }, "built-in PDF.js document and rendered page for " + route, 45_000);
    assert.equal(found.pages, 1);
    assert.ok(counts.get(route) > 0, "Firefox must request the actual loopback PDF");
  }
  console.log("PASS Firefox built-in PDF.js viewer renders local PDF and MIME-only PDF: " + version);
} catch (error) {
  console.error("Firefox isolated viewer diagnostic:", stderrTail);
  throw error;
} finally {
  if (sessionId) {
    try { await webdriver("DELETE", "/session/" + sessionId, undefined, 5_000); }
    catch { /* Exit process and remove disposable profile anyway. */ }
  }
  if (driver && driver.exitCode === null) driver.kill("SIGTERM");
  await delay(300);
  if (driver && driver.exitCode === null) driver.kill("SIGKILL");
  if (serverStarted) await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
