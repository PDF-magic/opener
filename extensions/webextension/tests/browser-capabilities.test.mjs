import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  BROWSER_CAPABILITY_NAMES, getBrowserCapabilityFlags
} from "../src/browser-capabilities.js";

const event = () => ({ addListener() {}, removeListener() {} });
const fullApi = () => ({
  runtime: {
    getManifest() {}, getURL() {}, sendMessage() {}, onMessage: event(),
    sendNativeMessage() {}
  },
  downloads: { onCreated: event(), onChanged: event(), onErased: event() }
});

test("flag catalog is stable, explicit and immutable", () => {
  assert.deepEqual(BROWSER_CAPABILITY_NAMES, [
    "runtimeMetadataApi", "runtimeMessagingApi", "downloadEventsApi",
    "nativeMessagingEnabled", "pdfOpeningEnabled", "scannerVerificationEnabled"
  ]);
  assert.ok(Object.isFrozen(BROWSER_CAPABILITY_NAMES));
  assert.deepEqual(Object.keys(getBrowserCapabilityFlags()), BROWSER_CAPABILITY_NAMES);
});

test("unknown, empty or malformed namespaces fail closed", () => {
  for (const value of [undefined, null, {}, 7, "firefox", []]) {
    const flags = getBrowserCapabilityFlags(value);
    assert.ok(Object.isFrozen(flags));
    assert.ok(Object.values(flags).every((capability) => capability === false));
  }
});

test("explicit browser, chrome or Safari-style API shape is detected consistently", () => {
  // Namespace selection is external: no platform guess from user agent or API name.
  for (const namespace of [fullApi(), fullApi(), fullApi()]) {
    const flags = getBrowserCapabilityFlags(namespace);
    assert.equal(flags.runtimeMetadataApi, true);
    assert.equal(flags.runtimeMessagingApi, true);
    assert.equal(flags.downloadEventsApi, true);
    assert.equal(flags.nativeMessagingEnabled, false);
    assert.equal(flags.pdfOpeningEnabled, false);
    assert.equal(flags.scannerVerificationEnabled, false);
  }
});

test("partial APIs do not advertise unsupported capabilities", () => {
  const api = fullApi();
  delete api.runtime.onMessage.removeListener;
  delete api.downloads.onChanged;
  let flags = getBrowserCapabilityFlags(api);
  assert.equal(flags.runtimeMetadataApi, true);
  assert.equal(flags.runtimeMessagingApi, false);
  assert.equal(flags.downloadEventsApi, false);
  delete api.runtime.getURL;
  flags = getBrowserCapabilityFlags(api);
  assert.equal(flags.runtimeMetadataApi, false);
});

test("API detection never invokes methods, getters or proxy traps recursively", () => {
  let invoked = 0;
  const api = fullApi();
  for (const obj of [api.runtime, api.downloads.onCreated]) {
    for (const key of Object.keys(obj)) {
      if (typeof obj[key] === "function") obj[key] = () => { invoked++; throw Error("must not call"); };
    }
  }
  const flags = getBrowserCapabilityFlags(api);
  assert.equal(flags.runtimeMetadataApi, true);
  assert.equal(flags.downloadEventsApi, true);
  assert.equal(invoked, 0);
  const hostile = Object.create(null);
  Object.defineProperty(hostile, "runtime", { get() { throw Error("no access"); } });
  assert.ok(Object.values(getBrowserCapabilityFlags(hostile)).every((x) => x === false));
  const trap = new Proxy({}, { getOwnPropertyDescriptor() { throw Error("blocked"); } });
  assert.ok(Object.values(getBrowserCapabilityFlags(trap)).every((x) => x === false));
});

test("prototype-inherited API methods cannot be silently accepted", () => {
  const inherited = Object.create({ sendMessage() {} });
  inherited.getManifest = () => ({});
  inherited.getURL = () => "";
  inherited.onMessage = event();
  const flags = getBrowserCapabilityFlags({ runtime: inherited });
  assert.equal(flags.runtimeMetadataApi, true);
  assert.equal(flags.runtimeMessagingApi, false);
});

test("returned flags are fresh, immutable snapshots", () => {
  const api = fullApi();
  const before = getBrowserCapabilityFlags(api);
  assert.ok(Object.isFrozen(before));
  assert.throws(() => { before.downloadEventsApi = false; }, TypeError);
  delete api.downloads;
  const after = getBrowserCapabilityFlags(api);
  assert.equal(before.downloadEventsApi, true);
  assert.equal(after.downloadEventsApi, false);
});

test("module does not activate browser integrations or unsafe transports", async () => {
  const source = await readFile(
    fileURLToPath(new URL("../src/browser-capabilities.js", import.meta.url)), "utf8"
  );
  for (const forbidden of [
    "globalThis.browser", "globalThis.chrome", "navigator.userAgent", "addListener(",
    "sendNativeMessage(", "sendMessage(", "fetch(", "window.open(", "browser.permissions.request"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
