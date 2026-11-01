// Browser-API contract regression for revoked extension permissions (opener-1065).
// Every browser API here is isolated; production extension startup stays inert.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { requestDownloadMonitoringPermission } from "../src/download-permission.js";
import { subscribeToDownloadCompletions } from "../src/download-completion.js";
import { subscribeToPermissionRevocations } from "../src/permission-revocations.js";

function browserEvent() {
  const listeners = new Set();
  return {
    addListener(callback) { listeners.add(callback); },
    removeListener(callback) { listeners.delete(callback); },
    emit(payload) { for (const callback of [...listeners]) callback(payload); },
    get size() { return listeners.size; }
  };
}

function simulatedBrowser() {
  const onRemoved = browserEvent();
  const onAdded = browserEvent();
  const granted = new Set();
  const calls = { request: 0, remove: 0 };
  const permissions = {
    onRemoved,
    onAdded,
    async request(details) {
      calls.request++;
      assert.deepEqual(details, { permissions: ["downloads"] });
      granted.add("downloads");
      onAdded.emit({ permissions: ["downloads"] });
      return true;
    },
    async contains({ permissions: names }) {
      return names.every((name) => granted.has(name));
    },
    async getAll() { return { permissions: [...granted], origins: [] }; },
    async remove(details) {
      calls.remove++;
      assert.deepEqual(details, { permissions: ["downloads"] });
      const removed = granted.delete("downloads");
      if (removed) onRemoved.emit({ permissions: ["downloads"], origins: [] });
      return removed;
    }
  };
  const downloads = {
    onCreated: browserEvent(),
    onChanged: browserEvent(),
    onErased: browserEvent()
  };
  return { permissions, downloads, calls };
}

test("revoking a previously granted optional permission stops active download monitoring", async () => {
  const { permissions, downloads, calls } = simulatedBrowser();
  const prefs = Object.freeze({ selectedPDFApplication: "custom-viewer",
    monitoringEnabled: true, protectionProfile: "strict" });
  const before = JSON.stringify(prefs);
  const pending = new Set();
  const completions = [];
  let stopped = 0;
  let stopDownloads;
  const observer = subscribeToPermissionRevocations(permissions, (state) => {
    if (state.downloadsRevoked) {
      stopDownloads?.();
      stopDownloads = undefined;
      pending.clear(); // The trusted coordinator cancels pending work.
      stopped++;
    }
  });

  assert.equal(await permissions.contains({ permissions: ["downloads"] }), false);
  assert.equal(downloads.onChanged.size, 0, "no opt-in means no monitoring");
  assert.equal(calls.request, 0, "installation never asks for access");
  const consent = await requestDownloadMonitoringPermission(permissions,
    { monitoringEnabled: true, userInitiated: true });
  assert.equal(consent, true);
  assert.equal(await permissions.contains({ permissions: ["downloads"] }), true);
  stopDownloads = subscribeToDownloadCompletions(downloads, (event) => {
    completions.push(event);
    pending.add(event.id); // A transfer is not a scanner verdict.
  });
  downloads.onChanged.emit({ id: 19, state: { current: "complete" } });
  assert.deepEqual(completions, [{ kind: "completed", id: 19 }]);
  assert.deepEqual([...pending], [19]);
  assert.equal(downloads.onChanged.size, 1);

  // Browser-style permissions.remove synchronously sends onRemoved.
  assert.equal(await permissions.remove({ permissions: ["downloads"] }), true);
  assert.equal(await permissions.contains({ permissions: ["downloads"] }), false);
  assert.deepEqual(await permissions.getAll(), { permissions: [], origins: [] });
  assert.equal(observer.isRevoked("downloads"), true);
  assert.equal(observer.state().permissionsVerified, false);
  assert.equal(observer.state().authorizesOpen, false);
  assert.equal(stopped, 1);
  assert.equal(pending.size, 0, "unscanned work must be cancelled");
  for (const source of Object.values(downloads)) assert.equal(source.size, 0);
  downloads.onChanged.emit({ id: 20, state: { current: "complete" } });
  assert.deepEqual(completions, [{ kind: "completed", id: 19 }],
    "revocation must prevent further completions from reaching the coordinator");

  assert.equal(await permissions.remove({ permissions: ["downloads"] }), false);
  permissions.onAdded.emit({ permissions: ["downloads"] });
  assert.equal(observer.isRevoked("downloads"), true,
    "an onAdded notification cannot silently resume a revoked feature");
  assert.equal(calls.request, 1, "no automatic re-request");
  assert.equal(stopped, 1, "duplicate removal is idempotent");
  assert.equal(JSON.stringify(prefs), before, "user preferences are untouched");
  observer.unsubscribe();
  assert.equal(permissions.onRemoved.size, 0);
});

