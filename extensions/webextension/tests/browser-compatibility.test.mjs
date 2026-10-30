import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createBrowserCompatibility } from "../src/browser-compatibility.js";

const fakeRuntime = (extra = {}) => ({
  getManifest: () => ({ manifest_version: 3, permissions: [] }),
  getURL: (path) => `extension://test/${path}`,
  ...extra
});

test("import does not inspect global browser APIs or activate integration", async () => {
  const source = await readFile(fileURLToPath(new URL("../src/browser-compatibility.js", import.meta.url)), "utf8");
  for (const forbidden of ["globalThis.browser", "globalThis.chrome", "addListener(",
    "requestPermission", "nativeMessaging", "sendMessage(", "downloads.download(",
    "fetch(", "open(", "clamscan(", "FileReader("]) {
    assert.equal(source.includes(forbidden), false, `unexpected runtime activation: ${forbidden}`);
  }
});

test("Firefox Promise namespace is preferred over Chrome's compatibility alias", async () => {
  let browserCalls = 0;
  let chromeCalls = 0;
  const adapter = createBrowserCompatibility({
    browser: { runtime: fakeRuntime({ getPlatformInfo: async () => {
      browserCalls++;
      return { os: "mac", arch: "arm" };
    } }) },
    chrome: { runtime: fakeRuntime({ getPlatformInfo: (_cb) => { chromeCalls++; } }) }
  });
  assert.equal(adapter.namespace, "browser");
  assert.equal(browserCalls, 0);
  assert.equal(chromeCalls, 0);
  assert.deepEqual(await adapter.getPlatformInfo(), { os: "mac", arch: "arm" });
  assert.equal(browserCalls, 1);
  assert.equal(chromeCalls, 0);
  assert.ok(Object.isFrozen(adapter));
});

test("Chromium callback namespace resolves metadata without assuming Promises", async () => {
  let observedCallback = null;
  const adapter = createBrowserCompatibility({ chrome: { runtime: fakeRuntime({
    getPlatformInfo(callback) {
      observedCallback = callback;
    }
  }) } });
  assert.equal(adapter.namespace, "chrome");
  const result = adapter.getPlatformInfo();
  assert.equal(typeof observedCallback, "function");
  observedCallback({ os: "linux", arch: "x86-64" });
  assert.deepEqual(await result, { os: "linux", arch: "x86-64" });
});

test("Safari can use browser namespace without user-agent sniffing", async () => {
  const adapter = createBrowserCompatibility({ browser: { runtime: fakeRuntime({
    getPlatformInfo: async () => ({ os: "mac", arch: "arm" })
  }) } });
  assert.equal(adapter.namespace, "browser");
  assert.deepEqual(await adapter.getPlatformInfo(), { os: "mac", arch: "arm" });
});

test("Safari can use Chrome-compatible namespace if only that is exposed", async () => {
  const adapter = createBrowserCompatibility({ chrome: { runtime: fakeRuntime({
    getPlatformInfo: (callback) => callback({ os: "mac", arch: "arm" })
  }) } });
  assert.equal(adapter.namespace, "chrome");
  assert.deepEqual(await adapter.getPlatformInfo(), { os: "mac", arch: "arm" });
});

test("missing and incomplete browser APIs fail closed", () => {
  for (const globals of [undefined, null, 4, {}, { browser: { runtime: {} } },
    { chrome: { runtime: { getURL() {} } } }]) {
    assert.throws(() => createBrowserCompatibility(globals));
  }
});

test("incomplete browser namespace falls back only to a complete chrome runtime", () => {
  const adapter = createBrowserCompatibility({ browser: { runtime: {} }, chrome: { runtime: fakeRuntime() } });
  assert.equal(adapter.namespace, "chrome");
});

test("manifest and resource APIs remain explicit and permission-free", () => {
  let called = 0;
  const adapter = createBrowserCompatibility({ browser: { runtime: fakeRuntime({
    getManifest: () => { called++; return { permissions: [] }; },
    getURL: (path) => { called++; return `extension://test/${path}`; }
  }) } });
  assert.equal(called, 0);
  assert.deepEqual(adapter.getManifest(), { permissions: [] });
  assert.equal(adapter.getResourceURL("icons/icon-32.png"), "extension://test/icons/icon-32.png");
  assert.equal(called, 2);
});

test("resource URL helper rejects absolute paths, traversal and external URLs", () => {
  const adapter = createBrowserCompatibility({ browser: { runtime: fakeRuntime() } });
  for (const path of ["", "/etc/passwd", "../secret", "safe/../secret", "safe//icon.png",
    "./image.png", "https://example.com/a", "icons\\icon.png", "icon.png?x=y",
    "icon.png#fragment", "%2e%2e/file", "a".repeat(257), null, 5]) {
    assert.throws(() => adapter.getResourceURL(path));
  }
  assert.equal(adapter.getResourceURL("icons/a.png"), "extension://test/icons/a.png");
});

test("optional API absence is explicit rather than silently claiming support", async () => {
  const adapter = createBrowserCompatibility({ browser: { runtime: fakeRuntime() } });
  await assert.rejects(adapter.getPlatformInfo(), /unavailable/);
});

test("Promise and callback errors are generic and cannot leak runtime messages", async () => {
  const sensitive = "/Users/private-user/secret.pdf";
  const firefox = createBrowserCompatibility({ browser: { runtime: fakeRuntime({
    getPlatformInfo: async () => { throw new Error(sensitive); }
  }) } });
  const chrome = createBrowserCompatibility({ chrome: { runtime: fakeRuntime({
    getPlatformInfo: (callback) => callback({ os: "mac" }),
    get lastError() { return { message: sensitive }; }
  }) } });
  for (const adapter of [firefox, chrome]) {
    await assert.rejects(adapter.getPlatformInfo(), (error) => {
      assert.equal(error.message.includes(sensitive), false);
      return true;
    });
  }
});

test("runtime errors and callback exceptions cannot expose sensitive diagnostics", async () => {
  const err = new Error("/private/failing-path.pdf");
  const browserAdapter = createBrowserCompatibility({ browser: { runtime: fakeRuntime({
    getManifest: () => { throw err; }, getURL: () => { throw err; }
  }) } });
  assert.throws(() => browserAdapter.getManifest(), (error) => error.message !== err.message);
  assert.throws(() => browserAdapter.getResourceURL("icons/test.png"), (error) => error.message !== err.message);
  const chromeAdapter = createBrowserCompatibility({ chrome: { runtime: fakeRuntime({
    getPlatformInfo: () => { throw err; }
  }) } });
  await assert.rejects(chromeAdapter.getPlatformInfo(), (error) => error.message !== err.message);
});
