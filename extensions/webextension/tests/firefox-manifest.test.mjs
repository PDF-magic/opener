import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const run = promisify(execFile);
const load = async (path) => JSON.parse(await readFile(join(root, path), "utf8"));

test("Firefox metadata explicitly requests no data collection", async () => {
  const settings = await load("firefox/gecko.json");
  assert.deepEqual(Object.keys(settings), ["gecko"]);
  assert.equal(settings.gecko.id, "pdf-magic-opener@example.invalid");
  assert.equal(settings.gecko.strict_min_version, "128.0");
  assert.deepEqual(settings.gecko.data_collection_permissions, {
    required: ["none"]
  });
});

test("Firefox build includes the shared MV3 identity without new privileges", async () => {
  await run(process.execPath, [join(root, "scripts", "build-firefox.mjs")], {
    cwd: root,
    timeout: 10_000
  });
  const source = await load("manifest.json");
  const built = await load("dist/firefox/manifest.json");
  const { browser_specific_settings: firefoxSettings, ...shared } = built;
  assert.deepEqual(shared, source);
  assert.deepEqual(firefoxSettings, await load("firefox/gecko.json"));
  assert.equal(built.manifest_version, 3);
  assert.deepEqual(built.permissions, []);
  assert.deepEqual(built.host_permissions, []);
  assert.deepEqual(built.action, source.action);
  assert.equal(built.action.default_title, "PDF Magic Opener (not active)");
  assert.equal(built.action.default_popup, undefined);
  for (const size of [16, 32, 48, 128]) {
    const path = built.action.default_icon[String(size)];
    assert.equal(path, `icons/icon-${size}.png`);
    assert.deepEqual(await readFile(join(root, "dist", "firefox", path)),
      await readFile(join(root, path)));
  }
  for (const forbidden of [
    "background", "content_scripts", "externally_connectable",
    "optional_permissions", "optional_host_permissions"
  ]) {
    assert.equal(built[forbidden], undefined);
  }
  const raw = await readFile(join(root, "dist", "firefox", "manifest.json"), "utf8");
  assert.equal(raw, `${JSON.stringify(built, null, 2)}\n`);
});
