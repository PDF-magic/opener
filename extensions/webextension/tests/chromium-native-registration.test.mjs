import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const directory = new URL("../../../native-messaging/", import.meta.url);
const extension = new URL("../manifest.json", import.meta.url);
const built = new URL("../dist/manifest.json", import.meta.url);

const readJson = async (url) => JSON.parse(await readFile(url, "utf8"));

test("native host registration inventory is canonical and contains every supported Chromium-family target", async () => {
  const [inventory, host] = await Promise.all([
    readJson(new URL("chromium-registration-targets.json", directory)),
    readJson(new URL("host-identity.json", directory))
  ]);
  assert.equal(inventory.hostName, host.name);
  assert.equal(inventory.hostName, "org.pdfmagic.opener");
  assert.equal(inventory.platform, "macOS");
  assert.equal(inventory.status, "identification-only");
  assert.deepEqual(inventory.targets.map((entry) => entry.browser), [
    "Google Chrome", "Chromium", "Google Chrome for Testing",
    "Microsoft Edge", "Brave", "Vivaldi", "Arc", "Opera"
  ]);
  assert.equal(new Set(inventory.targets.map((entry) => entry.browser)).size, 8);
  for (const entry of inventory.targets) {
    assert.deepEqual(Object.keys(entry).sort(), [
      "browser", "evidence", "registration", "source", "userManifestDirectory"
    ]);
    assert.equal(entry.userManifestDirectory.startsWith("~/Library/Application Support/"), true);
    assert.equal(entry.userManifestDirectory.endsWith("/NativeMessagingHosts"), true);
    assert.equal(entry.userManifestDirectory.includes(".."), false);
    assert.match(entry.source, /^https:\/\//);
    assert.ok(["publisher-documented", "integration-reference-not-publisher-confirmed"].includes(entry.evidence));
  }
});

test("independent browser lookups are not silently collapsed into Chrome and fallback exceptions remain explicit", async () => {
  const { targets } = await readJson(new URL("chromium-registration-targets.json", directory));
  const byBrowser = new Map(targets.map((target) => [target.browser, target]));
  const chromePath = byBrowser.get("Google Chrome").userManifestDirectory;
  for (const browser of ["Chromium", "Google Chrome for Testing", "Microsoft Edge", "Brave", "Vivaldi", "Arc"]) {
    assert.notEqual(byBrowser.get(browser).userManifestDirectory, chromePath, browser);
  }
  assert.equal(byBrowser.get("Google Chrome for Testing").registration, "separate-since-146");
  assert.equal(byBrowser.get("Opera").registration, "chrome-location-documented");
  assert.equal(byBrowser.get("Opera").userManifestDirectory, chromePath);
  for (const browser of ["Brave", "Vivaldi", "Arc"]) {
    assert.equal(byBrowser.get(browser).registration, "verify-browser-specific");
    assert.equal(byBrowser.get(browser).evidence, "integration-reference-not-publisher-confirmed");
  }
});

test("inventory is reference-only; native messaging and scanner remain disabled in source and built extensions", async () => {
  const [inventory, source, packaged, docs] = await Promise.all([
    readJson(new URL("chromium-registration-targets.json", directory)),
    readJson(extension),
    readJson(built),
    readFile(new URL("chromium-registration.md", directory), "utf8")
  ]);
  assert.equal("allowed_origins" in inventory, false);
  assert.equal("path" in inventory, false);
  assert.equal("type" in inventory, false);
  assert.deepEqual(packaged, source);
  for (const manifest of [source, packaged]) {
    assert.deepEqual(manifest.permissions, []);
    assert.deepEqual(manifest.host_permissions, []);
    assert.deepEqual(manifest.optional_permissions, ["downloads"]);
    assert.equal(manifest.incognito, "not_allowed");
    assert.equal(manifest.permissions.includes("nativeMessaging"), false);
    assert.equal(manifest.optional_permissions.includes("nativeMessaging"), false);
    assert.match(manifest.action.default_title, /not active/);
  }
  assert.match(docs, /no browser native messaging host is registered or enabled/i);
  assert.match(docs, /allowed_origins/);
  assert.match(docs, /ClamAV/);
  for (const target of inventory.targets) {
    assert.ok(docs.includes(target.browser), target.browser + " missing from documentation");
    assert.ok(docs.includes(target.userManifestDirectory), target.browser + " lookup directory not documented");
  }
});