test("unrelated browser permission changes do not disable a separately consented download listener", async () => {
  const { permissions, downloads } = simulatedBrowser();
  await requestDownloadMonitoringPermission(permissions,
    { monitoringEnabled: true, userInitiated: true });
  const received = [];
  const stop = subscribeToDownloadCompletions(downloads, (event) => received.push(event.id));
  let callbacks = 0;
  const observer = subscribeToPermissionRevocations(permissions, () => { callbacks++; });
  permissions.onRemoved.emit({ permissions: ["tabs"] });
  assert.equal(callbacks, 0);
  assert.equal(observer.isRevoked("downloads"), false);
  downloads.onChanged.emit({ id: 4, state: { current: "complete" } });
  assert.deepEqual(received, [4]);
  stop();
  observer.unsubscribe();
});

test("malformed removal events fail closed even if browser permission queries are stale", async () => {
  const { permissions, downloads } = simulatedBrowser();
  await requestDownloadMonitoringPermission(permissions,
    { monitoringEnabled: true, userInitiated: true });
  const received = [];
  const stop = subscribeToDownloadCompletions(downloads, (event) => received.push(event.id));
  const observer = subscribeToPermissionRevocations(permissions, (state) => {
    if (state.downloadsRevoked) stop();
  });
  permissions.onRemoved.emit({ permissions: ["downloads"], origins: "invalid" });
  assert.equal(await permissions.contains({ permissions: ["downloads"] }), true,
    "the mock intentionally returns a stale current grant");
  assert.equal(observer.isRevoked("downloads"), true);
  assert.equal(observer.isRevoked("nativeMessaging"), true);
  assert.equal(observer.isRevoked("siteAccess"), true);
  assert.equal(observer.state().authorizesOpen, false);
  downloads.onChanged.emit({ id: 5, state: { current: "complete" } });
  assert.deepEqual(received, [], "bad revocation messages cannot permit later work");
  observer.unsubscribe();
});

test("disabled and refused optional access never attaches privileged browser listeners", async () => {
  const { permissions, downloads, calls } = simulatedBrowser();
  assert.equal(await requestDownloadMonitoringPermission(permissions,
    { monitoringEnabled: false, userInitiated: true }), false);
  assert.equal(await requestDownloadMonitoringPermission(permissions,
    { monitoringEnabled: true, userInitiated: false }), false);
  permissions.request = async () => { calls.request++; return false; };
  assert.equal(await requestDownloadMonitoringPermission(permissions,
    { monitoringEnabled: true, userInitiated: true }), false);
  assert.equal(calls.request, 1);
  assert.deepEqual(await permissions.getAll(), { permissions: [], origins: [] });
  for (const source of Object.values(downloads)) assert.equal(source.size, 0);
});

test("revocation test leaves the installed scaffold's grants and scanner gates unchanged", async () => {
  const manifest = JSON.parse(await readFile(
    new URL("../manifest.json", import.meta.url), "utf8"));
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.match(background, /void 0;\s*$/);
  assert.doesNotMatch(background, /permissions\.request|connectNative|scan|downloads\.onChanged/);
});
