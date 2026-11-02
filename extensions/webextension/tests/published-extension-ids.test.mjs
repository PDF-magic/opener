import assert from "node:assert/strict";
import { mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { validatePublishedExtensionIds, verifyFromFiles } from "../../../scripts/verify_published_extension_ids.mjs";

const chromeId = "abcdefghijklmnopabcdefghijklmnop";
const edgeId = "ponmlkjihgfedcbaponmlkjihgfedcba";
const firefoxId = "released@pdfmagic.example";
const origin = (id) => "chrome-extension://" + id + "/";
const chromiumHost = (ids) => ({
  name: "org.pdfmagic.opener", description: "Host", path: "/Applications/PDFMagicOpener.app/Contents/Helpers/host",
  type: "stdio", allowed_origins: ids.map(origin)
});
const firefoxHost = (ids) => ({
  name: "org.pdfmagic.opener", description: "Firefox host", path: "/Applications/PDFMagicOpener.app/Contents/Helpers/host",
  type: "stdio", allowed_extensions: ids
});
const published = {
  chromium: [
    { channel: "chrome-web-store", id: chromeId, listing: "https://chromewebstore.google.com/detail/pdf-magic/" + chromeId },
    { channel: "edge-addons", id: edgeId, listing: "https://microsoftedge.microsoft.com/addons/detail/pdf-magic/" + edgeId }
  ],
  firefox: { id: firefoxId, listing: "https://addons.mozilla.org/en-US/firefox/addon/pdfmagic/" }
};
const addon = { browser_specific_settings: { gecko: { id: firefoxId } } };
const valid = () => ({ published, chromiumHosts: [chromiumHost([chromeId, edgeId])], firefoxHost: firefoxHost([firefoxId]), firefoxAddonManifest: addon });

test("matches independently supplied store IDs to exact host allowlists and signed Firefox metadata", () => {
  assert.deepEqual(validatePublishedExtensionIds(valid()), { chromiumStores: 2, firefox: true, hostManifests: 2 });
  assert.deepEqual(validatePublishedExtensionIds({ ...valid(), chromiumHosts: [chromiumHost([edgeId, chromeId]), chromiumHost([chromeId, edgeId])] }),
    { chromiumStores: 2, firefox: true, hostManifests: 3 });
});

test("refuses missing publication evidence, missing hosts and absent Firefox signed manifest", () => {
  assert.throws(() => validatePublishedExtensionIds({ published: { chromium: [], firefox: null } }), /No published/);
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), chromiumHosts: [] }), /require host manifests/);
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), firefoxAddonManifest: null }), /signed add-on/);
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), firefoxHost: null }), /needs host/);
});

test("refuses omitted, extra, duplicate and invalid Chromium native allowlist origins", () => {
  for (const ids of [[chromeId], [edgeId], [chromeId, edgeId, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"], [chromeId, chromeId], [chromeId, edgeId]]) {
    const host = chromiumHost(ids);
    if (ids.length === 2 && ids[0] !== ids[1]) host.allowed_origins[1] = "chrome-extension://*/";
    assert.throws(() => validatePublishedExtensionIds({ ...valid(), chromiumHosts: [host] }), /allowlist|duplicate|origin|match/);
  }
  const invalid = chromiumHost([chromeId, edgeId]);
  invalid.allowed_origins[0] = "chrome-extension://" + chromeId;
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), chromiumHosts: [invalid] }), /origin/);
});

test("refuses forged store domains, mismatched listing IDs and duplicate channel records", () => {
  for (const listing of [
    "http://chromewebstore.google.com/detail/pdf/" + chromeId,
    "https://chromewebstore.google.com.evil.test/detail/pdf/" + chromeId,
    "https://chromewebstore.google.com/detail/pdf/" + edgeId
  ]) {
    const modified = { ...published, chromium: [{ ...published.chromium[0], listing }] };
    assert.throws(() => validatePublishedExtensionIds({ published: modified, chromiumHosts: [chromiumHost([chromeId])], firefoxHost: firefoxHost([firefoxId]), firefoxAddonManifest: addon }), /HTTPS|domain|listing path/);
  }
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), published: { ...published, chromium: [...published.chromium, published.chromium[0]] } }), /Duplicate publishing channel/);
});

test("refuses Firefox placeholder, unrelated signed add-on ID and unexpected allowlist grants", () => {
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), published: { ...published, firefox: { ...published.firefox, id: "pdf-magic-opener@example.invalid" } } }), /development-only/);
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), firefoxAddonManifest: { browser_specific_settings: { gecko: { id: "other@example.org" } } } }), /signed Firefox/);
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), firefoxHost: firefoxHost([firefoxId, "other@example.com"]) }), /allowlist/);
  const altered = firefoxHost([firefoxId]); altered.name = "other.host";
  assert.throws(() => validatePublishedExtensionIds({ ...valid(), firefoxHost: altered }), /name differs/);
});

test("read-only CLI inputs reject symlinks and absent published file", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "pdfmagic-published-ids-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const evidence = join(root, "published.json");
  const manifest = join(root, "chromium.json");
  const firefox = join(root, "firefox.json");
  const signed = join(root, "addon.json");
  await Promise.all([
    writeFile(evidence, JSON.stringify(published)),
    writeFile(manifest, JSON.stringify(chromiumHost([chromeId, edgeId]))),
    writeFile(firefox, JSON.stringify(firefoxHost([firefoxId]))),
    writeFile(signed, JSON.stringify(addon))
  ]);
  assert.deepEqual(await verifyFromFiles({ published: evidence, chromiumHosts: [manifest], firefoxHost: firefox, firefoxAddonManifest: signed }),
    { chromiumStores: 2, firefox: true, hostManifests: 2 });
  await assert.rejects(verifyFromFiles({ chromiumHosts: [] }), /--published is required/);
  const link = join(root, "link.json");
  await symlink(manifest, link);
  await assert.rejects(verifyFromFiles({ published: evidence, chromiumHosts: [link], firefoxHost: firefox, firefoxAddonManifest: signed }), /regular, bounded/);
});
