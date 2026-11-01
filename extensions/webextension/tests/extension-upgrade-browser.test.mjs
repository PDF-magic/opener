import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("real Chromium extension upgrade regression is mandatory in browser CI", async () => {
  const workflow = await readFile(
    new URL("../../../.github/workflows/chromium-webextension.yml", import.meta.url), "utf8"
  );
  assert.match(workflow, /node scripts\/test-extension-upgrade\.mjs/);
  assert.match(workflow, /CHROMIUM_BINARY_PATH:/);
  assert.match(workflow, /playwright-core@1\.56\.1/);
});

test("upgrade smoke uses an isolated browser and only synthetic preferences", async () => {
  const script = await readFile(
    new URL("../scripts/test-extension-upgrade.mjs", import.meta.url), "utf8"
  );
  for (const required of [
    "launchPersistentContext(profile", "const profile = join(rootDir",
    "const extension = join(rootDir", "const previousVersion = \"0.0.0\"",
    "localStorage.setItem", "localStorage.getItem", "assert.equal(extensionId, originalId",
    "chrome.runtime.getManifest()", "chrome.permissions.contains",
    "assert.equal(await popup.locator(\"#scanPDF\").isDisabled(), true)",
    "await rm(rootDir", "await inspect(manifest.version, id)"
  ]) assert.ok(script.includes(required), "Missing upgrade assertion: " + required);
  for (const forbidden of [
    "chrome.permissions.request", "chrome.runtime.reload", "sendNativeMessage(",
    "connectNative(", "scan-and-open", "window.open(",
    "https://example.com", "process.env.HOME"
  ]) assert.equal(script.includes(forbidden), false, forbidden);
});
