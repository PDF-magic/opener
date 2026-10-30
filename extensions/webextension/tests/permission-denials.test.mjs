import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createPermissionDenialHandler, PERMISSION_DENIAL_MESSAGES
} from "../src/permission-denials.js";

function blocked(result) {
  assert.equal(result.canProceed, false);
  assert.equal(result.scannerVerified, false);
  assert.equal(result.authorizesOpen, false);
  assert.ok(Object.isFrozen(result));
  assert.equal(typeof result.message, "string");
}

test("denial handler is inert until a permission result is supplied", () => {
  let shutdowns = 0;
  const handler = createPermissionDenialHandler(() => { shutdowns++; });
  const snapshot = handler.state();
  assert.equal(snapshot.status, "unverified");
  blocked(snapshot);
  assert.ok(Object.isFrozen(handler));
  assert.ok(Object.isFrozen(PERMISSION_DENIAL_MESSAGES));
  assert.equal(shutdowns, 0);
});

test("explicit false and a site-access denied result are treated as denials", async () => {
  for (const result of [false, Object.freeze({ status: "denied" })]) {
    let shutdowns = 0;
    const handler = createPermissionDenialHandler(() => { shutdowns++; });
    const state = await handler.handle(result);
    assert.equal(state.status, "denied");
    assert.equal(state.message, PERMISSION_DENIAL_MESSAGES.denied);
    assert.deepEqual(handler.state(), state);
    assert.equal(shutdowns, 1);
    blocked(state);
  }
});

test("denied optional downloads access deactivates existing listeners once", async () => {
  const subscriptions = new Set(["created", "changed", "erased"]);
  let calls = 0;
  const handler = createPermissionDenialHandler(() => {
    calls++;
    subscriptions.clear();
  });
  const first = handler.handle(false);
  const second = handler.handle(false);
  assert.strictEqual(first, second);
  assert.equal((await first).status, "denied");
  assert.deepEqual([...subscriptions], []);
  assert.equal(calls, 1);
  assert.equal((await handler.handle(true)).status, "denied", "a later result cannot bypass denial");
});

test("unknown, absent and malformed results fail closed as unavailable", async () => {
  for (const result of [null, undefined, 0, "false", "true", {},
    { status: "unavailable" }, { status: "granted" },
    { status: "denied", authorizesOpen: true, scannerVerified: true },
    Promise.resolve(false), new Error("/private/document.pdf")]) {
    let calls = 0;
    const handler = createPermissionDenialHandler(() => { calls++; });
    const state = await handler.handle(result);
    blocked(state);
    assert.equal(calls, 1);
    if (result?.status === "denied") {
      assert.equal(state.status, "denied");
    } else {
      assert.equal(state.status, "unavailable");
    }
    assert.equal(JSON.stringify(state).includes("private"), false);
  }
});

test("an actual positive decision never authorizes or auto-enables the feature", async () => {
  let shutdowns = 0;
  const handler = createPermissionDenialHandler(() => { shutdowns++; });
  assert.equal((await handler.handle(true)).status, "unverified");
  assert.equal(shutdowns, 0);
  blocked(handler.state());
  assert.equal((await handler.handle(false)).status, "denied");
  assert.equal(shutdowns, 1);
});

test("untrusted accessors and hostile proxy traps cannot imply permission", async () => {
  let getterCalls = 0;
  const accessor = {};
  Object.defineProperty(accessor, "status", { get() { getterCalls++; throw Error("unsafe"); } });
  const proxy = new Proxy({}, { getOwnPropertyDescriptor() { throw Error("private"); } });
  for (const data of [accessor, proxy, Object.create({ status: "denied" })]) {
    const result = await createPermissionDenialHandler().handle(data);
    assert.equal(result.status, "unavailable");
    blocked(result);
  }
  assert.equal(getterCalls, 0);
});

test("reentrant denial while shutdown runs does not repeat cleanup", async () => {
  let shutdowns = 0;
  let handler;
  handler = createPermissionDenialHandler(() => {
    shutdowns++;
    handler.handle(false);
  });
  assert.equal((await handler.handle(false)).status, "denied");
  assert.equal(shutdowns, 1);
});

test("async cleanup is deduplicated and no retry or reprompt is performed", async () => {
  let release;
  let shutdowns = 0;
  const blockedCleanup = new Promise((resolve) => { release = resolve; });
  const handler = createPermissionDenialHandler(async () => {
    shutdowns++;
    await blockedCleanup;
  });
  const first = handler.handle(false);
  const second = handler.handle({ status: "denied" });
  assert.strictEqual(first, second);
  assert.equal(handler.state().status, "denied");
  assert.equal(shutdowns, 1, "shutdown starts synchronously");
  release();
  assert.equal((await first).status, "denied");
  assert.equal((await handler.handle(false)).status, "denied");
  assert.equal(shutdowns, 1);
});

test("cleanup failures report uncertainty without leaking exceptions", async () => {
  for (const cleanup of [
    () => { throw Error("/Users/private/secret.pdf"); },
    async () => { throw Error("/Users/private/secret.pdf"); }
  ]) {
    const handler = createPermissionDenialHandler(cleanup);
    const result = await handler.handle(false);
    assert.equal(result.status, "cleanup-failed");
    assert.equal(result.message, PERMISSION_DENIAL_MESSAGES.cleanupFailed);
    blocked(result);
    assert.equal(JSON.stringify(result).includes("secret"), false);
    assert.equal((await handler.handle(false)).status, "cleanup-failed");
  }
});

test("unavailable permission also calls shutdown and reports generic guidance", async () => {
  let calls = 0;
  const handler = createPermissionDenialHandler(() => { calls++; });
  const result = await handler.handle({ status: "unavailable" });
  assert.equal(result.status, "unavailable");
  assert.equal(result.message, PERMISSION_DENIAL_MESSAGES.unavailable);
  assert.equal(calls, 1);
  blocked(result);
});

test("invalid cleanup callbacks are rejected before any permission operations", () => {
  for (const option of [false, "stop", 1, {}, []]) {
    assert.throws(() => createPermissionDenialHandler(option), TypeError);
  }
});

test("denial handling has no import-time browser, storage, or scanner side effects", async () => {
  const source = await readFile(new URL("../src/permission-denials.js", import.meta.url), "utf8");
  const executable = source.replace(/\/\/[^\n]*/g, "");
  for (const forbidden of [
    "globalThis.", "browser.", "chrome.", "permissions.request(",
    "addListener(", "connectNative(", "sendNativeMessage(",
    "fetch(", "XMLHttpRequest", "window.open(", "localStorage",
    "sessionStorage", "node:fs", "scan-and-open", "clamscan"
  ]) assert.equal(executable.includes(forbidden), false, forbidden);
});
