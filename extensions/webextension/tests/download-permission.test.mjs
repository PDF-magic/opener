import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { requestDownloadMonitoringPermission } from "../src/download-permission.js";

test("never asks for downloads access unless monitoring and a user gesture are explicit", async () => {
  const requests = [];
  const api = { request(details) { requests.push(details); return Promise.resolve(true); } };
  for (const options of [
    undefined, {}, { monitoringEnabled: true }, { userInitiated: true },
    { monitoringEnabled: false, userInitiated: true },
    { monitoringEnabled: true, userInitiated: false },
    { monitoringEnabled: 1, userInitiated: true },
    { monitoringEnabled: true, userInitiated: "true" }
  ]) {
    assert.equal(await requestDownloadMonitoringPermission(api, options), false);
  }
  assert.deepEqual(requests, []);
  assert.equal(await requestDownloadMonitoringPermission(api, {
    monitoringEnabled: true, userInitiated: true
  }), true);
  assert.deepEqual(requests, [{ permissions: ["downloads"] }]);
  assert.deepEqual(Object.keys(requests[0]), ["permissions"]);
});

test("permission request starts synchronously without a preceding asynchronous step", async () => {
  let requested = false;
  const api = { request() { requested = true; return Promise.resolve(true); } };
  const completion = requestDownloadMonitoringPermission(api, {
    monitoringEnabled: true, userInitiated: true
  });
  assert.equal(requested, true);
  assert.equal(await completion, true);
});

test("denied, rejected, unsupported or callback-only requests fail closed", async () => {
  const opts = { monitoringEnabled: true, userInitiated: true };
  for (const api of [
    null, {}, { request: true }, { request: () => false },
    { request: () => Promise.resolve(false) }, { request: () => undefined },
    { request: () => Promise.reject(new Error("private browser error")) },
    { request: () => { throw new Error("private browser error"); } }
  ]) {
    assert.equal(await requestDownloadMonitoringPermission(api, opts), false);
  }
  // Avoid invoking untrusted API getters just to check for availability.
  const api = Object.defineProperty({}, "request", {
    get() { throw new Error("permission API getter must not run"); }
  });
  assert.equal(await requestDownloadMonitoringPermission(api, opts), false);
});

test("manifest declares downloads as the only optional privilege, not an install-time grant", async () => {
  const load = async (url) => JSON.parse(await readFile(url, "utf8"));
  for (const path of ["../manifest.json", "../dist/manifest.json",
                      "../dist/firefox/manifest.json"]) {
    const manifest = await load(new URL(path, import.meta.url));
    assert.deepEqual(manifest.permissions, []);
    assert.deepEqual(manifest.host_permissions, []);
    assert.deepEqual(manifest.optional_permissions, ["downloads"]);
    assert.equal(manifest.optional_host_permissions, undefined);
    assert.equal(manifest.nativeMessaging, undefined);
    assert.equal(manifest.content_scripts, undefined);
    assert.equal(manifest.web_accessible_resources, undefined);
  }
});

test("helper has no automatic browser access or download listener wiring", async () => {
  const src = await readFile(new URL("../src/download-permission.js", import.meta.url), "utf8");
  assert.equal(src.includes("globalThis."), false);
  assert.equal(src.includes("subscribeToDownloadEvents("), false);
  for (const forbidden of [
    "chrome.permissions", "browser.permissions", "downloads.onCreated",
    "downloads.onChanged", "downloads.open(", "nativeMessaging", "fetch(",
    "localStorage", "sessionStorage", "sendNativeMessage(", "scan-and-open"
  ]) {
    // These names may appear only in comments explaining what's prohibited.
    const executable = src.replace(/\/\/[^\n]*/g, "");
    assert.equal(executable.includes(forbidden), false, forbidden);
  }
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url)));
  assert.deepEqual(manifest.background, { service_worker: "background.js", type: "module" });
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
});
