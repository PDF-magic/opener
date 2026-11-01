import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  readExtensionManifests, validateExtensionManifests, validateFromDisk
} from "../scripts/validate-manifests.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const fixtures = await readExtensionManifests();
const clone = () => structuredClone(fixtures);

test("validate all reviewed source and packaged browser manifests", async () => {
  assert.doesNotThrow(() => validateExtensionManifests(clone()));
  await assert.doesNotReject(() => validateFromDisk());
});

test("reject malformed, escalated or missing shared manifest fields", () => {
  const mutations = [
    (m) => { m.manifest_version = 2; },
    (m) => { m.name = ""; },
    (m) => { m.version = "1.2"; },
    (m) => { m.incognito = "spanning"; },
    (m) => { m.permissions = ["tabs"]; },
    (m) => { m.host_permissions = ["<all_urls>"]; },
    (m) => { m.optional_permissions = ["downloads", "nativeMessaging"]; },
    (m) => { m.optional_permissions = []; },
    (m) => { m.content_scripts = [{ matches: ["<all_urls>"] }]; },
    (m) => { m.optional_host_permissions = ["https://example.org/*"]; },
    (m) => { m.externally_connectable = { matches: ["<all_urls>"] }; },
    (m) => { m.web_accessible_resources = []; },
    (m) => { m.background = { service_worker: "remote.js", type: "module" }; },
    (m) => { m.action.default_popup = "https://example.org/popup"; },
    (m) => { m.icons["16"] = "../other.png"; },
    (m) => { delete m.action; },
    (m) => { m.description = "Scans files automatically"; }
  ];
  for (const mutate of mutations) {
    const altered = clone();
    mutate(altered.shared);
    assert.throws(() => validateExtensionManifests(altered),
      "An unreviewed shared manifest change must fail validation");
  }
});

test("reject generated Chromium drift and unexpected Firefox privilege or metadata", () => {
  const mutations = [
    (m) => { m.chromium.permissions = ["nativeMessaging"]; },
    (m) => { m.chromium.version = "9.9.9"; },
    (m) => { m.firefox.background = { service_worker: "background.js" }; },
    (m) => { m.firefox.permissions = ["tabs"]; },
    (m) => { m.firefox.browser_specific_settings.gecko.data_collection_permissions.required = ["all"]; },
    (m) => { m.firefox.browser_specific_settings.gecko.id = "changed@example.invalid"; },
    (m) => { m.firefox.content_scripts = []; },
    (m) => { m.gecko.gecko.strict_min_version = "1.0"; }
  ];
  for (const mutate of mutations) {
    const altered = clone();
    mutate(altered);
    assert.throws(() => validateExtensionManifests(altered));
  }
});

test("Safari requires exactly its reviewed nativeMessaging delta", () => {
  for (const permissions of [
    [], ["tabs"], ["nativeMessaging", "tabs"],
    ["nativeMessaging", "nativeMessaging"]
  ]) {
    const altered = clone();
    altered.safari.permissions = permissions;
    assert.throws(() => validateExtensionManifests(altered));
  }
  for (const mutate of [
    (m) => { m.host_permissions = ["https://example.org/*"]; },
    (m) => { m.optional_permissions = []; },
    (m) => { m.action.default_popup = "other.html"; },
    (m) => { m.incognito = "split"; },
    (m) => { m.background = { scripts: ["background.js"] }; }
  ]) {
    const altered = clone();
    mutate(altered.safari);
    assert.throws(() => validateExtensionManifests(altered));
  }
});

test("reject unreadable, malformed, oversized and symlinked manifest inputs", async () => {
  const base = await mkdtemp(join(tmpdir(), "opener-manifest-validation-"));
  const directory = join(base, "webextension");
  const entries = {
    "manifest.json": fixtures.shared,
    "dist/manifest.json": fixtures.chromium,
    "dist/firefox/manifest.json": fixtures.firefox,
    "../safari/manifest.json": fixtures.safari,
    "firefox/gecko.json": fixtures.gecko
  };
  try {
    for (const [path, value] of Object.entries(entries)) {
      const full = join(directory, path);
      await mkdir(dirname(full), { recursive: true });
      await writeFile(full, JSON.stringify(value), "utf8");
    }
    await assert.doesNotReject(() => validateFromDisk(directory));

    const source = join(directory, "manifest.json");
    await writeFile(source, "{ invalid json", "utf8");
    await assert.rejects(() => validateFromDisk(directory), SyntaxError);

    await writeFile(source, "x".repeat(65 * 1024), "utf8");
    await assert.rejects(() => validateFromDisk(directory), /regular, bounded/);

    await rm(source);
    await symlink(join(directory, "dist", "manifest.json"), source);
    await assert.rejects(() => validateFromDisk(directory), /regular, bounded/);

    await rm(source);
    await assert.rejects(() => validateFromDisk(directory));
  } finally {
    await rm(base, { recursive: true, force: true });
  }
});

test("manifest validator does not require dependencies or modify preferences", async () => {
  const packageInfo = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
  assert.equal(packageInfo.scripts["validate:manifests"],
    "node scripts/validate-manifests.mjs");
  assert.equal(packageInfo.dependencies, undefined);
  assert.equal(packageInfo.devDependencies, undefined);
  const preferences = Object.freeze({ selectedPDFApplication: "custom-reader", scanEnabled: false });
  const before = JSON.stringify(preferences);
  await validateFromDisk();
  assert.equal(JSON.stringify(preferences), before);
});
