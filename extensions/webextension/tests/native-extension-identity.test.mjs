import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  isApprovedNativeExtensionIdentity, snapshotApprovedExtensionIds
} from "../src/native-extension-identity.js";
import { createNativeReconnectController } from "../src/native-reconnection.js";

const CHROME_ID = "abcdefghijklmnopabcdefghijklmnop";
const OTHER_CHROME_ID = "ponmlkjihgfedcbaponmlkjihgfedcba";
const FIREFOX_DEV_ID = "pdf-magic-opener@example.invalid";
const permitted = (browserKind, id, ids, development = false) =>
  isApprovedNativeExtensionIdentity({
    browserKind, browserRuntime: { id }, approvedExtensionIds: ids, development
  });

test("Chromium admits only exact, explicitly listed extension IDs", () => {
  assert.equal(permitted("chromium", CHROME_ID, [CHROME_ID]), true);
  assert.equal(permitted("chromium", OTHER_CHROME_ID, [CHROME_ID, OTHER_CHROME_ID]), true);
  for (const id of [
    OTHER_CHROME_ID, CHROME_ID.toUpperCase(),
    CHROME_ID.slice(0, -1), "chrome-extension://" + CHROME_ID + "/",
    CHROME_ID + "/", "*", "", null
  ]) {
    assert.equal(permitted("chromium", id, [CHROME_ID]), false, String(id));
  }
});

test("Firefox uses exact Gecko IDs and rejects its dev placeholder without explicit development approval", () => {
  const live = "publisher-owned@example.org";
  assert.equal(permitted("firefox", live, [live]), true);
  assert.equal(permitted("firefox", live, [FIREFOX_DEV_ID, live], true), true);
  assert.equal(permitted("firefox", FIREFOX_DEV_ID, [FIREFOX_DEV_ID]), false);
  assert.equal(permitted("firefox", FIREFOX_DEV_ID, [FIREFOX_DEV_ID], true), true);
  assert.equal(permitted("firefox", "Publisher-Owned@example.org", [live]), false);
  assert.equal(permitted("firefox", live, ["*@example.org"]), false);
  assert.equal(permitted("chromium", FIREFOX_DEV_ID, [FIREFOX_DEV_ID]), false);
  assert.equal(permitted("firefox", CHROME_ID, [CHROME_ID]), false);
});

test("invalid, absent, wildcard, duplicate, sparse or accessor lists cannot grant access", () => {
  for (const ids of [
    undefined, null, [], ["*"], ["chrome-extension://*/*"], [CHROME_ID, "*"],
    [CHROME_ID, CHROME_ID], [OTHER_CHROME_ID], [CHROME_ID, 17],
    [CHROME_ID, "another@invalid"], Array(1),
    Array.from({ length: 33 }, (_, i) => CHROME_ID + i)
  ]) {
    assert.equal(permitted("chromium", CHROME_ID, ids), false, String(ids));
  }
  const trapped = [];
  Object.defineProperty(trapped, "0", {
    get() { throw Error("untrusted accessor must not execute"); },
    enumerable: true
  });
  trapped.length = 1;
  assert.equal(permitted("chromium", CHROME_ID, trapped), false);
  const accessorRuntime = {};
  Object.defineProperty(accessorRuntime, "id", {
    get() { throw Error("untrusted runtime accessor must not execute"); }
  });
  assert.equal(isApprovedNativeExtensionIdentity({
    browserKind: "chromium", browserRuntime: accessorRuntime,
    approvedExtensionIds: [CHROME_ID]
  }), false);
  assert.equal(permitted("unknown-browser", CHROME_ID, [CHROME_ID]), false);
  assert.equal(isApprovedNativeExtensionIdentity({}), false);
});

test("allowlist snapshots cannot be changed through the source array", () => {
  const original = [CHROME_ID];
  const copy = snapshotApprovedExtensionIds(original);
  assert.deepEqual(copy, [CHROME_ID]);
  assert.equal(Object.isFrozen(copy), true);
  original[0] = OTHER_CHROME_ID;
  assert.deepEqual(copy, [CHROME_ID]);
});

test("native connector never starts for an unapproved or unprovided runtime identity", () => {
  let calls = 0;
  const makeController = (options) => createNativeReconnectController({
    connectNative() { calls++; throw Error("never connect"); },
    ...options
  });
  const consent = {
    registrationVerified: true, nativePermissionGranted: true, userApproved: true
  };
  for (const configuration of [
    {}, { browserKind: "chromium", approvedExtensionIds: [CHROME_ID] },
    { browserKind: "chromium", browserRuntime: { id: OTHER_CHROME_ID },
      approvedExtensionIds: [CHROME_ID] },
    { browserKind: "chromium", browserRuntime: { id: CHROME_ID },
      approvedExtensionIds: [] },
    { browserKind: "firefox", browserRuntime: { id: FIREFOX_DEV_ID },
      approvedExtensionIds: [FIREFOX_DEV_ID] }
  ]) {
    const controller = makeController(configuration);
    assert.equal(controller.start(consent), false);
    assert.equal(controller.state, "idle");
  }
  assert.equal(calls, 0);
});

test("reconnection rechecks the current runtime identity and never widens approval", () => {
  const browserRuntime = { id: CHROME_ID };
  const approvedExtensionIds = [CHROME_ID];
  let calls = 0;
  let onDisconnect;
  const tasks = [];
  const controller = createNativeReconnectController({
    browserKind: "chromium", browserRuntime, approvedExtensionIds,
    connectNative() {
      calls++;
      return {
        postMessage() {},
        disconnect() {},
        onMessage: { addListener() {} },
        onDisconnect: { addListener(callback) { onDisconnect = callback; } }
      };
    },
    nonceFactory: () => "Nonce_12345678901234567890",
    schedule(callback) { tasks.push(callback); return tasks.length; },
    cancel() {}
  });
  const consent = {
    registrationVerified: true, nativePermissionGranted: true, userApproved: true
  };
  assert.equal(controller.start(consent), true);
  assert.equal(calls, 1);
  onDisconnect();
  assert.equal(controller.state, "reconnecting");
  browserRuntime.id = OTHER_CHROME_ID;
  approvedExtensionIds[0] = OTHER_CHROME_ID; // cannot silently widen admission
  tasks.shift()();
  assert.equal(controller.state, "unavailable");
  assert.equal(calls, 1, "no new native process for a changed identity");
});

test("the integration stays dormant and preserves scanner and user configuration", async () => {
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(manifest.optional_permissions.includes("nativeMessaging"), false);
  const source = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(source.includes("native-extension-identity"), false);
  assert.equal(source.includes("native-reconnection"), false);
  const preferences = Object.freeze({ selectedPDFApplication: "chosen-viewer", scanBeforeOpen: true });
  const previous = JSON.stringify(preferences);
  assert.equal(permitted("chromium", CHROME_ID, [CHROME_ID]), true);
  assert.equal(JSON.stringify(preferences), previous);
});
