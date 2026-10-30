// Real Arc for macOS WebExtensions compatibility smoke (opener-0604).
// Uses only the built, inactive local MV3 extension in a disposable Arc profile.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const root = fileURLToPath(new URL("../", import.meta.url));
const extensionPath = resolve(root, "dist");
const appPath = process.env.ARC_APP_PATH || "/Applications/Arc.app";
const executablePath = join(appPath, "Contents", "MacOS", "Arc");

// Arc is a distinct signed macOS browser, not Chrome renamed. Before running
// Chromium automation against it, verify its actual installed app identity.
const bundleIdentifier = execFileSync("/usr/libexec/PlistBuddy", [
  "-c", "Print :CFBundleIdentifier", join(appPath, "Contents", "Info.plist")
], { encoding: "utf8", timeout: 10000 }).trim();
assert.equal(bundleIdentifier, "company.thebrowser.Browser",
  "The test requires the real Arc browser application");

const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
const manifest = JSON.parse(await readFile(join(extensionPath, "manifest.json"), "utf8"));
assert.deepEqual(manifest, source);
assert.equal(manifest.manifest_version, 3);
assert.equal(manifest.incognito, "not_allowed");
assert.deepEqual(manifest.permissions, []);
assert.deepEqual(manifest.host_permissions, []);
assert.deepEqual(manifest.optional_permissions, ["downloads"]);
assert.equal(manifest.content_scripts, undefined);
assert.equal(manifest.optional_host_permissions, undefined);
assert.deepEqual(manifest.background, { service_worker: "background.js", type: "module" });

const profile = await mkdtemp(join(tmpdir(), "pdfmagic-arc-smoke-"));
let context;
try {
  context = await chromium.launchPersistentContext(profile, {
    executablePath,
    headless: true,
    args: [
      "--disable-extensions-except=" + extensionPath,
      "--load-extension=" + extensionPath,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-sync",
      "--disable-component-update"
    ],
    timeout: 60000
  });

  // Do not pass if Arc only opens a first-run/sign-in screen: a real
  // registered extension service worker is mandatory evidence of support.
  const worker = context.serviceWorkers().find((item) =>
    /^chrome-extension:\/\/[a-p]{32}\/background\.js$/.test(item.url())
  ) ?? await context.waitForEvent("serviceworker", {
    predicate: (item) => /^chrome-extension:\/\/[a-p]{32}\/background\.js$/.test(item.url()),
    timeout: 30000
  });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/);

  const effectiveManifest = await worker.evaluate(() => chrome.runtime.getManifest());
  assert.equal(effectiveManifest.name, "PDF Magic Opener");
  assert.equal(effectiveManifest.incognito, "not_allowed");
  assert.deepEqual(effectiveManifest.background, manifest.background);
  assert.deepEqual(effectiveManifest.permissions, []);
  assert.deepEqual(effectiveManifest.host_permissions, []);
  assert.deepEqual(effectiveManifest.optional_permissions, ["downloads"]);

  const optionalGranted = await worker.evaluate(() =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  );
  assert.equal(optionalGranted, false, "Arc must not silently grant optional downloads access");

  // The only navigation is to this extension's bundled local popup. The
  // external preferences URL is inspected, not clicked or launched.
  const popup = await context.newPage();
  const pageErrors = [];
  popup.on("pageerror", (error) => pageErrors.push(error.message));
  const response = await popup.goto(
    "chrome-extension://" + extensionId + "/popup.html", { waitUntil: "load" }
  );
  assert.equal(response?.status(), 200, "Arc must render the unpacked extension popup");
  assert.equal(await popup.locator("#popup-title").innerText(), "PDF Magic Opener");
  assert.match(await popup.locator('[role="status"]').innerText(), /Not active/);
  assert.match(await popup.locator("body").innerText(),
    /cannot scan, sanitize, or open PDF files yet/);
  assert.equal(await popup.locator("#scanPDF").isDisabled(), true);
  assert.equal(await popup.locator("#scanPDF").getAttribute("aria-disabled"), "true");
  assert.equal(await popup.locator("#openPDFMagicPreferences").getAttribute("href"),
    "pdfmagicopener://preferences");
  assert.equal(await popup.locator('link[rel="stylesheet"]').getAttribute("href"), "popup.css");
  assert.equal(await popup.locator("script").count(), 0);
  assert.ok(await popup.evaluate(() => document.styleSheets.length) >= 1);
  assert.deepEqual(pageErrors, []);
  console.log("PASS actual Arc for macOS MV3 worker, inactive popup, optional-permission gate");
} finally {
  try { await context?.close(); } finally {
    await rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}
