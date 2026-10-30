import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (name) => JSON.parse(await readFile(join(root, name), "utf8"));

test("Chromium source and unpacked MV3 output use identical safe metadata", async () => {
  const source = await load("manifest.json");
  const built = await load("dist/manifest.json");
  assert.deepEqual(built, source);
  assert.equal(built.manifest_version, 3);
  assert.equal(built.incognito, "not_allowed");
  assert.deepEqual(built.background, { service_worker: "background.js", type: "module" });
  assert.deepEqual(built.permissions, []);
  assert.deepEqual(built.host_permissions, []);
  assert.deepEqual(built.optional_permissions, ["downloads"]);
  for (const forbidden of [
    "content_scripts", "optional_host_permissions", "externally_connectable",
    "web_accessible_resources", "nativeMessaging"
  ]) assert.equal(Object.hasOwn(built, forbidden), false, forbidden);
});

test("Chromium action, popup and PNG assets are packaged byte-for-byte", async () => {
  const manifest = await load("dist/manifest.json");
  assert.equal(manifest.action.default_popup, "popup.html");
  assert.equal(manifest.action.default_title, "PDF Magic Opener (not active)");
  for (const asset of [
    "background.js", "popup.html", "popup.css",
    "icons/icon-16.png", "icons/icon-32.png", "icons/icon-48.png", "icons/icon-128.png"
  ]) {
    const source = asset === "background.js"
      ? join(root, "src", asset)
      : asset.startsWith("icons/") ? join(root, asset) : join(root, "src", asset);
    assert.deepEqual(await readFile(join(root, "dist", asset)), await readFile(source));
  }
});

test("Chromium runtime smoke is isolated from production dependencies and files", async () => {
  const pkg = await load("package.json");
  assert.equal(pkg.dependencies, undefined);
  assert.equal(pkg.devDependencies, undefined);
  const script = await readFile(join(root, "scripts/test-chromium.mjs"), "utf8");
  assert.ok(script.includes("launchPersistentContext"));
  assert.ok(script.includes("--load-extension="));
  assert.ok(script.includes('chrome.permissions.contains({ permissions: ["downloads"] })'));
  assert.ok(script.includes("assert.equal(downloadsGranted, false"));
  assert.ok(script.includes('assert.equal(await popup.locator("#scanPDF").isDisabled(), true)'));
  assert.ok(script.includes("await rm(profile"));
  for (const unsafe of ["sendNativeMessage(", "connectNative(", "permissions.request(", "fetch(", "https://example.com"]) {
    assert.equal(script.includes(unsafe), false, unsafe);
  }
});
