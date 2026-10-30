import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { requestDownloadMonitoringPermission } from "../src/download-permission.js";
import { requestOptionalSitePermission } from "../src/optional-site-permissions.js";
import { requestLocalNativeMessagingPermission } from "../src/local-native-permission.js";
import { createPermissionDenialHandler } from "../src/permission-denials.js";
import { subscribeToPermissionRevocations } from "../src/permission-revocations.js";

const manifest = async () => JSON.parse(
  await readFile(new URL("../manifest.json", import.meta.url), "utf8")
);
const consent = { monitoringEnabled: true, userInitiated: true };

function safariPermissionFixture() {
  const calls = [];
  const listeners = new Set();
  const api = {
    request(details) {
      calls.push(details);
      return Promise.resolve(false);
    },
    onRemoved: {
      addListener(listener) { listeners.add(listener); },
      removeListener(listener) { listeners.delete(listener); }
    }
  };
  return {
    api, calls, listeners,
    revoke(details) { for (const listener of [...listeners]) listener(details); }
  };
}

test("Safari's shared extension manifest has zero required or site permissions", async () => {
  const source = await manifest();
  assert.equal(source.manifest_version, 3);
  assert.deepEqual(source.permissions, []);
  assert.deepEqual(source.host_permissions, []);
  assert.deepEqual(source.optional_permissions, ["downloads"]);
  assert.equal(Object.hasOwn(source, "optional_host_permissions"), false);
  assert.equal(source.incognito, "not_allowed");
  for (const key of ["content_scripts", "externally_connectable", "web_accessible_resources"]) {
    assert.equal(Object.hasOwn(source, key), false, key);
  }
  assert.equal(JSON.stringify(source).includes("nativeMessaging"), false);
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background,
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "void 0;\n");
});

test("Safari permission prompt is opt-in and limited to downloads", async () => {
  const fixture = safariPermissionFixture();
  for (const options of [
    undefined, {}, { monitoringEnabled: true }, { userInitiated: true },
    { monitoringEnabled: false, userInitiated: true },
    { monitoringEnabled: true, userInitiated: false }
  ]) {
    assert.equal(await requestDownloadMonitoringPermission(fixture.api, options), false);
  }
  assert.deepEqual(fixture.calls, [], "no permission prompts during startup or without consent");

  let requestedSynchronously = false;
  const api = {
    request(details) {
      requestedSynchronously = true;
      assert.deepEqual(details, { permissions: ["downloads"] });
      return Promise.resolve(true);
    }
  };
  const result = requestDownloadMonitoringPermission(api, consent);
  assert.equal(requestedSynchronously, true, "the request must begin in the user's action");
  assert.equal(await result, true, "a grant is only download API consent, not PDF authorization");
  assert.deepEqual(fixture.calls, []);
});

test("Safari denial, rejected prompt, and unsupported permission APIs fail closed", async () => {
  const fixture = safariPermissionFixture();
  assert.equal(await requestDownloadMonitoringPermission(fixture.api, consent), false);
  assert.deepEqual(fixture.calls, [{ permissions: ["downloads"] }]);
  for (const api of [
    null, {}, { request: () => undefined },
    { request: () => Promise.resolve(false) },
    { request: () => Promise.resolve("granted") },
    { request: () => Promise.reject(new Error("private document path")) },
    { request: () => { throw new Error("private document path"); } }
  ]) {
    assert.equal(await requestDownloadMonitoringPermission(api, consent), false);
  }
  let getterCalls = 0;
  const hostile = Object.defineProperty({}, "request", {
    get() { getterCalls++; throw new Error("unexpected browser API getter"); }
  });
  assert.equal(await requestDownloadMonitoringPermission(hostile, consent), false);
  assert.equal(getterCalls, 0);
});

test("Safari permission denial stops protected work once and never approves a PDF", async () => {
  let shutdowns = 0;
  const controller = createPermissionDenialHandler(() => { shutdowns++; });
  const denied = await controller.handle(false);
  assert.equal(denied.status, "denied");
  assert.equal(denied.canProceed, false);
  assert.equal(denied.scannerVerified, false);
  assert.equal(denied.authorizesOpen, false);
  assert.equal((await controller.handle(true)).status, "denied");
  assert.equal(shutdowns, 1, "late grants never undo a denial");

  const unsupported = await createPermissionDenialHandler().handle(undefined);
  assert.equal(unsupported.status, "unavailable");
  assert.equal(unsupported.authorizesOpen, false);
});

test("Safari-like permission removal immediately latches lost access without regranting", () => {
  const fixture = safariPermissionFixture();
  const observed = [];
  let observer;
  observer = subscribeToPermissionRevocations(fixture.api, (state) => {
    assert.equal(observer.isRevoked("downloads"), true);
    observed.push(state);
  });
  assert.equal(observer.state().permissionsVerified, false);
  fixture.revoke({ permissions: ["downloads"] });
  fixture.revoke({ permissions: ["downloads"] });
  assert.equal(observed.length, 1);
  assert.equal(observed[0].downloadsRevoked, true);
  assert.equal(observed[0].authorizesOpen, false);
  assert.deepEqual(fixture.calls, [], "revocation never triggers a new prompt");
  observer.unsubscribe();
  fixture.revoke({ permissions: ["nativeMessaging"] });
  assert.equal(observed.length, 1);
  assert.equal(fixture.listeners.size, 0);
  assert.equal(observer.isRevoked("downloads"), true);
});

test("Safari cannot request undeclared site or native messaging permissions", async () => {
  const source = await manifest();
  const fixture = safariPermissionFixture();
  const site = await requestOptionalSitePermission(fixture.api, source, {
    siteOrigin: "https://example.org/", siteFeatureEnabled: true, userInitiated: true
  });
  assert.equal(site.status, "unavailable");
  assert.equal(site.sitePermissionVerified, false);
  assert.equal(site.authorizesOpen, false);
  const native = await requestLocalNativeMessagingPermission({
    permissionsApi: fixture.api, manifest: source,
    localHost: { name: "org.example.pdfmagic", registrationVerified: true },
    userInitiated: true
  });
  assert.equal(native.granted, false);
  assert.equal(native.reason, "optional-permission-unavailable");
  assert.deepEqual(fixture.calls, [], "undeclared privileges must not prompt");
});

test("permission handling does not change the user's PDF destination", async () => {
  const preferences = Object.freeze({
    selectedPDFApplication: "custom-browser", monitoringEnabled: false
  });
  const before = JSON.stringify(preferences);
  const fixture = safariPermissionFixture();
  await requestDownloadMonitoringPermission(fixture.api, {
    monitoringEnabled: preferences.monitoringEnabled, userInitiated: true
  });
  assert.deepEqual(fixture.calls, []);
  assert.equal(JSON.stringify(preferences), before);
});
