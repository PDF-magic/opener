// Exercise Firefox's browser-owned native PDF download manager with real
// WebDriver clicks on generated loopback responses. Never access a user profile,
// install an extension, invoke PDF Magic's scanner, or open the saved PDF.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createServer } from "node:http";
import { createServer as createTcpServer } from "node:net";
import { mkdir, mkdtemp, readFile, readdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { createNativePdfDownloadFixture } from "./native-pdf-download-fixture.mjs";

const firefox = process.argv[2] || process.env.FIREFOX_PATH;
const driver = process.argv[3] || process.env.GECKODRIVER_PATH || "geckodriver";
assert.ok(firefox, "Usage: node scripts/test-firefox-native-pdf-download.mjs FIREFOX_BINARY [GECKODRIVER_BINARY]");
const version = execFileSync(firefox, ["--version"], {
  encoding: "utf8", timeout: 8000
}).trim();
assert.match(version, /Mozilla Firefox/, "The real Firefox binary is required");
const verifyMacHandoff = process.argv.includes("--macos-handoff");
if (verifyMacHandoff) assert.equal(process.platform, "darwin",
  "The quarantine/scan-open integration requires a real macOS runner");
const fixture = createNativePdfDownloadFixture();

// Two genuine inline responses with Firefox's PDF.js deliberately disabled in
// this disposable profile, plus a .pdf-looking HTML control. These test
// unsupported inline viewing, not the existing attachment download cases.
const unsupportedInline = Object.freeze([
  Object.freeze({
    path: "/unsupported-inline/disabled.pdf", name: "disabled.pdf",
    mime: "application/pdf"
  }),
  Object.freeze({
    path: "/unsupported-inline/octet.pdf", name: "octet.pdf",
    mime: "application/octet-stream"
  })
]);
const unsupportedHits = new Map(unsupportedInline.map(item => [item.path, 0]));
let htmlControlHits = 0;
const server = createServer((request, response) => {
  if (request.url?.startsWith("/unsupported-inline/")) {
    if (request.method !== "GET") {
      response.writeHead(405, { "Allow": "GET", "Cache-Control": "no-store" });
      response.end();
      return;
    }
    if (request.url === "/unsupported-inline/index") {
      response.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"
      });
      response.end("<!doctype html><title>Unsupported inline PDF fixture</title>" +
        unsupportedInline.map((item, index) =>
          '<a id="inline-' + index + '" href="' + item.path + '">Local PDF</a>'
        ).join(""));
      return;
    }
    const item = unsupportedInline.find(entry => entry.path === request.url);
    if (item) {
      unsupportedHits.set(item.path, unsupportedHits.get(item.path) + 1);
      response.writeHead(200, {
        "Content-Type": item.mime,
        "Content-Disposition": "inline",
        "Content-Length": fixture.pdf.length,
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"
      });
      response.end(fixture.pdf);
      return;
    }
    if (request.url === "/unsupported-inline/not-really.pdf") {
      htmlControlHits++;
      const html = "<!doctype html><title>Not a PDF</title>" +
        "<p>HTML control, not a PDF viewer</p>";
      response.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": Buffer.byteLength(html),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"
      });
      response.end(html);
      return;
    }
  }
  if (fixture.handle(request, response)) return;
  response.writeHead(404, { "Cache-Control": "no-store" });
  response.end();
});
const profile = await mkdtemp(join(tmpdir(), "pdfmagic-firefox-native-download-"));
const downloadDir = join(profile, "downloads");
let processHandle;
let driverUrl;
let sessionId;
let listening = false;
let stderrTail = "";

