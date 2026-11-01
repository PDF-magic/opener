// Real Chromium extension version-upgrade regression (opener-1067).
// Only a copied, inert unpacked extension and disposable browser profile are used.
// Browser-store delivery and the inactive native app are intentionally out of scope.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const root = fileURLToPath(new URL("../", import.meta.url));
const executablePath = process.env.CHROMIUM_BINARY_PATH;
assert.ok(executablePath, "CHROMIUM_BINARY_PATH must identify unbranded Chromium");
assert.match(execFileSync(executablePath, ["--version"], {
  encoding: "utf8", timeout: 10000
}).trim(), /^Chromium\s+\d+/, "Do not substitute branded Chrome");

const manifest = JSON.parse(await readFile(join(root, "dist/manifest.json"), "utf8"));
const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
assert.deepEqual(manifest, source, "Only a built, reviewed manifest may be tested");
assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
assert.notEqual(manifest.version, "0.0.0", "A previous version is needed");
assert.deepEqual(manifest.permissions, []);
assert.deepEqual(manifest.host_permissions, []);
assert.deepEqual(manifest.optional_permissions, ["downloads"]);
assert.equal(manifest.incognito, "not_allowed");

const rootDir = await mkdtemp(join(tmpdir(), "pdfmagic-extension-upgrade-"));
const extension = join(rootDir, "extension");
const profile = join(rootDir, "browser-profile");
const installedManifest = join(extension, "manifest.json");
const previousVersion = "0.0.0";
const sentinel = Object.freeze({
  viewer: "fixture-user-chosen-viewer",
  protection: "fixture-user-chosen-protection"
});
let context;

async function inspect(version, originalId = null, saveFixture = false) {
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

  const isOurWorker = (item) =>
    /^chrome-extension:\/\/[a-p]{32}\/background\.js$/.test(item.url());
  const worker = context.serviceWorkers().find(isOurWorker) ??
    await context.waitForEvent("serviceworker", {
      predicate: isOurWorker, timeout: 30000
    });
  const extensionId = new URL(worker.url()).host;
  assert.match(extensionId, /^[a-p]{32}$/);
  if (originalId !== null) {
    assert.equal(extensionId, originalId, "Upgrade must retain the extension identity");
  }

  // Runtime initialization can trail the worker event on loaded CI runners.
  let ready = false;
  for (let i = 0; i < 30; i++) {
    ready = await worker.evaluate(() =>
      typeof globalThis.chrome?.runtime?.getManifest === "function" &&
      typeof globalThis.chrome?.permissions?.contains === "function"
    );
    if (ready) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(ready, "Chromium extension APIs must initialize");
  const actual = await worker.evaluate(() => chrome.runtime.getManifest());
  assert.equal(actual.version, version, "Real Chromium must load the changed version");
  assert.equal(actual.name, "PDF Magic Opener");
  assert.equal(actual.incognito, "not_allowed");
  assert.deepEqual(actual.permissions, []);
  assert.deepEqual(actual.host_permissions, []);
  assert.deepEqual(actual.optional_permissions, ["downloads"]);
  assert.equal(await worker.evaluate(() =>
    chrome.permissions.contains({ permissions: ["downloads"] })
  ), false, "An upgrade cannot grant optional downloads access");

  const popup = await context.newPage();
  const errors = [];
  popup.on("pageerror", (error) => errors.push(error.message));
  const response = await popup.goto(
    "chrome-extension://" + extensionId + "/popup.html", { waitUntil: "load" }
  );
  assert.equal(response?.status(), 200);
  assert.match(await popup.locator(".heading .status").innerText(), /Not active/);
  assert.equal(await popup.locator("#scanPDF").isDisabled(), true);
  assert.equal(await popup.locator("#scanPDF").getAttribute("aria-disabled"), "true");
  assert.equal(await popup.locator("#explicitPdfScanResult").innerText(),
    "No verified scan result is available.");
  assert.equal(await popup.locator("script").count(), 0);
  assert.equal(await popup.locator("iframe").count(), 0);
  assert.deepEqual(errors, []);

  // Synthetic extension-origin preference markers: never user or native-app data.
  // A browser restart and unpacked version change must not wipe this origin.
  const stored = await popup.evaluate(({ save, fixture }) => {
    if (save) {
      localStorage.setItem("pdfmagic-test-viewer", fixture.viewer);
      localStorage.setItem("pdfmagic-test-protection", fixture.protection);
    }
    return {
      viewer: localStorage.getItem("pdfmagic-test-viewer"),
      protection: localStorage.getItem("pdfmagic-test-protection")
    };
  }, { save: saveFixture, fixture: sentinel });
  assert.deepEqual(stored, sentinel, "Upgrade must preserve browser-origin preferences");
  await context.close();
  context = null;
  return extensionId;
}

try {
  await cp(join(root, "dist"), extension, { recursive: true });
  await writeFile(installedManifest, JSON.stringify({
    ...manifest, version: previousVersion
  }, null, 2) + "\n", "utf8");
  const id = await inspect(previousVersion, null, true);
  await writeFile(installedManifest, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  await inspect(manifest.version, id);
  // Reopening the *same* installed version cannot reset user choice either.
  await inspect(manifest.version, id);
  console.log("PASS real Chromium unpacked extension upgrade " +
    previousVersion + " -> " + manifest.version + " preserves state and gates");
} finally {
  try { await context?.close(); } finally {
    await rm(rootDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}
