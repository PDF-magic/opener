import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const docPath = fileURLToPath(new URL("../../../docs/browser-extension-permissions.md", import.meta.url));
const indexPath = fileURLToPath(new URL("../../README.md", import.meta.url));
const fields = ["permissions", "host_permissions", "optional_permissions", "optional_host_permissions"];
const builds = [
  ["Shared / Chromium", "manifest.json"],
  ["Firefox", "dist/firefox/manifest.json"],
  ["Safari", "../safari/manifest.json"]
];

function documentedRow(documentation, label) {
  const row = documentation.split("\n").find((line) => line.startsWith(`| ${label} |`));
  assert.ok(row, `Missing documented browser build: ${label}`);
  const cells = row.split("|").slice(2, -1).map((cell) => cell.trim());
  assert.equal(cells.length, fields.length, `Incorrect matrix width: ${label}`);
  return cells.map((cell) => {
    if (cell === "None") return [];
    const permissions = [...cell.matchAll(/`([^`]+)`/g)].map((match) => match[1]);
    assert.ok(permissions.length > 0, `Undocumented grants for ${label}: ${cell}`);
    return permissions;
  });
}

function verifyRow(manifest, row, label) {
  for (const [index, field] of fields.entries()) {
    assert.deepEqual(manifest[field] ?? [], row[index], `${label} ${field}: documentation differs from manifest`);
  }
}

test("published browser requirements match each real source or built manifest", async () => {
  const guide = await readFile(docPath, "utf8");
  for (const [label, path] of builds) {
    const manifest = JSON.parse(await readFile(join(root, path), "utf8"));
    verifyRow(manifest, documentedRow(guide, label), label);
  }
});

test("public guide describes consent and keeps browser permissions separate from PDF safety", async () => {
  const guide = await readFile(docPath, "utf8");
  const index = await readFile(indexPath, "utf8");
  assert.match(index, /\.\.\/docs\/browser-extension-permissions\.md/);
  assert.match(guide, /native macOS PDF handler works without a browser/i);
  assert.match(guide, /inactive scaffolds/i);
  assert.match(guide, /Safari-only manifest difference/i);
  assert.match(guide, /not granted on install/i);
  assert.match(guide, /user-initiated gesture/i);
  assert.match(guide, /denied, revoked, or unavailable/i);
  assert.match(guide, /filenames, source URLs and download history/i);
  assert.match(guide, /no host origins are requested/i);
  assert.match(guide, /future-only/i);
  assert.match(guide, /app sandbox only/i);
  assert.match(guide, /ClamAV signature freshness/i);
  assert.match(guide, /user.s chosen PDF destination/i);
  for (const path of [
    "../extensions/webextension/permissions.md",
    "../extensions/webextension/host-permissions.md",
    "../extensions/webextension/permission-explanations.md",
    "../extensions/safari/README.md"
  ]) assert.ok(guide.includes(`](${path})`), `Missing contract reference: ${path}`);
});

test("undocumented additional browser or host privileges fail the matrix contract", async () => {
  const guide = await readFile(docPath, "utf8");
  const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  const declared = documentedRow(guide, "Shared / Chromium");
  assert.throws(() => verifyRow({ ...source, permissions: ["tabs"] }, declared, "Chromium"),
    /documentation differs from manifest/);
  assert.throws(() => verifyRow({ ...source, host_permissions: ["<all_urls>"] }, declared, "Chromium"),
    /documentation differs from manifest/);
  assert.throws(() => verifyRow({ ...source, optional_permissions: [] }, declared, "Chromium"),
    /documentation differs from manifest/);
  const safari = JSON.parse(await readFile(join(root, "../safari/manifest.json"), "utf8"));
  assert.throws(() => verifyRow({ ...safari, permissions: [] }, documentedRow(guide, "Safari"), "Safari"),
    /documentation differs from manifest/);
});