async function until(check, label, timeout = 45_000) {
  const deadline = Date.now() + timeout;
  let last;
  while (Date.now() < deadline) {
    try {
      const result = await check();
      if (result) return result;
    } catch (error) {
      last = error;
    }
    await delay(250);
  }
  throw new Error("Firefox native PDF download timed out: " + label +
    (last ? " (" + last.message + ")" : ""));
}
async function availablePort() {
  const reservation = createTcpServer();
  await new Promise((resolve, reject) => {
    reservation.once("error", reject);
    reservation.listen(0, "127.0.0.1", resolve);
  });
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  return port;
}
async function webdriver(method, path, data, timeout = 30_000) {
  const response = await fetch(driverUrl + path, {
    method,
    headers: { "Content-Type": "application/json" },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    signal: AbortSignal.timeout(timeout)
  });
  const result = await response.json();
  if (!response.ok || result.value?.error) {
    throw new Error("Firefox WebDriver failed: " + path +
      " (" + (result.value?.error || response.status) + ")");
  }
  return result.value;
}

try {
  await mkdir(downloadDir);
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.removeListener("error", reject);
      listening = true;
      resolve();
    });
  });
  const origin = "http://127.0.0.1:" + server.address().port;
  driverUrl = "http://127.0.0.1:" + await availablePort();
  processHandle = spawn(driver, [
    "--host", "127.0.0.1", "--port", new URL(driverUrl).port, "--log", "error"
  ], { stdio: ["ignore", "ignore", "pipe"] });
  processHandle.stderr.on("data", bytes => {
    stderrTail = (stderrTail + bytes.toString("utf8")).slice(-1800);
  });
  await until(async () => {
    if (processHandle.exitCode !== null || processHandle.signalCode !== null) {
      throw new Error("geckodriver stopped before startup");
    }
    return (await webdriver("GET", "/status", undefined, 3000)).ready === true;
  }, "disposable Firefox driver", 30_000);

  const session = await webdriver("POST", "/session", {
    capabilities: { alwaysMatch: {
      browserName: "firefox", pageLoadStrategy: "eager",
      "moz:firefoxOptions": {
        binary: firefox,
        args: ["-headless", "-profile", profile],
        prefs: {
          // All preferences apply solely to this newly created profile.
          // Force save-to-disk to test native downloads, not PDF.js inline
          // behavior or any existing user's PDF opening preferences.
          "pdfjs.disabled": true,
          "browser.download.folderList": 2,
          "browser.download.dir": downloadDir,
          "browser.download.useDownloadDir": true,
          "browser.download.always_ask_before_handling_new_types": false,
          "browser.helperApps.neverAsk.saveToDisk":
            "application/pdf,application/octet-stream",
          "browser.download.alwaysOpenPanel": false,
          "browser.download.manager.showWhenStarting": false,
          "browser.shell.checkDefaultBrowser": false,
          "app.update.enabled": false
        }
      },
      timeouts: { pageLoad: 25_000, script: 10_000 }
    } }
  }, 50_000);
  assert.equal(session.capabilities.browserName, "firefox");
  sessionId = session.sessionId;
  assert.ok(sessionId);

  for (const item of fixture.cases) {
    // Real WebDriver element clicks exercise Firefox's own handling of an
    // attachment response, not an extension downloads.download() call.
    await webdriver("POST", "/session/" + sessionId + "/url", {
      url: origin + "/native-download/index"
    }, 35_000);
    const element = await webdriver("POST",
      "/session/" + sessionId + "/element", {
        using: "css selector", value: item.selector
      }, 10_000);
    const elementId = element["element-6066-11e4-a52e-4f735466cecf"];
    assert.ok(elementId, "Firefox must find an actual download link");
    await webdriver("POST", "/session/" + sessionId +
      "/element/" + elementId + "/click", {}, 35_000);
    assert.ok(await until(async () => {
      const count = fixture.snapshot().requests[item.path];
      return count > 0 ? count : null;
    }, "actual Firefox PDF HTTP request " + item.name));
    await until(async () => {
      const downloaded = await stat(join(downloadDir, item.name));
      const files = await readdir(downloadDir);
      return downloaded.size === fixture.pdf.length &&
        !files.some(name => name.endsWith(".part")) ? true : null;
    }, "completed native PDF file " + item.name, 55_000);
    assert.deepEqual(await readFile(join(downloadDir, item.name)), fixture.pdf,
      "Firefox must save exact bytes with the server-supplied filename");
    if (verifyMacHandoff) {
      // The helper runs the real scanner gate with all external scanner/GUI
      // commands mocked; nothing is launched outside this disposable profile.
      const verified = execFileSync("python3", [
        "../../tests/browser/firefox-downloaded-open.py",
        join(downloadDir, item.name)
      ], { encoding: "utf8", timeout: 45_000 });
      assert.match(verified, /PASS Firefox-downloaded PDF scan-and-open isolation/);
    }
  }

  // When the built-in PDF.js viewer is disabled by this temporary profile,
  // inline PDF MIME and unknown/octet MIME must take the browser-owned
  // download path rather than claiming a rendered or scanned inline viewer.
  for (const [index, item] of unsupportedInline.entries()) {
    await webdriver("POST", "/session/" + sessionId + "/url", {
      url: origin + "/unsupported-inline/index"
    });
    const element = await webdriver("POST", "/session/" + sessionId + "/element", {
      using: "css selector", value: "#inline-" + index
    });
    const elementId = element["element-6066-11e4-a52e-4f735466cecf"];
    assert.ok(elementId, "Firefox must expose the real inline link");
    await webdriver("POST", "/session/" + sessionId +
      "/element/" + elementId + "/click", {}, 35_000);
    await until(async () => unsupportedHits.get(item.path) === 1,
      "Firefox requesting unsupported inline PDF " + item.name);
    await until(async () => {
      const downloaded = await stat(join(downloadDir, item.name));
      const files = await readdir(downloadDir);
      return downloaded.size === fixture.pdf.length &&
        !files.some(name => name.endsWith(".part"));
    }, "Firefox saving unsupported inline PDF " + item.name, 55_000);
    assert.deepEqual(await readFile(join(downloadDir, item.name)), fixture.pdf,
      "Disabled inline viewer must preserve the exact PDF bytes on download");
    assert.equal(unsupportedHits.get(item.path), 1,
      "Unsupported inline route must only be requested once");
  }

  // A .pdf suffix with an actual HTML MIME type is not PDF evidence; the
  // browser must display the harmless HTML control, not save/approve a PDF.
  const notPdf = origin + "/unsupported-inline/not-really.pdf";
  await webdriver("POST", "/session/" + sessionId + "/url", { url: notPdf });
  await until(async () => {
    const observed = await webdriver("POST", "/session/" + sessionId +
      "/execute/sync", {
        script: "return {url: location.href, text: document.body.textContent};",
        args: []
      });
    return observed.url === notPdf &&
      observed.text?.includes("HTML control, not a PDF viewer");
  }, "HTML content at a misleading .pdf URL");
  assert.equal(htmlControlHits, 1, "HTML fallback must be served only once");

  assert.deepEqual((await readdir(downloadDir)).sort(),
    [...fixture.cases, ...unsupportedInline].map(item => item.name).sort(),
    "Only the expected downloaded PDFs may be saved");
  assert.ok(fixture.snapshot().landingRequests >= fixture.cases.length);
  for (const item of fixture.cases) {
    assert.equal(fixture.snapshot().requests[item.path], 1,
      "One user-like click must fetch one PDF");
  }
  console.log("PASS Firefox browser-native PDF attachment and octet downloads: " + version);
  console.log("PASS Firefox unsupported inline viewer fallbacks and HTML MIME control: " + version);
  if (verifyMacHandoff) console.log(
    "PASS Firefox-downloaded PDF safe-opening and quarantine scenarios on macOS"
  );
} catch (error) {
  console.error("Firefox isolated download diagnostics:", stderrTail);
  throw error;
} finally {
  if (sessionId) {
    try {
      await webdriver("DELETE", "/session/" + sessionId, undefined, 6000);
    } catch { /* Still dispose the temporary process and profile. */ }
  }
  if (processHandle && processHandle.exitCode === null) {
    processHandle.kill("SIGTERM");
  }
  await delay(300);
  if (processHandle && processHandle.exitCode === null) {
    processHandle.kill("SIGKILL");
  }
  if (listening) await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
