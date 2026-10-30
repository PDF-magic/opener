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
let browser;
let child;
const port = 9223; // Isolated CI machine, loopback only. Never expose CDP externally.
const endpoint = "http://127.0.0.1:" + port;
const { setTimeout: sleep } = await import("node:timers/promises");
try {
  // Arc does not support Playwright's --remote-debugging-pipe launch protocol.
  // Launch the real signed Arc executable, then attach through its supported
  // loopback Chrome DevTools port instead. Do not attach to a user's session.
  child = (await import("node:child_process")).spawn(executablePath, [
    "--remote-debugging-port=" + port,
    "--remote-debugging-address=127.0.0.1",
    "--user-data-dir=" + profile,
    "--disable-extensions-except=" + extensionPath,
    "--load-extension=" + extensionPath,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-component-update",
    "about:blank"
  ], { stdio: "ignore" });

  let started = false;
  for (let i = 0; i < 90; i += 1) {
    if (child.exitCode !== null) throw new Error("Arc terminated before exposing local CDP");
    try {
      const response = await fetch(endpoint + "/json/version", {
        signal: AbortSignal.timeout(700)
      });
      if (response.ok) {
        const info = await response.json();
        assert.match(info.Browser || "", /Chrome|Chromium|Arc/,
          "Debugging endpoint must be provided by a Chromium-family browser");
        started = true;
        break;
      }
    } catch { /* Arc may still be launching */ }
    await sleep(500);
  }
  assert.ok(started, "Real Arc never exposed its local DevTools endpoint");
  browser = await chromium.connectOverCDP(endpoint, { timeout: 15000 });
  const context = browser.contexts()[0];
  assert.ok(context, "Real Arc must expose a browser context");

  // A CDP endpoint alone is insufficient: Arc must register the exact MV3
  // extension worker and render the local popup with no extra permissions.
  // Arc has its own built-in extensions with background.js service workers.
  // Match the actual installed manifest identity, not just a generic worker
  // URL, or the test could accidentally validate Arc's internal extension.
  let worker;
  const inspected = new Set();
  const deadline = Date.now() + 30000;
  while (!worker && Date.now() < deadline) {
    for (const candidate of context.serviceWorkers()) {
      if (!/^chrome-extension:\/\/[a-p]{32}\/background\.js$/.test(candidate.url()) ||
          inspected.has(candidate.url())) continue;
      inspected.add(candidate.url());
      try {
        const metadata = await candidate.evaluate(() => chrome.runtime.getManifest());
        if (metadata?.name === "PDF Magic Opener") {
          worker = candidate;
          break;
        }
      } catch {
        // Other internal workers can shut down independently of our extension.
      }
    }
    if (!worker) await sleep(250);
  }
  assert.ok(worker,
    "Arc did not register PDF Magic Opener's MV3 service worker (other Arc workers do not count)");
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
  console.log("PASS actual Arc MV3 worker, inactive popup and optional permission gate");
} finally {
  try { await browser?.close(); } catch { /* Arc may have already exited */ }
  if (child && child.exitCode === null) child.kill("SIGTERM");
  await sleep(300);
  if (child && child.exitCode === null) child.kill("SIGKILL");
  await rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
