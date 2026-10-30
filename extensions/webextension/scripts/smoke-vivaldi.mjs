// Real Vivaldi Stable extension smoke (opener-0602).
// Launch the official browser directly, rather than via Playwright's generic
// Chromium launch flags, in a disposable isolated CI-only profile.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const root = fileURLToPath(new URL("../", import.meta.url));
const extensionPath = resolve(root, "dist");
const executablePath = process.env.VIVALDI_BROWSER_PATH || "/usr/bin/vivaldi-stable";
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-vivaldi-"));
const pause = (ms) => new Promise((done) => setTimeout(done, ms));
let browser;
let processHandle;
let processError = "";
try {
  const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  const packaged = JSON.parse(await readFile(join(extensionPath, "manifest.json"), "utf8"));
  assert.deepEqual(packaged, source);
  assert.equal(packaged.manifest_version, 3);
  assert.equal(packaged.incognito, "not_allowed");
  assert.deepEqual(packaged.permissions, []);
  assert.deepEqual(packaged.host_permissions, []);
  assert.deepEqual(packaged.optional_permissions, ["downloads"]);
  assert.equal(packaged.optional_host_permissions, undefined);
  assert.deepEqual(packaged.background,
    { service_worker: "background.js", type: "module" });

  // Vivaldi is not stock Chromium: Chromium launch defaults can disable its
  // extension engine or crash the Vivaldi UI. Start the actual binary with
  // only the arguments this isolated smoke test needs, then attach via CDP.
  // The debug port listens on loopback only; nothing is exposed externally.
  processHandle = spawn(executablePath, [
    "--user-data-dir=" + profile,
    "--remote-debugging-port=0",
    "--remote-debugging-address=127.0.0.1",
    "--disable-extensions-except=" + extensionPath,
    "--load-extension=" + extensionPath,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
    "about:blank"
  ], { stdio: ["ignore", "ignore", "pipe"] });
  processHandle.on("error", (error) => { processError = error.message; });
  processHandle.stderr.on("data", (data) => {
    processError = (processError + data.toString("utf8")).slice(-5000);
  });

  let port;
  for (let i = 0; i < 160; i++) {
    if (processHandle.exitCode !== null || processHandle.signalCode !== null) {
      throw new Error("Vivaldi exited before debugging started: " +
        processHandle.exitCode + " / " + processHandle.signalCode +
        " / " + processError.slice(-1500));
    }
    try {
      const data = await readFile(join(profile, "DevToolsActivePort"), "utf8");
      const candidate = Number(data.split("\n")[0]);
      if (Number.isInteger(candidate) && candidate > 0 && candidate < 65536) {
        port = candidate;
        break;
      }
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
    await pause(200);
  }
  if (!port) throw new Error("Vivaldi did not expose its localhost debug port");
  browser = await chromium.connectOverCDP("http://127.0.0.1:" + port,
    { timeout: 20000 });
  const context = browser.contexts()[0];
  assert.ok(context, "Vivaldi must provide a real persistent profile");

  const worker = context.serviceWorkers().find((entry) =>
    entry.url().startsWith("chrome-extension://")) ??
    await context.waitForEvent("serviceworker", {
      predicate: (entry) => entry.url().startsWith("chrome-extension://"),
      timeout: 35000
    });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/,
    "Vivaldi must register the unpacked Manifest V3 extension worker");

  const effective = await worker.evaluate(() => chrome.runtime.getManifest());
  assert.equal(effective.name, "PDF Magic Opener");
  assert.equal(effective.manifest_version, 3);
  assert.equal(effective.incognito, "not_allowed");
  assert.deepEqual(effective.permissions, []);
  assert.deepEqual(effective.host_permissions, []);
  assert.deepEqual(effective.optional_permissions, ["downloads"]);
  assert.equal(effective.optional_host_permissions, undefined);
  assert.equal(effective.action.default_popup, "popup.html");

  const popup = await context.newPage();
  const javascriptErrors = [];
  popup.on("pageerror", (error) => javascriptErrors.push(error.message));
  const response = await popup.goto(
    "chrome-extension://" + extensionId + "/popup.html", { waitUntil: "load" }
  );
  assert.equal(response?.status(), 200, "Vivaldi must render the local popup");
  assert.equal(await popup.locator("#popup-title").innerText(), "PDF Magic Opener");
  assert.equal(await popup.locator('[role="status"]').innerText(), "Not active");
  assert.match(await popup.locator("#availability-title").innerText(),
    /Browser integration is not enabled/);
  const scanButton = popup.locator("#scanPDF");
  assert.equal(await scanButton.isDisabled(), true);
  assert.equal(await scanButton.getAttribute("aria-disabled"), "true");
  assert.equal(await scanButton.getAttribute("aria-describedby"), "scanPDFUnavailable");
  assert.match(await popup.locator("#scanPDFUnavailable").innerText(),
    /verified native scanner/);
  assert.equal(await popup.locator("#openPDFMagicPreferences").getAttribute("href"),
    "pdfmagicopener://preferences");
  assert.equal(await popup.locator('link[rel="stylesheet"]').getAttribute("href"),
    "popup.css");
  assert.equal(await popup.evaluate(() =>
    [...document.styleSheets].some((sheet) => sheet.href?.endsWith("/popup.css"))), true);
  assert.deepEqual(javascriptErrors, []);

  // The optional download permission must not be silently granted.
  const downloadsGranted = await worker.evaluate(async () =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  );
  assert.equal(downloadsGranted, false,
    "Vivaldi must not silently grant optional downloads access");
  console.log("Vivaldi Stable smoke passed: real MV3 worker, inactive popup, no grants.");
} finally {
  try {
    await browser?.close();
  } finally {
    if (processHandle && processHandle.exitCode === null &&
        processHandle.signalCode === null) {
      processHandle.kill("SIGTERM");
      for (let i = 0; i < 20 && processHandle.exitCode === null &&
           processHandle.signalCode === null; i++) await pause(100);
      if (processHandle.exitCode === null && processHandle.signalCode === null) {
        processHandle.kill("SIGKILL");
      }
    }
    await rm(profile, { recursive: true, force: true });
  }
}
