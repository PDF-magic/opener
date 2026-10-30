import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { requestLocalNativeMessagingPermission } from "../src/local-native-permission.js";

const identityURL = new URL("../../../native-messaging/host-identity.json", import.meta.url);
const sourceManifestURL = new URL("../manifest.json", import.meta.url);

async function readJson(url) {
  return JSON.parse(await readFile(url, "utf8"));
}

test("native messaging host has one stable, portable, version-independent name", async () => {
  const identity = await readJson(identityURL);
  assert.deepEqual(identity, { name: "org.pdfmagic.opener" });
  assert.ok(identity.name.length <= 128);
  assert.match(identity.name, /^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$/);
  assert.equal(identity.name.includes("@"), false, "not a Firefox add-on ID");
  assert.equal(identity.name.includes("/"), false, "not a path or address");
});

test("the canonical host name is accepted only by the existing guarded opt-in helper", async () => {
  const { name } = await readJson(identityURL);
  const optInManifest = {
    manifest_version: 3,
    permissions: [],
    host_permissions: [],
    optional_permissions: ["nativeMessaging"]
  };
  const calls = [];
  const permissionsApi = {
    request(value) {
      calls.push(value);
      return Promise.resolve(true);
    }
  };
  const args = {
    permissionsApi,
    manifest: optInManifest,
    localHost: { name, registrationVerified: true },
    userInitiated: true
  };
  assert.deepEqual(await requestLocalNativeMessagingPermission(args), {
    granted: true, reason: "granted"
  });
  assert.deepEqual(calls, [{ permissions: ["nativeMessaging"] }]);

  for (const invalidHost of [
    { name, registrationVerified: false },
    { name },
    { name: "https://not-a-local-host.invalid", registrationVerified: true }
  ]) {
    assert.deepEqual(
      await requestLocalNativeMessagingPermission({ ...args, localHost: invalidHost }),
      { granted: false, reason: "local-integration-required" }
    );
  }
  assert.equal(calls.length, 1, "unverified hosts never request access");
});

test("defining a host identifier does not activate native messaging or scanner access", async () => {
  const manifest = await readJson(sourceManifestURL);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  const { name } = await readJson(identityURL);
  let called = false;
  const response = await requestLocalNativeMessagingPermission({
    permissionsApi: { request() { called = true; return Promise.resolve(true); } },
    manifest,
    localHost: { name, registrationVerified: true },
    userInitiated: true
  });
  assert.deepEqual(response, {
    granted: false, reason: "optional-permission-unavailable"
  });
  assert.equal(called, false);
});
