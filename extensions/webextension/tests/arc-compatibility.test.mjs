import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const readManifest = async (path) =>
  JSON.parse(await readFile(join(root, path), "utf8"));

test("Arc uses the same safe unpacked Chromium MV3 manifest", async () => {
  const source = await readManifest("manifest.json");
  const built = await readManifest("dist/manifest.json");
  assert.deepEqual(built, source);
  assert.equal(built.manifest_version, 3);
  assert.equal(built.incognito, "not_allowed");
  assert.deepEqual(built.permissions, []);
  assert.deepEqual(built.host_permissions, []);
  assert.deepEqual(built.optional_permissions, ["downloads"]);
  assert.equal(built.optional_host_permissions, undefined);
  assert.equal(built.content_scripts, undefined);
  assert.deepEqual(built.background, {
    service_worker: "background.js", type: "module"
  });
  assert.equal(built.action.default_title, "PDF Magic Opener (not active)");
  assert.equal(built.action.default_popup, "popup.html");
});

test("Arc unpacked extension bundles the exact source assets", async () => {
  for (const asset of [
    "background.js", "popup.html", "popup.css",
    "icons/icon-16.png", "icons/icon-32.png",
    "icons/icon-48.png", "icons/icon-128.png"
  ]) {
    const source = asset.startsWith("icons/")
      ? join(root, asset) : join(root, "src", asset);
    assert.deepEqual(await readFile(join(root, "dist", asset)), await readFile(source));
  }
  const popup = await readFile(join(root, "dist/popup.html"), "utf8");
  assert.match(popup, /id="scanPDF"[^>]+disabled/);
  assert.match(popup, /Not active/);
  assert.equal(popup.includes("<script"), false);
  const worker = await readFile(join(root, "dist/background.js"), "utf8");
  assert.equal(worker, "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\nvoid 0;\n");
});

test("Arc real-browser smoke cannot substitute Chrome or mutate user state", async () => {
  const pkg = await readManifest("package.json");
  assert.equal(pkg.dependencies, undefined);
  assert.equal(pkg.devDependencies, undefined);
  const smoke = await readFile(join(root, "scripts/test-arc.mjs"), "utf8");
  assert.ok(smoke.includes('assert.equal(bundleIdentifier, "company.thebrowser.Browser"'));
  assert.ok(smoke.includes("launchPersistentContext(profile"));
  assert.ok(smoke.includes("--load-extension="));
  assert.ok(smoke.includes('chrome.permissions.contains({ permissions: ["downloads"] })'));
  assert.ok(smoke.includes("assert.equal(optionalGranted, false"));
  assert.ok(smoke.includes('popup.locator("#scanPDF").isDisabled()'));
  assert.ok(smoke.includes("await rm(profile"));
  for (const forbidden of [
    "sendNativeMessage(", "connectNative(", "permissions.request(",
    "window.open(", "https://example.com", "node:child_process.exec("
  ]) assert.equal(smoke.includes(forbidden), false, forbidden);
});
