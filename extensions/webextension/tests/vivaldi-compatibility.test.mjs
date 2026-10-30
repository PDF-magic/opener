import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createBrowserCompatibility } from "../src/browser-compatibility.js";
import { getBrowserCapabilityFlags } from "../src/browser-capabilities.js";

const root = fileURLToPath(new URL("../", import.meta.url));
const text = (path) => readFile(join(root, path), "utf8");
const json = async (path) => JSON.parse(await text(path));

test("Vivaldi uses the Chrome Chromium MV3 build with no extra privileges", async () => {
  const source = await json("manifest.json");
  const built = await json("dist/manifest.json");
  assert.deepEqual(built, source);
  assert.equal(built.manifest_version, 3);
  assert.equal(built.incognito, "not_allowed");
  assert.deepEqual(built.permissions, []);
  assert.deepEqual(built.host_permissions, []);
  assert.deepEqual(built.optional_permissions, ["downloads"]);
  for (const forbidden of [
    "optional_host_permissions", "content_scripts", "externally_connectable",
    "web_accessible_resources", "nativeMessaging"
  ]) assert.equal(Object.hasOwn(built, forbidden), false, forbidden);
  assert.deepEqual(built.background, { service_worker: "background.js", type: "module" });
  assert.equal(built.action.default_popup, "popup.html");
  assert.equal(built.action.default_title, "PDF Magic Opener (not active)");
});

test("Vivaldi receives the unchanged inactive popup, worker and original icons", async () => {
  assert.equal(await text("dist/background.js"), await text("src/background.js"));
  assert.ok((await text("dist/background.js")).trimEnd().endsWith("void 0;"));
  const popup = await text("dist/popup.html");
  assert.equal(popup, await text("src/popup.html"));
  assert.match(popup, /Not active/);
  assert.match(popup, /id="scanPDF"[^>]*disabled[^>]*aria-disabled="true"/);
  assert.match(popup, /Scan PDF is unavailable until a verified native scanner is connected/);
  assert.equal(await text("dist/popup.css"), await text("src/popup.css"));
  const manifest = await json("dist/manifest.json");
  for (const size of [16, 32, 48, 128]) {
    const path = manifest.icons[String(size)];
    assert.equal(path, "icons/icon-" + size + ".png");
    assert.deepEqual(await readFile(join(root, "dist", path)),
      await readFile(join(root, path)));
  }
});

test("Vivaldi-style Chromium runtime detection does not enable scanner privileges", () => {
  const runtime = {
    getManifest: () => ({ name: "PDF Magic Opener" }),
    getURL: (path) => "chrome-extension://abcdefghijklmnopabcdefghijklmnop/" + path
  };
  const adapter = createBrowserCompatibility({ chrome: { runtime } });
  assert.equal(adapter.namespace, "chrome");
  assert.deepEqual(adapter.getManifest(), { name: "PDF Magic Opener" });
  assert.match(adapter.getResourceURL("popup.html"), /^chrome-extension:/);
  const flags = getBrowserCapabilityFlags({ runtime });
  assert.equal(flags.runtimeMetadataApi, true);
  assert.equal(flags.runtimeMessagingApi, false);
  assert.equal(flags.downloadEventsApi, false);
  assert.equal(flags.nativeMessagingEnabled, false);
  assert.equal(flags.pdfOpeningEnabled, false);
  assert.equal(flags.scannerVerificationEnabled, false);
  assert.ok(Object.isFrozen(flags));
});

test("Vivaldi workflow uses the real installed browser with disposable profile", async () => {
  const workflow = await text("../../.github/workflows/vivaldi-webextension.yml");
  for (const phrase of [
    "repo.vivaldi.com/archive/deb/", "linux_signing_key.pub",
    "vivaldi-stable", "signed-by=", "xvfb-run",
    "node scripts/smoke-vivaldi.mjs"
  ]) assert.ok(workflow.includes(phrase), phrase);
  const smoke = await text("scripts/smoke-vivaldi.mjs");
  for (const phrase of [
    "Extensions.loadUnpacked", "/usr/bin/vivaldi-stable", "--remote-debugging-pipe",
    "--enable-unsafe-extension-debugging", "Target.createTarget", "chrome.runtime.getManifest",
    "chrome.permissions.contains", "scan.disabled", "mkdtemp(", "browser.kill",
    "rm(profile"
  ]) assert.ok(smoke.includes(phrase), phrase);
  for (const forbidden of [
    "chromium.launch(", "sendNativeMessage(", "downloads.open(",
    "chrome.tabs.create(", "window.open("
  ]) assert.equal(smoke.includes(forbidden), false, forbidden);
  const doc = await text("vivaldi/README.md");
  assert.match(doc, /actual Vivaldi|real Vivaldi/i);
  assert.match(doc, /CI/);
});
