// Actual Opera Stable MV3 smoke test (opener-0603).
// Use Opera's own Chromium DevTools endpoint, not Playwright's unsupported
// Opera launch pipe or a substitute Chromium browser.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const root = fileURLToPath(new URL("../", import.meta.url));
const extensionPath = resolve(root, "dist");
const binary = process.env.OPERA_BROWSER_PATH || "/usr/bin/opera";
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-opera-test-"));
let browser, child;

async function chooseLocalPort() {
  const server = createServer();
  try {
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", resolve);
    });
    return server.address().port;
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

async function waitForDebugging(port) {
  const baseUrl = "http://127.0.0.1:" + port;
  for (let attempt = 0; attempt < 60; attempt++) {
    if (child.exitCode !== null || child.signalCode !== null) break;
    try {
      const response = await fetch(baseUrl + "/json/version", {
        signal: AbortSignal.timeout(500)
      });
      if (response.ok) {
        const info = await response.json();
        if (typeof info.webSocketDebuggerUrl === "string" &&
            info.webSocketDebuggerUrl.startsWith("ws://127.0.0.1:")) {
          return baseUrl;
        }
      }
    } catch {
      // Opera can take time to start; don't infer browser compatibility.
    }
    await delay(250);
  }
  throw new Error("The actual Opera browser did not expose a usable local debugging endpoint");
}

try {
  const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  const built = JSON.parse(await readFile(join(extensionPath, "manifest.json"), "utf8"));
  assert.deepEqual(built, source);
  assert.equal(built.manifest_version, 3);
  assert.equal(built.incognito, "not_allowed");
  assert.deepEqual(built.permissions, []);
  assert.deepEqual(built.host_permissions, []);
  assert.deepEqual(built.optional_permissions, ["downloads"]);
  assert.equal(built.optional_host_permissions, undefined);

  const port = await chooseLocalPort();
  child = spawn(binary, [
    "--user-data-dir=" + profile,
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=" + port,
    "--disable-extensions-except=" + extensionPath,
    "--load-extension=" + extensionPath,
    "--no-sandbox",
    "--disable-background-networking",
    "--no-default-browser-check",
    "--no-first-run",
    "--password-store=basic"
  ], { stdio: ["ignore", "ignore", "ignore"] });
  child.on("error", () => { /* Fail via debugging endpoint and cleanup. */ });

  const debuggingUrl = await waitForDebugging(port);
  browser = await puppeteer.connect({
    browserURL: debuggingUrl,
    defaultViewport: null,
    protocolTimeout: 20000
  });
  // Opera exposes built-in extension workers (e.g. Opera Touch Background).
  // Identify *our* extension by its live manifest, never the first worker.
  const workerTarget = await browser.waitForTarget(async (target) => {
    if (target.type() !== "service_worker" ||
        !target.url().startsWith("chrome-extension://")) return false;
    try {
      const candidate = await target.worker();
      return candidate && await candidate.evaluate(() =>
        chrome.runtime.getManifest().name) === "PDF Magic Opener";
    } catch {
      return false;
    }
  }, { timeout: 30000 });
  const extensionId = new URL(workerTarget.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/,
    "Opera must load an actual unpacked MV3 extension service worker");

  const worker = await workerTarget.worker();
  assert.ok(worker, "Opera must expose a running extension service worker");
  const effective = await worker.evaluate(() => chrome.runtime.getManifest());
  assert.equal(effective.name, "PDF Magic Opener");
  assert.equal(effective.manifest_version, 3);
  assert.equal(effective.incognito, "not_allowed");
  assert.deepEqual(effective.permissions, []);
  assert.deepEqual(effective.host_permissions, []);
  assert.deepEqual(effective.optional_permissions, ["downloads"]);
  assert.equal(effective.optional_host_permissions, undefined);

  const popup = await browser.newPage();
  const errors = [];
  popup.on("pageerror", (error) => errors.push(error.message));
  const response = await popup.goto("chrome-extension://" + extensionId +
    "/popup.html", { waitUntil: "load", timeout: 15000 });
  assert.equal(response?.status(), 200, "Opera must serve the actual extension popup");
  assert.equal(await popup.$eval("#popup-title", (el) => el.textContent.trim()),
    "PDF Magic Opener");
  assert.equal(await popup.$eval('[role="status"]', (el) => el.textContent.trim()),
    "Not active");
  assert.match(await popup.$eval("#availability-title", (el) => el.textContent),
    /Browser integration is not enabled/);
  assert.equal(await popup.$eval("#scanPDF", (el) => el.disabled), true);
  assert.equal(await popup.$eval("#scanPDF", (el) => el.getAttribute("aria-disabled")),
    "true");
  assert.match(await popup.$eval("#scanPDFUnavailable", (el) => el.textContent),
    /verified native scanner/);
  assert.equal(await popup.$eval("#openPDFMagicPreferences", (el) => el.getAttribute("href")),
    "pdfmagicopener://preferences");
  assert.equal(await popup.$eval('link[rel="stylesheet"]', (el) => el.getAttribute("href")),
    "popup.css");
  assert.deepEqual(errors, []);

  const downloadsGranted = await worker.evaluate(() =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  );
  assert.equal(downloadsGranted, false,
    "Opera must not silently grant optional downloads permission");
  console.log("Opera Stable MV3 compatibility verified: worker, popup and permissions.");
} finally {
  try {
    await browser?.close();
  } catch {
    // Still terminate our disposable Opera process.
  }
  if (child && child.exitCode === null && child.signalCode === null) {
    child.kill("SIGTERM");
    await Promise.race([
      new Promise((resolve) => child.once("exit", resolve)),
      delay(1500)
    ]);
    if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
  }
  await rm(profile, { recursive: true, force: true });
}
