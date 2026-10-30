import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const get = (path) => readFile(join(root, path), "utf8");
const json = async (path) => JSON.parse(await get(path));

test("Opera uses the validated, unpacked Chromium MV3 build without extra privileges", async () => {
  const source = await json("manifest.json");
  const built = await json("dist/manifest.json");
  assert.deepEqual(built, source);
  assert.equal(built.manifest_version, 3);
  assert.equal(built.incognito, "not_allowed");
  assert.deepEqual(built.permissions, []);
  assert.deepEqual(built.host_permissions, []);
  assert.deepEqual(built.optional_permissions, ["downloads"]);
  for (const forbidden of ["optional_host_permissions", "content_scripts",
    "externally_connectable", "web_accessible_resources"]) {
    assert.equal(Object.hasOwn(built, forbidden), false, forbidden);
  }
  assert.deepEqual(built.background,
    { service_worker: "background.js", type: "module" });
  assert.equal(built.action.default_popup, "popup.html");
  assert.equal(built.action.default_title, "PDF Magic Opener (not active)");
});

test("Opera gets the same inert popup and background assets as the shared build", async () => {
  const worker = await get("dist/background.js");
  assert.equal(worker, await get("src/background.js"));
  assert.ok(worker.trimEnd().endsWith("void 0;"));
  const popup = await get("dist/popup.html");
  assert.equal(popup, await get("src/popup.html"));
  assert.match(popup, /<h1 id="popup-title">PDF Magic Opener<\/h1>/);
  assert.match(popup, /Not active/);
  assert.match(popup, /id="scanPDF"[^>]*disabled[^>]*aria-disabled="true"/);
  assert.match(popup, /Scan PDF is unavailable until a verified native scanner is connected/);
  assert.equal(await get("dist/popup.css"), await get("src/popup.css"));
});

test("Opera CI uses the actual stable browser, not a Chromium-only approximation", async () => {
  const smoke = await get("scripts/smoke-opera.mjs");
  for (const requirement of [
    "playwright-core", "/usr/bin/opera", "launchPersistentContext",
    "--load-extension=", "serviceWorkers()", "chrome.runtime.getManifest",
    "chrome.permissions.contains", "isDisabled()", "mkdtemp(", "context?.close()",
    "rm(profile"
  ]) assert.ok(smoke.includes(requirement), requirement);
  assert.ok(!smoke.includes("chromium.launch("),
    "Use Opera's executable, not the bundled test browser");
  assert.ok(!smoke.includes("sendNativeMessage("),
    "Opera smoke must not contact the native scanner");
  const profile = await get("opera/README.md");
  assert.match(profile, /real Opera|actual Opera/i);
  assert.match(profile, /CI/);
});
