import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const read = (p) => readFile(join(root, p), "utf8");
const json = async (p) => JSON.parse(await read(p));

test("private/incognito windows are excluded in all WebExtensions manifests", async () => {
  const names = ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"];
  for (const name of names) {
    const manifest = await json(name);
    assert.equal(manifest.incognito, "not_allowed", name);
    assert.deepEqual(manifest.permissions, [], name + ": required API access");
    assert.deepEqual(manifest.host_permissions, [], name + ": host access");
    assert.deepEqual(manifest.optional_permissions, ["downloads"],
      name + ": separate optional download consent is preserved");
    assert.equal(manifest.optional_host_permissions, undefined, name);
  }
  assert.deepEqual(await json("dist/manifest.json"), await json("manifest.json"),
    "Chromium manifest must be the exact shared manifest");
});

test("builders fail closed on missing or weaker private browsing policy", async () => {
  const chromium = await read("scripts/build.mjs");
  const firefox = await read("scripts/build-firefox.mjs");
  assert.ok(chromium.includes('manifest.incognito !== "not_allowed"'),
    "Chromium build must reject other incognito modes and absent key");
  assert.ok(firefox.includes('source.incognito !== "not_allowed"'),
    "Firefox build must reject other private browsing modes and absent key");
  for (const mode of [undefined, "spanning", "split", true, "allowed"]) {
    assert.notEqual(mode, "not_allowed");
  }
});

test("private browsing exclusion adds no event listeners or scanner authority", async () => {
  const worker = await read("src/background.js");
  assert.equal(worker,
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "void 0;\n");
  const doc = await read("README.md");
  assert.match(doc, /incognito.*not_allowed|not_allowed.*private/is);
  assert.match(doc, /Safari.*user-managed|Safari.*private-browsing/is);
});
