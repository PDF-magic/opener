import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createPermissionDenialHandler } from "../src/permission-denials.js";
import { requestDownloadMonitoringPermission } from "../src/download-permission.js";

const load = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("an explicit refused permission request stops protected monitoring and latches denial", async () => {
  const subscriptions = new Set(["downloads.onCreated", "downloads.onChanged"]);
  let shutdowns = 0;
  const handler = createPermissionDenialHandler(() => {
    shutdowns++;
    subscriptions.clear();
  });
  let calls = 0;
  const denied = await requestDownloadMonitoringPermission({
    request: ({ permissions }) => {
      calls++;
      assert.deepEqual(permissions, ["downloads"]);
      return Promise.resolve(false);
    }
  }, { monitoringEnabled: true, userInitiated: true });
  assert.equal(denied, false);
  assert.equal(calls, 1);
  const result = await handler.handle(denied);
  assert.equal(result.status, "denied");
  assert.equal(result.canProceed, false);
  assert.equal(result.scannerVerified, false);
  assert.equal(result.authorizesOpen, false);
  assert.equal(shutdowns, 1);
  assert.deepEqual([...subscriptions], []);
  assert.equal((await handler.handle(true)).status, "denied",
    "a stale subsequent grant must not resume a denied feature");
  assert.equal(shutdowns, 1);
});

test("browser failures and unverifiable requests cannot enable a scanner", async () => {
  const options = { monitoringEnabled: true, userInitiated: true };
  for (const request of [
    () => Promise.reject(new Error("private document path")),
    () => { throw new Error("private document path"); },
    () => undefined
  ]) {
    const grant = await requestDownloadMonitoringPermission({ request }, options);
    assert.equal(grant, false);
    const denied = await createPermissionDenialHandler().handle(grant);
    assert.equal(denied.canProceed, false);
    assert.equal(denied.authorizesOpen, false);
    assert.equal(JSON.stringify(denied).includes("private"), false);
  }
});

test("real Brave extension smoke verifies denied browser API and unchanged grants", async () => {
  const [smoke,workflow,manifest,background,doc] = await Promise.all([
    load("../scripts/smoke-brave.mjs"),
    load("../../../.github/workflows/brave-webextension.yml"),
    load("../manifest.json").then(JSON.parse),
    load("../src/background.js"),
    load("../brave/README.md")
  ]);
  for (const phrase of [
    "chrome.downloads?.search", "chrome.downloads.search({}",
    "chrome.runtime.lastError", '"unexpected-access"',
    "chrome.permissions.getAll()", "downloadsGranted",
    "assert.deepEqual(grantsAfterDenial.permissions, [])",
    "assert.deepEqual(grantsAfterDenial.origins, [])",
    "scanButton.isDisabled()", "No verified scan result is available.",
    "context?.close()", "rm(profile"
  ]) assert.ok(smoke.includes(phrase), phrase);
  assert.match(workflow, /node scripts\/smoke-brave\.mjs/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  for (const phrase of [
    "opener-0812", "denial", "Brave", "scanner", "user preferences"
  ]) assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
});
