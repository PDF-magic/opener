// Actual Opera-stable WebExtensions smoke test (opener-0603).
// Run only in CI/manual testing after building the validated unpacked extension.
// The profile is isolated and disposed; no PDF files, user browsing data,
// native scanner or installed browser preferences are touched.
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const root = fileURLToPath(new URL("../", import.meta.url));
const extensionPath = resolve(root, "dist");
const binary = process.env.OPERA_BROWSER_PATH || "/usr/bin/opera";
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-opera-test-"));
let context;
try {
  const sourceManifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  const builtManifest = JSON.parse(await readFile(join(extensionPath, "manifest.json"), "utf8"));
  assert.deepEqual(builtManifest, sourceManifest);
  assert.equal(builtManifest.manifest_version, 3);
  assert.equal(builtManifest.incognito, "not_allowed");
  assert.deepEqual(builtManifest.permissions, []);
  assert.deepEqual(builtManifest.host_permissions, []);
  assert.deepEqual(builtManifest.optional_permissions, ["downloads"]);
  assert.equal(builtManifest.optional_host_permissions, undefined);

  // Playwright does not officially support Opera. Use the actual Opera
  // executable and treat launch/protocol incompatibilities as test failures.
  context = await chromium.launchPersistentContext(profile, {
    executablePath: binary,
    headless: false,
    args: [
      "--disable-extensions-except=" + extensionPath,
      "--load-extension=" + extensionPath,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking"
    ],
    timeout: 60000
  });

  const worker = context.serviceWorkers().find(
    (candidate) => candidate.url().startsWith("chrome-extension://")
  ) ?? await context.waitForEvent("serviceworker", {
    predicate: (candidate) => candidate.url().startsWith("chrome-extension://"),
    timeout: 45000
  });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/, "Opera must load an actual unpacked MV3 extension");

  const effectiveManifest = await worker.evaluate(() => chrome.runtime.getManifest());
  assert.equal(effectiveManifest.name, "PDF Magic Opener");
  assert.equal(effectiveManifest.incognito, "not_allowed");
  assert.deepEqual(effectiveManifest.permissions, []);
  assert.deepEqual(effectiveManifest.host_permissions, []);
  assert.deepEqual(effectiveManifest.optional_permissions, ["downloads"]);
  assert.equal(effectiveManifest.optional_host_permissions, undefined);

  const popup = await context.newPage();
  const errors = [];
  popup.on("pageerror", (error) => errors.push(error.message));
  const response = await popup.goto(
    "chrome-extension://" + extensionId + "/popup.html", { waitUntil: "load" }
  );
  assert.equal(response?.status(), 200, "Opera must render the bundled popup");
  assert.equal(await popup.locator("#popup-title").innerText(), "PDF Magic Opener");
  assert.equal(await popup.locator('[role="status"]').innerText(), "Not active");
  assert.match(await popup.locator("#availability-title").innerText(),
    /Browser integration is not enabled/);
  const scanButton = popup.locator("#scanPDF");
  assert.equal(await scanButton.isDisabled(), true, "No unverified PDF scan in Opera");
  assert.equal(await scanButton.getAttribute("aria-disabled"), "true");
  assert.match(await popup.locator("#scanPDFUnavailable").innerText(),
    /verified native scanner/);
  assert.equal(await popup.locator("#openPDFMagicPreferences").getAttribute("href"),
    "pdfmagicopener://preferences");
  assert.equal(await popup.locator('link[rel="stylesheet"]').getAttribute("href"),
    "popup.css");
  assert.deepEqual(errors, [], "Opera popup must not raise page errors");

  // No download, native-messaging, site or private-window privilege is granted
  // by extension installation. This API queries current permission state only.
  const downloadsGranted = await worker.evaluate(async () =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  );
  assert.equal(downloadsGranted, false,
    "Opera must not silently grant the optional downloads permission");

  console.log("Opera MV3 smoke passed: loaded worker and popup; privileges absent; Scan PDF disabled.");
} finally {
  try { await context?.close(); } finally {
    await rm(profile, { recursive: true, force: true });
  }
}
