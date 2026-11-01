// Read-only, dependency-free validation for the reviewed browser manifests.
import assert from "node:assert/strict";
import { lstat, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const iconPaths = {
  "16": "icons/icon-16.png",
  "32": "icons/icon-32.png",
  "48": "icons/icon-48.png",
  "128": "icons/icon-128.png"
};
const allowedFields = [
  "action", "background", "description", "host_permissions", "icons",
  "incognito", "manifest_version", "name", "optional_permissions",
  "permissions", "version"
];
const manifestFiles = {
  shared: "manifest.json",
  chromium: "dist/manifest.json",
  firefox: "dist/firefox/manifest.json",
  safari: "../safari/manifest.json",
  gecko: "firefox/gecko.json"
};

export function validateExtensionManifests({ shared, chromium, firefox, safari, gecko }) {
  assert.ok(shared && typeof shared === "object" && !Array.isArray(shared),
    "Shared manifest must be an object");
  assert.deepEqual(Object.keys(shared).sort(), allowedFields,
    "Shared manifest contains missing or unreviewed fields");
  assert.equal(shared.manifest_version, 3, "Manifest V3 is required");
  assert.equal(shared.name, "PDF Magic Opener");
  assert.match(shared.version, /^\d+\.\d+\.\d+$/, "Version must be numeric triplet");
  assert.equal(shared.incognito, "not_allowed", "Private browsing must remain excluded");
  assert.equal(shared.description,
    "PDF Magic Opener browser integration scaffold. Not active; cannot scan, sanitize, or open PDF files.");
  assert.deepEqual(shared.permissions, [], "No required browser privileges");
  assert.deepEqual(shared.host_permissions, [], "No website grants");
  assert.deepEqual(shared.optional_permissions, ["downloads"],
    "Only user-consented download access is declared");
  assert.deepEqual(shared.icons, iconPaths, "Only the reviewed local icon paths are allowed");
  assert.deepEqual(shared.background, {
    service_worker: "background.js", type: "module"
  }, "The shared background must remain a module service worker");
  assert.deepEqual(shared.action, {
    default_title: "PDF Magic Opener (not active)",
    default_icon: iconPaths,
    default_popup: "popup.html"
  }, "The toolbar must retain its inactive local popup");

  assert.deepEqual(chromium, shared,
    "Built Chromium manifest must match the reviewed source without additions");
  assert.deepEqual(gecko, {
    gecko: {
      id: "pdf-magic-opener@example.invalid",
      strict_min_version: "128.0",
      data_collection_permissions: { required: ["none"] }
    }
  }, "Firefox metadata must retain its reviewed identity and no-collection policy");
  assert.deepEqual(firefox, {
    ...shared,
    background: { scripts: ["background.js"] },
    browser_specific_settings: gecko
  }, "Firefox may differ only in its background registration and Gecko metadata");
  assert.deepEqual(safari, {
    ...shared,
    permissions: ["nativeMessaging"]
  }, "Only the contained Safari extension may require nativeMessaging");
}

async function readJsonFile(path) {
  const info = await lstat(path);
  assert.ok(info.isFile() && !info.isSymbolicLink() && info.size <= 64 * 1024,
    "Manifest input must be a regular, bounded file");
  return JSON.parse(await readFile(path, "utf8"));
}

export async function readExtensionManifests(directory = root) {
  const manifests = {};
  for (const [name, relative] of Object.entries(manifestFiles)) {
    manifests[name] = await readJsonFile(join(directory, relative));
  }
  return manifests;
}

export async function validateFromDisk(directory = root) {
  validateExtensionManifests(await readExtensionManifests(directory));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await validateFromDisk();
  console.log("PASS shared, Chromium, Firefox and Safari extension manifest validation");
}
