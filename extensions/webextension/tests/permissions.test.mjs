import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (file) => JSON.parse(await readFile(join(root, file), "utf8"));
const permissionFields = [
  "permissions", "host_permissions", "optional_permissions", "optional_host_permissions"
];

test("permission audit declares only an optional download grant and no required API access", async () => {
  const audit = await load("permissions-audit.json");
  assert.deepEqual(audit, {
    schemaVersion: 1,
    currentManifestRequirements: {
      permissions: [], host_permissions: [], optional_permissions: ["downloads"],
      optional_host_permissions: []
    },
    futureFeaturesOnly: {
      downloadEventMonitoring: ["downloads"],
      nativeAppMessaging: ["nativeMessaging"],
      userNotifications: ["notifications"],
      persistentSettings: ["storage"]
    }
  });
});

test("source and both built WebExtensions manifests request no browser or host access", async () => {
  const audit = await load("permissions-audit.json");
  for (const path of ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"]) {
    const manifest = await load(path);
    assert.equal(manifest.manifest_version, 3, path);
    for (const field of ["permissions", "host_permissions"]) {
      assert.deepEqual(manifest[field], audit.currentManifestRequirements[field], `${path}: ${field}`);
    }
    assert.deepEqual(manifest.optional_permissions, ["downloads"], `${path}: only conditional download access`);
    assert.equal(Object.hasOwn(manifest, "optional_host_permissions"), false,
      `${path}: optional host access must not be declared`);
    for (const privileged of [
      "content_scripts", "externally_connectable", "web_accessible_resources",
      "devtools_page", "content_security_policy"
    ]) {
      assert.equal(Object.hasOwn(manifest, privileged), false, `${path}: unexpected ${privileged}`);
    }
    assert.equal(JSON.stringify(manifest).includes("<all_urls>"), false, path);
  }
});

test("Firefox declares no data collection and preserves the same permissions", async () => {
  const chromium = await load("dist/manifest.json");
  const firefox = await load("dist/firefox/manifest.json");
  assert.deepEqual(firefox.permissions, chromium.permissions);
  assert.deepEqual(firefox.host_permissions, chromium.host_permissions);
  assert.deepEqual(firefox.optional_permissions, chromium.optional_permissions);
  assert.deepEqual(firefox.browser_specific_settings.gecko.data_collection_permissions, {
    required: ["none"]
  });
});

test("inactive background does not activate privileged browser integrations", async () => {
  const source = await readFile(join(root, "src/background.js"), "utf8");
  assert.equal(source,
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "void 0;\n");
  const audit = await readFile(join(root, "permissions.md"), "utf8");
  assert.match(audit, /minimum browser permissions/i);
  assert.match(audit, /downloadEventMonitoring|Download event monitoring/);
  assert.match(audit, /nativeMessaging/);
  assert.match(audit, /Neither permission inventory nor manifest validation is a malware-clean/i);
});
