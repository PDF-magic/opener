import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (name) => JSON.parse(await readFile(join(root, name), "utf8"));
const manifestFiles = [
  "manifest.json",
  "dist/manifest.json",
  "dist/firefox/manifest.json"
];
const withoutHostGrants = [
  "optional_host_permissions",
  "content_scripts",
  "externally_connectable"
];

test("host scope audit records only empty current origin grants", async () => {
  const audit = await load("host-permissions-audit.json");
  assert.deepEqual(audit.currentHostAccess, {
    requiredOrigins: [],
    optionalOrigins: [],
    contentScriptMatches: []
  });
  assert.equal(audit.schemaVersion, 1);
  assert.deepEqual(Object.keys(audit).sort(), [
    "currentHostAccess", "featuresNotRequiringHostOrigins",
    "futureSiteAccessReview", "schemaVersion"
  ]);
  assert.deepEqual(audit.featuresNotRequiringHostOrigins, [
    "staticToolbarAndPopup",
    "extensionUpdateEventObservation",
    "browserDownloadEventObservation",
    "callerSuppliedPdfMetadataClassification",
    "extensionInternalMessaging",
    "localNativeScannerMessaging",
    "localNativePreferencesLink"
  ]);
  assert.deepEqual(audit.futureSiteAccessReview, {
    contentScriptInjection: "reviewExactSitesAndUserConsent",
    crossOriginPdfRetrieval: "reviewExactOriginsAndUserConsent"
  });
});

test("Chromium, Firefox and common source grant zero host origins", async () => {
  const audit = await load("host-permissions-audit.json");
  const expected = audit.currentHostAccess.requiredOrigins;
  for (const path of manifestFiles) {
    const manifest = await load(path);
    assert.equal(manifest.manifest_version, 3, path);
    assert.deepEqual(manifest.host_permissions, expected, path + ": host_permissions");
    for (const key of withoutHostGrants) {
      assert.equal(Object.hasOwn(manifest, key), false, path + ": " + key);
    }
    assert.equal(JSON.stringify(manifest).includes("<all_urls>"), false, path);
    assert.equal(JSON.stringify(manifest).includes("file://"), false, path);
  }
});

test("host scope is independent of browser API permission scope", async () => {
  for (const path of manifestFiles) {
    const manifest = await load(path);
    assert.deepEqual(manifest.permissions, [], path);
    // The independent optional-downloads PR may add a downloads-only API
    // prompt; that does not permit access to website origins.
    if (Object.hasOwn(manifest, "optional_permissions")) {
      assert.deepEqual(manifest.optional_permissions, ["downloads"], path);
    }
    assert.equal(Object.hasOwn(manifest, "web_accessible_resources"), false, path);
    assert.equal(Object.hasOwn(manifest, "content_scripts"), false, path);
  }
});

test("no background observer or website injection activates a host grant", async () => {
  const source = await readFile(join(root, "src/background.js"), "utf8");
  const chromium = await readFile(join(root, "dist/background.js"), "utf8");
  const firefox = await readFile(join(root, "dist/firefox/background.js"), "utf8");
  assert.equal(chromium, source);
  assert.equal(firefox, source);
  assert.equal(source,
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "void 0;\n");
});

test("host permission guidance distinguishes download and native API grants from origin access", async () => {
  const doc = await readFile(join(root, "host-permissions.md"), "utf8");
  for (const statement of [
    "zero host permissions", "downloads", "nativeMessaging",
    "exact-origin", "user", "ClamAV", "host-permissions-audit.json"
  ]) {
    assert.ok(doc.includes(statement), "Missing host audit explanation: " + statement);
  }
});
