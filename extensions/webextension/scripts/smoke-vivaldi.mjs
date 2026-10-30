// Real Vivaldi Stable extension smoke (opener-0602). No real PDFs, native
// scanner, personal browser profile, permission requests or browsing data.
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const root = fileURLToPath(new URL("../", import.meta.url));
const extensionPath = resolve(root, "dist");
const executablePath = process.env.VIVALDI_BROWSER_PATH || "/usr/bin/vivaldi-stable";
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-vivaldi-"));
let context;
try {
  const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  const packaged = JSON.parse(await readFile(join(extensionPath, "manifest.json"), "utf8"));
  assert.deepEqual(packaged, source, "Vivaldi must load the reviewed Chromium manifest");
  assert.equal(packaged.manifest_version, 3);
  assert.equal(packaged.incognito, "not_allowed");
  assert.deepEqual(packaged.permissions, []);
  assert.deepEqual(packaged.host_permissions, []);
  assert.deepEqual(packaged.optional_permissions, ["downloads"]);
  assert.equal(packaged.optional_host_permissions, undefined);
  assert.deepEqual(packaged.background,
    { service_worker: "background.js", type: "module" });

  // Target the actual installed Vivaldi binary, NOT bundled Chromium.
  // Xvfb permits headed extension loading even when headless flags change.
  const launchOptions = {
    executablePath,
    headless: false,
    // Playwright disables all extensions by default. Vivaldi's own UI and
    // the unpacked MV3 worker both require this single flag to be omitted.
    ignoreDefaultArgs: ["--disable-extensions"],
    args: [
      "--disable-extensions-except=" + extensionPath,
      "--load-extension=" + extensionPath,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-dev-shm-usage"
    ],
    timeout: 45000
  };
  context = await chromium.launchPersistentContext(profile, launchOptions);

  const worker = context.serviceWorkers().find((entry) =>
    entry.url().startsWith("chrome-extension://")) ??
    await context.waitForEvent("serviceworker", {
      predicate: (entry) => entry.url().startsWith("chrome-extension://"),
      timeout: 35000
    });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/,
    "Vivaldi must actually register the Manifest V3 extension worker");

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
  assert.equal(await scanButton.isDisabled(), true,
    "Vivaldi must not enable an unverified scan action");
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

  // An optional manifest permission is NOT a silent effective grant.
  const downloadsGranted = await worker.evaluate(async () =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  );
  assert.equal(downloadsGranted, false,
    "Vivaldi must not grant optional downloads access at installation");

  console.log("Vivaldi Stable smoke passed: real MV3 worker, inert popup, no grants.");
} finally {
  try { await context?.close(); } finally {
    await rm(profile, { recursive: true, force: true });
  }
}
