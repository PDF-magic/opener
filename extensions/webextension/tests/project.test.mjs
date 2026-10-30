import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (path) => JSON.parse(await readFile(join(root, path), "utf8"));

test("the shared project is a private dependency-free Node package", async () => {
  const pkg = await load("package.json");
  assert.equal(pkg.private, true);
  assert.equal(pkg.type, "module");
  assert.equal(pkg.scripts.build, "node scripts/build.mjs");
  assert.equal(pkg.scripts.test, "node --test tests/*.test.mjs");
  assert.equal(pkg.dependencies, undefined);
  assert.equal(pkg.devDependencies, undefined);
  assert.equal(pkg.scripts.install, undefined);
  assert.equal(pkg.scripts.start, undefined);
});

test("the common Manifest V3 scaffold has no browser or host privileges", async () => {
  const manifest = await load("manifest.json");
  assert.deepEqual(Object.keys(manifest).sort(), [
    "description", "host_permissions", "manifest_version", "name", "permissions", "version"
  ]);
  assert.equal(manifest.manifest_version, 3);
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
  assert.equal(manifest.name, "PDF Magic Opener");
  assert.equal(manifest.description,
    "PDF Magic Opener browser integration scaffold. Not active; cannot scan, sanitize, or open PDF files.");
  assert.ok(manifest.description.length <= 132);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  for (const forbidden of [
    "background", "content_scripts", "externally_connectable", "nativeMessaging",
    "web_accessible_resources", "action", "optional_permissions", "optional_host_permissions"
  ]) {
    assert.equal(manifest[forbidden], undefined);
  }
});

test("the build generates the same inert portable manifest", async () => {
  const source = await load("manifest.json");
  const output = await load("dist/manifest.json");
  assert.deepEqual(output, source);
  assert.equal(output.name, "PDF Magic Opener");
  const raw = await readFile(join(root, "dist", "manifest.json"), "utf8");
  assert.equal(raw, `${JSON.stringify(source, null, 2)}\n`);
});
