#!/usr/bin/env node
// Offline, read-only cross-check of publisher-confirmed IDs and native host allowlists.
import assert from "node:assert/strict";
import { lstat, readFile } from "node:fs/promises";
import { isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";

const chromiumId = /^[a-p]{32}$/;
const geckoId = /^(?:[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9.-]{1,253}|\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\})$/;
const stores = {
  "chrome-web-store": "chromewebstore.google.com",
  "edge-addons": "microsoftedge.microsoft.com",
  "opera-addons": "addons.opera.com"
};
const hostName = "org.pdfmagic.opener";

function exactFields(value, names, label) {
  assert.ok(value && typeof value === "object" && !Array.isArray(value), label + " must be an object");
  assert.deepEqual(Object.keys(value).sort(), [...names].sort(), label + " has missing or unreviewed fields");
}

function listingUrl(value, domain, label) {
  assert.equal(typeof value, "string", label + " listing URL required");
  const url = new URL(value);
  assert.equal(url.protocol, "https:", label + " listing must use HTTPS");
  assert.equal(url.hostname, domain, label + " listing uses an unexpected publisher domain");
  assert.equal(url.username, "");
  assert.equal(url.password, "");
  assert.equal(url.search, "");
  assert.equal(url.hash, "");
  return url;
}

function hostManifest(manifest, allowKey) {
  exactFields(manifest, ["name", "description", "path", "type", allowKey], "Native host manifest");
  assert.equal(manifest.name, hostName, "Native host name differs");
  assert.equal(manifest.type, "stdio", "Native host transport differs");
  assert.ok(typeof manifest.description === "string" && manifest.description.length > 0 &&
    Buffer.byteLength(manifest.description) <= 256, "Native host description is invalid");
  assert.ok(typeof manifest.path === "string" && isAbsolute(manifest.path) &&
    !manifest.path.split("/").some((piece) => piece === "." || piece === ".."),
  "Native host path must be canonical and absolute");
  const allowed = manifest[allowKey];
  assert.ok(Array.isArray(allowed) && allowed.length > 0 && allowed.length <= 32,
    allowKey + " must be a nonempty bounded list");
  assert.equal(new Set(allowed).size, allowed.length, allowKey + " contains duplicates");
  return allowed;
}

function sameMembers(actual, expected, label) {
  assert.deepEqual([...actual].sort(), [...expected].sort(), label + " does not exactly match published IDs");
}

export function validatePublishedExtensionIds({ published, chromiumHosts = [], firefoxHost = null, firefoxAddonManifest = null }) {
  exactFields(published, ["chromium", "firefox"], "Publisher-confirmed identities");
  assert.ok(Array.isArray(published.chromium), "chromium must be an array");
  assert.ok(published.firefox === null || typeof published.firefox === "object", "firefox must be null or a record");
  assert.ok(published.chromium.length || published.firefox, "No published extension IDs supplied");
  const channels = new Set();
  const ids = new Set();
  for (const entry of published.chromium) {
    exactFields(entry, ["channel", "id", "listing"], "Published Chromium entry");
    assert.ok(Object.hasOwn(stores, entry.channel), "Unknown Chromium publishing channel");
    assert.ok(!channels.has(entry.channel), "Duplicate publishing channel");
    channels.add(entry.channel);
    assert.ok(typeof entry.id === "string" && chromiumId.test(entry.id), "Invalid published Chromium extension ID");
    ids.add(entry.id);
    const url = listingUrl(entry.listing, stores[entry.channel], entry.channel);
    if (entry.channel !== "opera-addons") {
      assert.equal(url.pathname.split("/").filter(Boolean).at(-1), entry.id,
        "Store listing path does not match the published extension ID");
    }
  }
  assert.equal(chromiumHosts.length > 0, ids.size > 0,
    "Published Chromium IDs require host manifests (and vice versa)");
  for (const manifest of chromiumHosts) {
    const origins = hostManifest(manifest, "allowed_origins");
    assert.ok(origins.every((origin) => typeof origin === "string" &&
      /^chrome-extension:\/\/[a-p]{32}\/$/.test(origin)), "Invalid Chromium origin");
    sameMembers(origins, [...ids].map((id) => "chrome-extension://" + id + "/"), "Chromium host allowlist");
  }
  if (published.firefox === null) {
    assert.equal(firefoxHost, null, "Firefox host has no published Firefox identity");
    assert.equal(firefoxAddonManifest, null, "Firefox package has no published Firefox identity");
  } else {
    exactFields(published.firefox, ["id", "listing"], "Published Firefox entry");
    const id = published.firefox.id;
    assert.ok(typeof id === "string" && geckoId.test(id) &&
      !id.endsWith("@example.invalid"), "Published Firefox ID is invalid or development-only");
    listingUrl(published.firefox.listing, "addons.mozilla.org", "Firefox AMO");
    assert.ok(firefoxHost && firefoxAddonManifest, "Firefox needs host and installed signed add-on manifest");
    sameMembers(hostManifest(firefoxHost, "allowed_extensions"), [id], "Firefox host allowlist");
    assert.equal(firefoxAddonManifest.browser_specific_settings?.gecko?.id, id,
      "Installed signed Firefox add-on ID does not match the publisher ID");
  }
  return { chromiumStores: channels.size, firefox: Boolean(published.firefox), hostManifests: chromiumHosts.length + Number(Boolean(firefoxHost)) };
}

async function boundedJson(path) {
  const stat = await lstat(path);
  assert.ok(stat.isFile() && !stat.isSymbolicLink() && stat.size > 0 && stat.size <= 65536,
    "Identity verification input must be a regular, bounded JSON file");
  return JSON.parse(await readFile(path, "utf8"));
}

export async function verifyFromFiles({ published, chromiumHosts, firefoxHost, firefoxAddonManifest }) {
  assert.ok(published, "--published is required; never infer a production ID");
  return validatePublishedExtensionIds({
    published: await boundedJson(published),
    chromiumHosts: await Promise.all(chromiumHosts.map(boundedJson)),
    firefoxHost: firefoxHost ? await boundedJson(firefoxHost) : null,
    firefoxAddonManifest: firefoxAddonManifest ? await boundedJson(firefoxAddonManifest) : null
  });
}

async function main(args) {
  const options = { chromiumHosts: [] };
  const flags = new Map([
    ["--published", "published"], ["--chromium-host", "chromiumHosts"],
    ["--firefox-host", "firefoxHost"], ["--firefox-addon-manifest", "firefoxAddonManifest"]
  ]);
  for (let i = 0; i < args.length; i += 2) {
    const field = flags.get(args[i]);
    assert.ok(field && args[i + 1] && !args[i + 1].startsWith("--"), "Unknown or incomplete verification argument");
    if (field === "chromiumHosts") options.chromiumHosts.push(args[i + 1]);
    else {
      assert.ok(!Object.hasOwn(options, field), "Duplicate " + args[i] + " argument");
      options[field] = args[i + 1];
    }
  }
  const result = await verifyFromFiles(options);
  console.log("PASS: " + result.chromiumStores + " Chromium store(s), Firefox=" + result.firefox + ", " + result.hostManifests + " exact native host allowlist(s)");
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main(process.argv.slice(2)).catch((error) => {
    console.error("Published extension ID verification FAILED: " + error.message);
    process.exitCode = 1;
  });
}
