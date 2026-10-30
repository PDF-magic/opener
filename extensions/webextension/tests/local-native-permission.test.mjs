import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { requestLocalNativeMessagingPermission } from "../src/local-native-permission.js";

const manifest = Object.freeze({
  manifest_version: 3,
  permissions: [],
  host_permissions: [],
  optional_permissions: ["nativeMessaging"]
});
const host = Object.freeze({ name: "org.pdfmagic.opener", registrationVerified: true });

function mockApi(response) {
  const responseValue = arguments.length === 0 ? true : response;
  const calls = [];
  const permissionsApi = {
    request(input) {
      calls.push(input);
      return Promise.resolve(responseValue);
    }
  };
  return { permissionsApi, calls };
}

const request = (args = {}) => requestLocalNativeMessagingPermission({
  manifest, localHost: host, userInitiated: true, ...args
});

test("the current inactive extension does not declare native messaging", async () => {
  const source = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  const built = JSON.parse(await readFile(new URL("../dist/manifest.json", import.meta.url), "utf8"));
  const firefox = JSON.parse(await readFile(new URL("../dist/firefox/manifest.json", import.meta.url), "utf8"));
  for (const deployed of [source, built, firefox]) {
    assert.deepEqual(deployed.permissions, []);
    assert.deepEqual(deployed.host_permissions, []);
    assert.equal(deployed.optional_permissions, undefined);
    const { permissionsApi, calls } = mockApi();
    assert.deepEqual(await request({ manifest: deployed, permissionsApi }), {
      granted: false, reason: "optional-permission-unavailable"
    });
    assert.equal(calls.length, 0);
  }
});

test("a verified registered local integration and user gesture are both mandatory", async () => {
  const { permissionsApi, calls } = mockApi();
  const cases = [
    { userInitiated: false }, { userInitiated: "yes" },
    { localHost: null }, { localHost: { name: "org.pdfmagic.opener" } },
    { localHost: { name: "org.pdfmagic.opener", registrationVerified: false } },
    { localHost: { name: "https://remote.invalid", registrationVerified: true } },
    { localHost: { name: "../local", registrationVerified: true } },
    { localHost: { name: "local", registrationVerified: true } },
    { localHost: { name: "x".repeat(129), registrationVerified: true } }
  ];
  for (const item of cases) {
    assert.deepEqual(await request({ permissionsApi, ...item }), {
      granted: false, reason: "local-integration-required"
    });
  }
  assert.equal(calls.length, 0);
});

test("optional nativeMessaging must be declared alone, not pregranted or combined with host access", async () => {
  const { permissionsApi, calls } = mockApi();
  for (const invalid of [
    {}, { ...manifest, optional_permissions: [] },
    { ...manifest, optional_permissions: ["downloads", "nativeMessaging"] },
    { ...manifest, optional_permissions: ["nativeMessaging", "nativeMessaging"] },
    { ...manifest, permissions: ["nativeMessaging"] },
    { ...manifest, host_permissions: ["<all_urls>"] },
    { ...manifest, optional_host_permissions: ["https://example.invalid/*"] },
    { ...manifest, manifest_version: 2 },
    { ...manifest, optional_permissions: "nativeMessaging" }
  ]) {
    assert.deepEqual(await request({ manifest: invalid, permissionsApi }), {
      granted: false, reason: "optional-permission-unavailable"
    });
  }
  assert.equal(calls.length, 0);
});

test("a valid local user action requests only nativeMessaging, directly before Promise settlement", async () => {
  const calls = [];
  const permissionsApi = {
    request(input) {
      calls.push(input);
      return Promise.resolve(true);
    }
  };
  const pending = request({ permissionsApi });
  assert.deepEqual(calls, [{ permissions: ["nativeMessaging"] }],
    "call occurs synchronously inside the direct gesture handler");
  const outcome = await pending;
  assert.deepEqual(outcome, { granted: true, reason: "granted" });
  assert.equal(Object.isFrozen(outcome), true);
  assert.deepEqual(Object.keys(outcome).sort(), ["granted", "reason"]);
});

test("denial, non-boolean response, and a rejected permission request never grant access", async () => {
  for (const value of [false, null, undefined, "true", 1]) {
    const { permissionsApi } = mockApi(value);
    assert.deepEqual(await request({ permissionsApi }), { granted: false, reason: "denied" });
  }
  assert.deepEqual(await request({ permissionsApi: { request: () => Promise.reject(Error("/private/host/path")) } }), {
    granted: false, reason: "permission-request-failed"
  });
  assert.deepEqual(await request({ permissionsApi: { request() { throw Error("/private/host/path"); } } }), {
    granted: false, reason: "permission-request-failed"
  });
});

test("missing or non-Promise permission APIs are rejected without a callback fallback", async () => {
  assert.deepEqual(await request({ permissionsApi: {} }), {
    granted: false, reason: "permission-api-unavailable"
  });
  assert.deepEqual(await request({ permissionsApi: { request: () => true } }), {
    granted: false, reason: "permission-api-unavailable"
  });
});

test("untrusted getters are not executed on integration and browser API records", async () => {
  const evilHost = {};
  Object.defineProperty(evilHost, "registrationVerified", {
    get() { throw Error("host getter must not run"); }
  });
  assert.deepEqual(await request({ localHost: evilHost }), {
    granted: false, reason: "local-integration-required"
  });
  const evilApi = {};
  Object.defineProperty(evilApi, "request", {
    get() { throw Error("API getter must not run"); }
  });
  assert.deepEqual(await request({ permissionsApi: evilApi }), {
    granted: false, reason: "permission-api-unavailable"
  });
  const evilManifest = { ...manifest };
  Object.defineProperty(evilManifest, "optional_permissions", {
    get() { throw Error("manifest getter must not run"); }
  });
  assert.deepEqual(await request({ permissionsApi: mockApi().permissionsApi, manifest: evilManifest }), {
    granted: false, reason: "optional-permission-unavailable"
  });
});

test("permission request does not mutate a customized application selection or scanning policy", async () => {
  const prefs = Object.freeze({ selectedPDFApplication: "my-custom-viewer", scanBeforeOpen: true });
  const before = JSON.stringify(prefs);
  const { permissionsApi } = mockApi(true);
  assert.deepEqual(await request({ permissionsApi }), { granted: true, reason: "granted" });
  assert.equal(JSON.stringify(prefs), before);
});

test("module never opens native connections, requests other privileges or accesses storage", async () => {
  const source = await readFile(new URL("../src/local-native-permission.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "sendNativeMessage(", "connectNative(", "fetch(",
    "storage.local", "localStorage", "window.open(", "scan-and-open",
    "permissions.remove(", "node:fs", "node:child_process"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
