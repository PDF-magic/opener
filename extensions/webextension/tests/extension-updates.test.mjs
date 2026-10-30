import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  normalizeExtensionUpdate,
  subscribeToExtensionUpdates
} from "../src/extension-updates.js";

function createRuntime(version = "0.2.0") {
  const listeners = new Set();
  const counters = { registered: 0, removed: 0, manifests: 0 };
  const runtime = {
    getManifest() {
      counters.manifests += 1;
      return { name: "PDF Magic Opener", version };
    },
    onInstalled: {
      addListener(listener) {
        counters.registered += 1;
        listeners.add(listener);
      },
      removeListener(listener) {
        counters.removed += 1;
        listeners.delete(listener);
      }
    }
  };
  return {
    runtime, counters, listeners,
    emit(details) {
      for (const listener of [...listeners]) listener(details);
    }
  };
}

test("only actual extension updates produce a version-only event", () => {
  for (const reason of ["install", "chrome_update", "shared_module_update", "startup", undefined]) {
    assert.equal(normalizeExtensionUpdate({ reason, previousVersion: "0.1.0" }, "0.2.0"), null);
  }
  assert.deepEqual(normalizeExtensionUpdate({
    reason: "update", previousVersion: "0.1.0",
    id: "private-extension-id", url: "https://private.invalid/file.pdf"
  }, "0.2.0"), {
    kind: "extension-update", previousVersion: "0.1.0", currentVersion: "0.2.0"
  });
});

test("invalid, missing, unchanged or out-of-range versions fail closed", () => {
  for (const [before, after] of [
    [undefined, "0.2.0"], ["0.1.0", undefined], ["0.1.0", "0.1.0"],
    ["0.1.0", "2.0"], ["0.1.0", "2.0.0-beta"], ["0.1.0", "99999.2.3"],
    ["x".repeat(100), "0.2.0"], ["0.1.0", "../0.2.0"], ["01.2.3", "1.2.3"],
    ["0.1.0", "0.2.0.0.0"], [123, "0.2.0"]
  ]) {
    assert.equal(normalizeExtensionUpdate({ reason: "update", previousVersion: before }, after), null);
  }
  assert.deepEqual(normalizeExtensionUpdate({
    reason: "update", previousVersion: "1.2.3.4"
  }, "1.2.3.5").currentVersion, "1.2.3.5");
});

test("untrusted detail getters and prototype-based inputs are not invoked", () => {
  const malformed = Object.create({ reason: "update", previousVersion: "0.1.0" });
  assert.equal(normalizeExtensionUpdate(malformed, "0.2.0"), null);
  const getter = {};
  Object.defineProperty(getter, "reason", { get() { throw Error("must not execute"); } });
  assert.equal(normalizeExtensionUpdate(getter, "0.2.0"), null);
  const versionGetter = { reason: "update" };
  Object.defineProperty(versionGetter, "previousVersion", {
    get() { throw Error("must not execute"); }
  });
  assert.equal(normalizeExtensionUpdate(versionGetter, "0.2.0"), null);
  assert.equal(normalizeExtensionUpdate([], "0.2.0"), null);
  assert.equal(normalizeExtensionUpdate(null, "0.2.0"), null);
});

test("update results are immutable, minimal, and contain no arbitrary metadata", () => {
  const event = normalizeExtensionUpdate({
    reason: "update", previousVersion: "0.1.0", tabId: 24,
    downloadUrl: "https://private.invalid/a.pdf", selectedApplication: "/private/app"
  }, "0.2.0");
  assert.deepEqual(Object.keys(event).sort(), ["currentVersion", "kind", "previousVersion"]);
  assert.equal(Object.isFrozen(event), true);
  assert.equal(JSON.stringify(event).includes("private"), false);
  assert.throws(() => { event.currentVersion = "9.9.9"; }, TypeError);
});

