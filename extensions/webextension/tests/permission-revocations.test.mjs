import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  normalizePermissionRevocation,
  subscribeToPermissionRevocations
} from "../src/permission-revocations.js";

function browserPermissions() {
  const listeners = new Set();
  const history = { add: 0, remove: 0, request: 0 };
  const api = {
    onRemoved: {
      addListener(fn) { history.add++; listeners.add(fn); },
      removeListener(fn) { history.remove++; listeners.delete(fn); }
    },
    request() { history.request++; throw Error("permission request is prohibited"); }
  };
  return { api, history, listeners, emit: (payload) => {
    for (const fn of [...listeners]) fn(payload);
  } };
}

const empty = {
  downloadsRevoked: false,
  nativeMessagingRevoked: false,
  notificationsRevoked: false,
  storageRevoked: false,
  siteAccessRevoked: false
};

test("normalizes known removed API permissions without exposing event metadata", () => {
  const value = normalizePermissionRevocation({
    permissions: ["downloads", "nativeMessaging"],
    origins: [],
    privateUrl: "https://secret.example/path.pdf"
  });
  assert.deepEqual(value, { ...empty, downloadsRevoked: true, nativeMessagingRevoked: true });
  assert.equal(Object.isFrozen(value), true);
  assert.equal(JSON.stringify(value).includes("secret"), false);
});

test("revoking site origins conservatively blocks site access without exposing sites", () => {
  const value = normalizePermissionRevocation({
    permissions: [], origins: ["https://sensitive.example/*"]
  });
  assert.deepEqual(value, { ...empty, siteAccessRevoked: true });
  assert.equal(JSON.stringify(value).includes("sensitive"), false);
});

test("unknown valid permissions do not disable unrelated capabilities", () => {
  assert.deepEqual(normalizePermissionRevocation({ permissions: ["tabs"] }), empty);
  assert.deepEqual(normalizePermissionRevocation({ permissions: ["constructor", "__proto__"] }), empty);
  assert.deepEqual(normalizePermissionRevocation({ permissions: [], origins: [] }), empty);
});

test("malformed and accessor-bearing removal events fail closed", () => {
  const bad = [null, {}, { permissions: false }, { origins: "https://example.invalid/*" },
    { permissions: [null] }, { permissions: Array(1) },
    { permissions: ["x".repeat(513)] },
    { origins: Array(65).fill("https://safe.example/*") }];
  const getter = {};
  Object.defineProperty(getter, "permissions", { get() { throw Error("do not run"); } });
  bad.push(getter);
  for (const input of bad) {
    const value = normalizePermissionRevocation(input);
    assert.deepEqual(value, Object.fromEntries(Object.keys(empty).map((key) => [key, true])));
  }
});

test("registration is explicit and existing permissions are not treated as authorization", () => {
  const { api, history } = browserPermissions();
  assert.equal(history.add, 0);
  const states = [];
  const watcher = subscribeToPermissionRevocations(api, (state) => states.push(state));
  assert.equal(history.add, 1);
  assert.equal(watcher.isRevoked("downloads"), false);
  assert.equal(watcher.isRevoked("unreviewedApi"), true);
  assert.deepEqual(watcher.state(), { ...empty, authorizesOpen: false, permissionsVerified: false });
  assert.equal(history.request, 0);
  watcher.unsubscribe();
});

test("revocation latches synchronously before teardown and is never automatically restored", () => {
  const { api, emit } = browserPermissions();
  const snapshots = [];
  let watcher;
  watcher = subscribeToPermissionRevocations(api, (state) => {
    assert.equal(watcher.isRevoked("downloads"), true);
    assert.equal(state.downloadsRevoked, true);
    snapshots.push(state);
  });
  emit({ permissions: ["downloads"] });
  emit({ permissions: ["downloads"] });
  emit({ permissions: ["tabs"] });
  assert.equal(snapshots.length, 1);
  emit({ permissions: ["nativeMessaging"] });
  assert.equal(snapshots.length, 2);
  assert.equal(snapshots[1].downloadsRevoked, true);
  assert.equal(snapshots[1].nativeMessagingRevoked, true);
  assert.equal(snapshots[1].authorizesOpen, false);
  assert.equal(Object.isFrozen(snapshots[1]), true);
  assert.throws(() => { snapshots[1].downloadsRevoked = false; }, TypeError);
  watcher.unsubscribe();
});

