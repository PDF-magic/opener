import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (name) => JSON.parse(await readFile(join(root, name), "utf8"));
const apiFields = ["permissions", "optional_permissions"];
const hostFields = ["host_permissions", "optional_host_permissions"];
const explanationFields = ["explanation", "dataAccess", "userChoice", "safetyBoundary"];

function verifyExplanations(manifest, catalog) {
  for (const field of [...apiFields, ...hostFields]) {
    const values = manifest[field] ?? [];
    assert.ok(Array.isArray(values), field + " must be an array");
    const available = hostFields.includes(field) ? catalog.hostPermissions : catalog.apiPermissions;
    for (const value of values) {
      assert.equal(typeof value, "string", field);
      const explanation = available[value];
      assert.ok(explanation, "Undocumented " + field + ": " + value);
      for (const key of explanationFields) {
        assert.ok(typeof explanation[key] === "string" && explanation[key].trim().length >= 35,
          "Incomplete " + field + " explanation for " + value + ": " + key);
      }
    }
  }
}

test("every reviewed potential API permission has a complete individual explanation", async () => {
  const catalog = await load("permission-explanations.json");
  const audit = await load("permissions-audit.json");
  assert.equal(catalog.schemaVersion, 1);
  assert.deepEqual(Object.keys(catalog).sort(), ["apiPermissions", "hostPermissions", "schemaVersion"]);
  const potential = [...new Set(Object.values(audit.futureFeaturesOnly).flat())].sort();
  assert.deepEqual(Object.keys(catalog.apiPermissions).sort(), potential);
  assert.deepEqual(catalog.hostPermissions, {}, "no website origins are approved");
  for (const [permission, entry] of Object.entries(catalog.apiPermissions)) {
    assert.deepEqual(Object.keys(entry).sort(),
      ["dataAccess", "explanation", "feature", "safetyBoundary", "userChoice"]);
    assert.ok(typeof entry.feature === "string" && entry.feature.trim().length >= 20, permission);
    for (const field of explanationFields) {
      assert.ok(typeof entry[field] === "string" && entry[field].trim().length >= 35,
        permission + " missing " + field);
    }
  }
});

test("source, Chromium and Firefox declared permissions all have explanations", async () => {
  const catalog = await load("permission-explanations.json");
  for (const file of ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"]) {
    const manifest = await load(file);
    verifyExplanations(manifest, catalog);
    assert.deepEqual(manifest.permissions, [], file + " must have no required API grants");
    assert.deepEqual(manifest.host_permissions, [], file + " must have no required site grants");
  }
});

test("unexplained required, optional or website-origin access fails closed", async () => {
  const catalog = await load("permission-explanations.json");
  assert.throws(() => verifyExplanations({ permissions: ["tabs"] }, catalog), /Undocumented permissions/);
  assert.throws(() => verifyExplanations({ optional_permissions: ["history"] }, catalog), /Undocumented optional_permissions/);
  assert.throws(() => verifyExplanations({ host_permissions: ["<all_urls>"] }, catalog), /Undocumented host_permissions/);
  assert.throws(() => verifyExplanations({ optional_host_permissions: ["https:\/\/\*\/\*"] }, catalog), /Undocumented optional_host_permissions/);
  const inadequate = {
    ...catalog,
    apiPermissions: {
      ...catalog.apiPermissions,
      downloads: { ...catalog.apiPermissions.downloads, userChoice: "" }
    }
  };
  assert.throws(() => verifyExplanations({ optional_permissions: ["downloads"] }, inadequate),
    /Incomplete optional_permissions/);
});

test("download explanation addresses privacy, opt-in and mandatory scanner checks", async () => {
  const catalog = await load("permission-explanations.json");
  const d = catalog.apiPermissions.downloads;
  assert.match(d.explanation, /download|monitor/i);
  assert.match(d.dataAccess, /filename|URL|history/i);
  assert.match(d.userChoice, /approve|declin|opt|prompt/i);
  assert.match(d.safetyBoundary, /ClamAV|scan|quarantine/i);
  const docs = await readFile(join(root, "permission-explanations.md"), "utf8");
  for (const p of Object.keys(catalog.apiPermissions)) {
    assert.ok(docs.includes(String.fromCharCode(96) + p + String.fromCharCode(96)),
      "Document missing permission: " + p);
  }
  assert.match(docs, /not four currently granted/i);
});