test("subscription is explicit and reads manifest only for update events", () => {
  const { runtime, counters, emit, listeners } = createRuntime();
  const seen = [];
  assert.equal(counters.registered, 0);
  const stop = subscribeToExtensionUpdates(runtime, (e) => seen.push(e));
  assert.equal(counters.registered, 1);
  assert.equal(listeners.size, 1);
  emit({ reason: "install" });
  emit({ reason: "chrome_update", previousVersion: "0.1.0" });
  assert.equal(counters.manifests, 0);
  emit({ reason: "update", previousVersion: "0.1.0" });
  assert.deepEqual(seen, [{
    kind: "extension-update", previousVersion: "0.1.0", currentVersion: "0.2.0"
  }]);
  assert.equal(counters.manifests, 1);
  stop();
});

test("duplicate events are deduplicated while different version transitions remain visible", () => {
  const { runtime, emit } = createRuntime("0.2.0");
  let calls = 0;
  const stop = subscribeToExtensionUpdates(runtime, () => { calls += 1; });
  emit({ reason: "update", previousVersion: "0.1.0" });
  emit({ reason: "update", previousVersion: "0.1.0" });
  emit({ reason: "update", previousVersion: "0.0.9" });
  assert.equal(calls, 2);
  stop();
});

test("unsubscribe is idempotent and late callbacks remain inactive", () => {
  const { runtime, emit, counters, listeners } = createRuntime();
  let captured;
  runtime.onInstalled.addListener = (listener) => {
    captured = listener;
    counters.registered += 1;
    listeners.add(listener);
  };
  let calls = 0;
  const stop = subscribeToExtensionUpdates(runtime, () => { calls += 1; });
  stop();
  stop();
  assert.equal(counters.removed, 1);
  assert.equal(listeners.size, 0);
  captured({ reason: "update", previousVersion: "0.1.0" });
  emit({ reason: "update", previousVersion: "0.1.0" });
  assert.equal(calls, 0);
});

test("callback errors are isolated and do not mutate stored user customizations", () => {
  const { runtime, emit } = createRuntime();
  const preferences = {
    selectedPDFApplication: "custom-viewer",
    scanEnabled: true,
    userRule: "keep"
  };
  const snapshot = JSON.stringify(preferences);
  const errors = [];
  const stop = subscribeToExtensionUpdates(runtime, () => {
    throw Error("consumer failure");
  }, { onError(error) { errors.push(error.message); throw Error("error hook failure"); } });
  assert.doesNotThrow(() => emit({ reason: "update", previousVersion: "0.1.0" }));
  assert.deepEqual(errors, ["consumer failure"]);
  assert.equal(JSON.stringify(preferences), snapshot);
  stop();
});

test("registration and manifest lookup failures fail closed without hidden retries", () => {
  assert.throws(() => subscribeToExtensionUpdates({}, () => {}), TypeError);
  assert.throws(() => subscribeToExtensionUpdates(createRuntime().runtime, null), TypeError);
  const { runtime, counters, emit } = createRuntime();
  runtime.onInstalled.addListener = () => { throw Error("registration failed"); };
  assert.throws(() => subscribeToExtensionUpdates(runtime, () => {}), /registration failed/);
  assert.equal(counters.removed, 1, "best-effort rollback");
  const broken = createRuntime();
  broken.runtime.getManifest = () => { throw Error("/private/extension.json"); };
  const errors = [];
  let calls = 0;
  const stop = subscribeToExtensionUpdates(broken.runtime, () => { calls += 1; },
    { onError(error) { errors.push(error.message); } });
  broken.emit({ reason: "update", previousVersion: "0.1.0" });
  assert.equal(calls, 0);
  assert.deepEqual(errors, ["Extension update version unavailable"]);
  stop();
});

test("module does not access browser APIs or scanner and storage privileges", async () => {
  const source = await readFile(new URL("../src/extension-updates.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "localStorage", "storage.local",
    "storage.sync", "fetch(", "XMLHttpRequest", "WebSocket",
    "runtime.reload(", "permissions.request(", "nativeMessaging",
    "sendNativeMessage(", "scan-and-open", "window.open(",
    "node:fs", "node:child_process"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