test("a revoked downloads permission can immediately detach active event monitoring", async () => {
  const { subscribeToDownloadEvents } = await import("../src/download-monitoring.js");
  const { api, emit } = browserPermissions();
  const registered = new Set();
  const mkEvent = () => ({
    addListener(callback) { registered.add(callback); },
    removeListener(callback) { registered.delete(callback); }
  });
  const downloadsApi = { onCreated: mkEvent(), onChanged: mkEvent(), onErased: mkEvent() };
  const stopMonitoring = subscribeToDownloadEvents(downloadsApi, () => {});
  assert.equal(registered.size, 3);
  const watcher = subscribeToPermissionRevocations(api, (state) => {
    if (state.downloadsRevoked) stopMonitoring();
  });
  emit({ permissions: ["downloads"] });
  assert.equal(registered.size, 0);
  watcher.unsubscribe();
});

test("cleanup callback errors cannot undo the revoked state or leak private errors", () => {
  const { api, emit } = browserPermissions();
  const errors = [];
  const watcher = subscribeToPermissionRevocations(api, () => {
    throw Error("/private/pdf/path");
  }, { onError(error) { errors.push(error.message); throw Error("error hook failed"); } });
  assert.doesNotThrow(() => emit({ permissions: ["nativeMessaging"] }));
  assert.equal(watcher.isRevoked("nativeMessaging"), true);
  assert.deepEqual(errors, ["Permission revocation cleanup failed"]);
  watcher.unsubscribe();
});

test("unsubscribe is idempotent and stale listener callbacks are inert", () => {
  const { api, emit, history, listeners } = browserPermissions();
  const originalAdd = api.onRemoved.addListener;
  let saved;
  api.onRemoved.addListener = function (fn) { saved = fn; originalAdd.call(this, fn); };
  let calls = 0;
  const watcher = subscribeToPermissionRevocations(api, () => { calls++; });
  watcher.unsubscribe();
  watcher.unsubscribe();
  assert.equal(history.remove, 1);
  assert.equal(listeners.size, 0);
  saved({ permissions: ["downloads"] });
  emit({ permissions: ["nativeMessaging"] });
  assert.equal(calls, 0);
  assert.deepEqual(watcher.state(), { ...empty, authorizesOpen: false, permissionsVerified: false });
});

test("missing browser event APIs and registration failures fail safely", () => {
  assert.throws(() => subscribeToPermissionRevocations({}, () => {}), TypeError);
  assert.throws(() => subscribeToPermissionRevocations(browserPermissions().api, null), TypeError);
  const { api, history } = browserPermissions();
  api.onRemoved.addListener = () => { throw Error("register failed"); };
  assert.throws(() => subscribeToPermissionRevocations(api, () => {}), /could not be registered/);
  assert.equal(history.remove, 1);
});

test("revocation does not modify persisted preferences or grant runtime access", () => {
  const prefs = Object.freeze({ selectedPDFApplication: "custom-viewer", downloadMonitoringEnabled: true });
  const before = JSON.stringify(prefs);
  const { api, emit, history } = browserPermissions();
  const watcher = subscribeToPermissionRevocations(api, () => {});
  emit({ permissions: ["downloads", "nativeMessaging"] });
  assert.equal(JSON.stringify(prefs), before);
  assert.equal(history.request, 0);
  assert.equal(watcher.state().permissionsVerified, false);
  watcher.unsubscribe();
});

test("module has no browser globals, native bridge, storage, or scanner side effects", async () => {
  const source = await readFile(new URL("../src/permission-revocations.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "permissions.request(", "permissions.remove(",
    "connectNative(", "sendNativeMessage(", "fetch(", "localStorage",
    "storage.local", "window.open(", "scan-and-open", "node:fs", "node:child_process"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
