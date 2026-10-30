import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { credentialFreeNativeMessage } from "../src/native-credential-boundary.js";
import { createNativeReconnectController } from "../src/native-reconnection.js";

const challenge = "Nonce_12345678901234567890";
const valid = () => ({
  version: 1, kind: "request", topic: "host.handshake",
  requestId: `hello_${challenge}`, payload: { clientNonce: challenge }
});

test("only a new, detached, exact handshake envelope is permitted", () => {
  const proposed = valid();
  const safe = credentialFreeNativeMessage(proposed);
  assert.deepEqual(safe, valid());
  assert.notEqual(safe, proposed);
  assert.notEqual(safe.payload, proposed.payload);
  assert.equal(Object.isFrozen(safe), true);
  assert.equal(Object.isFrozen(safe.payload), true);
  proposed.payload.clientNonce = "changed";
  assert.equal(safe.payload.clientNonce, challenge);
});

test("credential-like browser fields anywhere in the envelope are rejected rather than transmitted", () => {
  const secret = "private-test-credential-not-real";
  for (const field of [
    "cookie", "cookies", "authorization", "headers", "password",
    "accessToken", "refreshToken", "sessionToken", "credentials",
    "browserStorage", "url", "referrer", "document", "scanPath"
  ]) {
    assert.equal(credentialFreeNativeMessage({ ...valid(), [field]: secret }), null, field);
    assert.equal(credentialFreeNativeMessage({
      ...valid(), payload: { clientNonce: challenge, [field]: secret }
    }), null, field);
  }
});

test("unapproved topics and malformed or credential-bearing challenges fail closed", () => {
  for (const topic of [
    "host.ping", "host.health", "scan.request", "scan.status",
    "scan.result", "scan.cancel", "pdf.open", "process.exec"
  ]) {
    assert.equal(credentialFreeNativeMessage({ ...valid(), topic }), null, topic);
  }
  for (const modification of [
    { kind: "event" }, { version: 2 }, { requestId: "old_request" },
    { payload: null }, { payload: {} }, { payload: { clientNonce: 17 } },
    { payload: { clientNonce: "Bearer user-secret" } },
    { payload: { clientNonce: "https://user:password@example.invalid/" } },
    { payload: { clientNonce: "/home/user/browser-profile" } },
    { payload: { clientNonce: "short" } }
  ]) assert.equal(credentialFreeNativeMessage({ ...valid(), ...modification }), null);
});

test("accessors, inherited data, symbols and hostile proxies never provide credentials", () => {
  let accessed = 0;
  const badEnvelope = valid();
  Object.defineProperty(badEnvelope, "topic", {
    enumerable: true, get() { accessed++; throw Error("must not read browser secrets"); }
  });
  const badPayload = valid();
  Object.defineProperty(badPayload.payload, "clientNonce", {
    enumerable: true, get() { accessed++; throw Error("must not read browser secrets"); }
  });
  const symbol = valid();
  symbol[Symbol("secret")] = "not-real";
  const inherited = Object.assign(Object.create({ version: 1 }), valid());
  const proxy = new Proxy(valid(), {
    ownKeys() { throw Error("hostile browser object"); }
  });
  for (const input of [badEnvelope, badPayload, symbol, inherited, proxy,
    null, undefined, "host.handshake", [], 123]) {
    assert.equal(credentialFreeNativeMessage(input), null);
  }
  assert.equal(accessed, 0);
});

test("native reconnection never reads or forwards browser credential properties", () => {
  const secret = "TEST_ONLY_NOT_A_CREDENTIAL";
  let reads = 0;
  const browserRuntime = { id: "abcdefghijklmnopabcdefghijklmnop" };
  for (const name of ["cookies", "authorization", "sessionToken"]) {
    Object.defineProperty(browserRuntime, name, {
      get() { reads++; throw Error(secret); }
    });
  }
  const sent = [];
  const port = {
    postMessage(value) { sent.push(value); },
    disconnect() {},
    onMessage: { addListener() {} },
    onDisconnect: { addListener() {} }
  };
  const controller = createNativeReconnectController({
    connectNative() { return port; },
    browserKind: "chromium", browserRuntime,
    approvedExtensionIds: [browserRuntime.id],
    nonceFactory: () => challenge,
    schedule() { return 1; }, cancel() {}
  });
  const consent = {
    registrationVerified: true, nativePermissionGranted: true, userApproved: true,
    cookie: secret, headers: { authorization: secret }
  };
  assert.equal(controller.start(consent), true);
  assert.equal(reads, 0);
  assert.deepEqual(sent, [valid()]);
  assert.equal(JSON.stringify(sent).includes(secret), false);
  controller.stop();
});

test("a browser credential object cannot be used as the handshake challenge", () => {
  const sent = [];
  let reads = 0;
  const credential = { clientNonce: challenge };
  Object.defineProperty(credential, "cookies", {
    get() { reads++; throw Error("never inspect browser storage"); }
  });
  let disconnected = false;
  const controller = createNativeReconnectController({
    connectNative() {
      return {
        postMessage(value) { sent.push(value); },
        disconnect() { disconnected = true; },
        onMessage: { addListener() {} },
        onDisconnect: { addListener() {} }
      };
    },
    browserKind: "chromium",
    browserRuntime: { id: "abcdefghijklmnopabcdefghijklmnop" },
    approvedExtensionIds: ["abcdefghijklmnopabcdefghijklmnop"],
    nonceFactory: () => credential,
    schedule() { return 1; }, cancel() {}
  });
  assert.equal(controller.start({
    registrationVerified: true, nativePermissionGranted: true, userApproved: true
  }), true);
  assert.equal(controller.state, "unavailable");
  assert.equal(disconnected, true);
  assert.deepEqual(sent, []);
  assert.equal(reads, 0);
});

test("built extension remains inactive and exposes no credential or native permission APIs", async () => {
  const root = new URL("../", import.meta.url);
  const source = await readFile(new URL("src/background.js", root), "utf8");
  for (const file of ["src/background.js", "dist/background.js", "dist/firefox/background.js"]) {
    assert.equal(await readFile(new URL(file, root), "utf8"), source);
  }
  for (const file of ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"]) {
    const manifest = JSON.parse(await readFile(new URL(file, root), "utf8"));
    assert.equal(manifest.permissions.includes("nativeMessaging"), false);
    assert.equal(manifest.optional_permissions.includes("nativeMessaging"), false);
    assert.deepEqual(manifest.host_permissions, []);
  }
  const helper = await readFile(new URL("src/native-credential-boundary.js", root), "utf8");
  for (const forbidden of [
    "chrome.cookies", "browser.cookies", "webRequest", "onMessageExternal",
    "localStorage", "storage.local", "fetch(", "sendNativeMessage(",
    "connectNative(", "document.cookie"
  ]) assert.equal(helper.includes(forbidden), false, forbidden);
});
