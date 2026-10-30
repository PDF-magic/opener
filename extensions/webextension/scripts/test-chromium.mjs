// Real unbranded Chromium WebExtensions compatibility smoke (opener-0601).
// Disposable browser profile; never scans, requests grants or visits websites.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const root = fileURLToPath(new URL("../", import.meta.url));
const extension = resolve(root, "dist");
const executablePath = process.env.CHROMIUM_BINARY_PATH;
assert.ok(executablePath, "CHROMIUM_BINARY_PATH must select a real Chromium browser");
const version = execFileSync(executablePath, ["--version"], {
  encoding: "utf8", timeout: 10000
}).trim();
assert.match(version, /^Chromium\s+\d+/, "Must use unbranded Chromium, not Google Chrome");

const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
const manifest = JSON.parse(await readFile(join(extension, "manifest.json"), "utf8"));
assert.deepEqual(manifest, source);
assert.equal(manifest.manifest_version, 3);
assert.equal(manifest.incognito, "not_allowed");
assert.deepEqual(manifest.permissions, []);
assert.deepEqual(manifest.host_permissions, []);
assert.deepEqual(manifest.optional_permissions, ["downloads"]);
assert.equal(manifest.optional_host_permissions, undefined);
assert.equal(manifest.content_scripts, undefined);
assert.deepEqual(manifest.background, {
  service_worker: "background.js", type: "module"
});

const profile = await mkdtemp(join(tmpdir(), "pdfmagic-chromium-smoke-"));
let context;
try {
  context = await chromium.launchPersistentContext(profile, {
    executablePath,
    headless: true,
    args: [
      "--disable-extensions-except=" + extension,
      "--load-extension=" + extension,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-sync"
    ],
    timeout: 45000
  });

  const worker = context.serviceWorkers().find((item) =>
    /^chrome-extension:\/\/[a-p]{32}\/background\.js$/.test(item.url())
  ) ?? await context.waitForEvent("serviceworker", {
    predicate: (item) =>
      /^chrome-extension:\/\/[a-p]{32}\/background\.js$/.test(item.url()),
    timeout: 30000
  });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/);

  // The worker event can precede extension API initialization on busy runners.
  // Wait briefly for the real runtime and permission APIs, never skipping checks.
  let runtimeReady = false;
  for (let attempt = 0; attempt < 30; attempt++) {
    runtimeReady = await worker.evaluate(() =>
      typeof globalThis.chrome?.runtime?.getManifest === "function" &&
      typeof globalThis.chrome?.permissions?.contains === "function"
    );
    if (runtimeReady) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(runtimeReady, "Chromium extension APIs must be initialized");
  const effectiveManifest = await worker.evaluate(() => chrome.runtime.getManifest());
  assert.equal(effectiveManifest.name, "PDF Magic Opener");
  assert.equal(effectiveManifest.incognito, "not_allowed");
  assert.deepEqual(effectiveManifest.background, manifest.background);
  assert.deepEqual(effectiveManifest.permissions, []);
  assert.deepEqual(effectiveManifest.host_permissions, []);
  assert.deepEqual(effectiveManifest.optional_permissions, ["downloads"]);

  const downloadsGranted = await worker.evaluate(() =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  );
  assert.equal(downloadsGranted, false, "Optional downloads must not be pregranted");

  const popup = await context.newPage();
  const errors = [];
  popup.on("pageerror", (error) => errors.push(error.message));
  const response = await popup.goto(
    "chrome-extension://" + extensionId + "/popup.html", { waitUntil: "load" }
  );
  assert.equal(response?.status(), 200, "Chromium must render the local popup");
  assert.equal(await popup.locator("#popup-title").innerText(), "PDF Magic Opener");
  assert.match(await popup.locator('[role="status"]').innerText(), /Not active/);
  assert.match(await popup.locator("body").innerText(),
    /cannot scan, sanitize, or open PDF files yet/);
  assert.equal(await popup.locator("#scanPDF").isDisabled(), true);
  assert.equal(await popup.locator("#scanPDF").getAttribute("aria-disabled"), "true");
  assert.equal(await popup.locator("#openPDFMagicPreferences").getAttribute("href"),
    "pdfmagicopener://preferences");
  assert.equal(await popup.locator('link[rel="stylesheet"]').getAttribute("href"),
    "popup.css");
  assert.equal(await popup.locator("script").count(), 0);
  assert.equal(await popup.locator("iframe").count(), 0);
  assert.ok(await popup.evaluate(() => document.styleSheets.length) >= 1,
    "Chromium must load the local stylesheet");
  assert.deepEqual(errors, [], "The popup must not raise JavaScript errors");
  console.log("PASS Chromium MV3 worker, popup and permission boundary: " + version);
} finally {
  try { await context?.close(); } finally {
    await rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}
