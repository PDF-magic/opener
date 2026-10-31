// Actual Brave-stable WebExtensions smoke test (opener-0599).
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
const binary = process.env.BRAVE_BROWSER_PATH || "/usr/bin/brave-browser";
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-brave-test-"));
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

  // A real Brave binary is required. Playwright's Chromium driver only
  // automates Brave; it does not substitute bundled Chromium for this test.
  context = await chromium.launchPersistentContext(profile, {
    executablePath: binary,
    headless: true,
    args: [
      "--disable-extensions-except=" + extensionPath,
      "--load-extension=" + extensionPath,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking"
    ],
    timeout: 45000
  });

  const worker = context.serviceWorkers().find(
    (candidate) => candidate.url().startsWith("chrome-extension://")
  ) ?? await context.waitForEvent("serviceworker", {
    predicate: (candidate) => candidate.url().startsWith("chrome-extension://"),
    timeout: 30000
  });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/, "Brave must load an actual unpacked MV3 extension");

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
  assert.equal(response?.status(), 200, "Brave must render the bundled popup");
  assert.equal(await popup.locator("#popup-title").innerText(), "PDF Magic Opener");
  assert.equal(await popup.locator(".heading .status").innerText(), "Not active");
  assert.equal(await popup.locator("#explicitPdfScanResult").innerText(),
    "No verified scan result is available.");
  assert.match(await popup.locator("#availability-title").innerText(),
    /Browser integration is not enabled/);
  const scanButton = popup.locator("#scanPDF");
  assert.equal(await scanButton.isDisabled(), true, "No unverified PDF scan in Brave");
  assert.equal(await scanButton.getAttribute("aria-disabled"), "true");
  assert.match(await popup.locator("#scanPDFUnavailable").innerText(),
    /verified native scanner/);
  assert.equal(await popup.locator("#openPDFMagicPreferences").getAttribute("href"),
    "pdfmagicopener://preferences");
  assert.equal(await popup.locator('link[rel="stylesheet"]').getAttribute("href"),
    "popup.css");
  assert.deepEqual(errors, [], "Brave popup must not raise page errors");

  // No download, native-messaging, site or private-window privilege is granted
  // by extension installation. This API queries current permission state only.
  const downloadsGranted = await worker.evaluate(async () =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  );
  assert.equal(downloadsGranted, false,
    "Brave must not silently grant the optional downloads permission");

  // opener-0812: Call a real privileged browser API while permission is
  // absent. This is an API refusal, NOT a simulated false grant and NOT an
  // interactive permission prompt. No downloads are started or inspected.
  // Some Brave/Chromium versions hide the API entirely without a grant;
  // others expose it and reject calls through runtime.lastError.
  const deniedDownloadAccess = await worker.evaluate(async () => {
    if (typeof chrome.downloads?.search !== "function") {
      return { outcome: "unavailable" };
    }
    return await new Promise((resolve) => {
      try {
        chrome.downloads.search({}, () => {
          const denied = Boolean(chrome.runtime.lastError);
          resolve({ outcome: denied ? "denied" : "unexpected-access" });
        });
      } catch {
        resolve({ outcome: "denied" });
      }
    });
  });
  assert.ok(["denied", "unavailable"].includes(deniedDownloadAccess.outcome),
    "Brave must reject downloads API usage without optional permission");

  // The failed privileged call must not prompt, upgrade permissions, open a
  // PDF, or change the extension's originally inactive scanner controls.
  const grantsAfterDenial = await worker.evaluate(async () => {
    const current = await chrome.permissions.getAll();
    return {
      downloadsGranted: await chrome.permissions.contains({
        permissions: ["downloads"]
      }),
      permissions: current.permissions,
      origins: current.origins
    };
  });
  assert.equal(grantsAfterDenial.downloadsGranted, false);
  assert.deepEqual(grantsAfterDenial.permissions, []);
  assert.deepEqual(grantsAfterDenial.origins, []);
  assert.equal(await scanButton.isDisabled(), true);
  assert.equal(await popup.locator(".heading .status").innerText(), "Not active");
  assert.equal(await popup.locator("#explicitPdfScanResult").innerText(),
    "No verified scan result is available.");
  assert.deepEqual(errors, [], "Denied browser privileges cannot break the popup");

  console.log("Brave MV3 smoke passed: absent downloads permission denied real API access; Scan PDF disabled.");
} finally {
  try { await context?.close(); } finally {
    await rm(profile, { recursive: true, force: true });
  }
}
