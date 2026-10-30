import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createExtensionInitializer, INITIALIZATION_ERROR_CODES
} from "../src/initialization-errors.js";

const expected = (phase, errorCode = null) => ({
  phase, errorCode, scannerVerified: false, authorizesOpen: false
});

test("startup is dormant until explicitly requested", () => {
  let calls = 0;
  const controller = createExtensionInitializer([
    () => { calls++; return () => {}; }
  ]);
  assert.deepEqual(controller.state(), expected("idle"));
  assert.equal(calls, 0);
  assert.ok(Object.isFrozen(controller));
  assert.ok(Object.isFrozen(controller.state()));
});

test("missing integration steps fail closed with a fixed unavailable error", async () => {
  const controller = createExtensionInitializer();
  assert.deepEqual(await controller.start(),
    expected("failed", INITIALIZATION_ERROR_CODES.UNAVAILABLE));
  assert.deepEqual(await controller.start(),
    expected("failed", INITIALIZATION_ERROR_CODES.UNAVAILABLE));
  assert.deepEqual(await controller.stop(),
    expected("failed", INITIALIZATION_ERROR_CODES.UNAVAILABLE));
});

test("successful startup acquires resources in order and cleans up in reverse", async () => {
  const calls = [];
  const controller = createExtensionInitializer([
    async () => { calls.push("start-a"); return async () => { calls.push("stop-a"); }; },
    () => { calls.push("start-b"); return () => { calls.push("stop-b"); }; }
  ]);
  assert.deepEqual(await controller.start(), expected("initialized"));
  assert.deepEqual(calls, ["start-a", "start-b"]);
  assert.deepEqual(await controller.start(), expected("initialized"));
  assert.deepEqual(await controller.stop(), expected("stopped"));
  assert.deepEqual(await controller.stop(), expected("stopped"));
  assert.deepEqual(calls, ["start-a", "start-b", "stop-b", "stop-a"]);
  assert.deepEqual(await controller.start(), expected("stopped"));
});


test("shutdown marks initialized resources as stopping until asynchronous cleanup completes", async () => {
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const controller = createExtensionInitializer([() => async () => { await pending; }]);
  assert.deepEqual(await controller.start(), expected("initialized"));
  const finishing = controller.stop();
  assert.deepEqual(controller.state(), expected("stopping"));
  assert.deepEqual(await controller.start(), expected("stopping"));
  release();
  assert.deepEqual(await finishing, expected("stopped"));
  assert.deepEqual(await controller.start(), expected("stopped"));
});

test("startup failure rolls back acquired resources and hides sensitive errors", async () => {
  const calls = [];
  const controller = createExtensionInitializer([
    () => { calls.push("start-a"); return () => { calls.push("stop-a"); }; },
    () => { throw Error("Sensitive PDF path /Users/private.pdf"); },
    () => { calls.push("must-not-start"); return () => {}; }
  ]);
  const result = await controller.start();
  assert.deepEqual(result, expected("failed", INITIALIZATION_ERROR_CODES.STARTUP_FAILED));
  assert.deepEqual(calls, ["start-a", "stop-a"]);
  assert.equal(JSON.stringify(result).includes("private.pdf"), false);
  assert.deepEqual(await controller.start(), result);
});

test("missing cleanup return aborts initialization and undoes earlier steps", async () => {
  const calls = [];
  const controller = createExtensionInitializer([
    () => { calls.push("start-a"); return () => { calls.push("stop-a"); }; },
    () => { calls.push("start-b"); return undefined; }
  ]);
  assert.deepEqual(await controller.start(),
    expected("failed", INITIALIZATION_ERROR_CODES.STARTUP_FAILED));
  assert.deepEqual(calls, ["start-a", "start-b", "stop-a"]);
});

test("cleanup failure does not skip remaining rollback and is reported generically", async () => {
  const calls = [];
  const controller = createExtensionInitializer([
    () => { calls.push("start-a"); return () => { calls.push("stop-a"); }; },
    () => { calls.push("start-b"); return () => {
      calls.push("stop-b"); throw Error("/secret/cleanup-path");
    }; }
  ]);
  await controller.start();
  const result = await controller.stop();
  assert.deepEqual(result, expected("failed", INITIALIZATION_ERROR_CODES.CLEANUP_FAILED));
  assert.deepEqual(calls, ["start-a", "start-b", "stop-b", "stop-a"]);
  assert.equal(JSON.stringify(result).includes("secret"), false);
});

test("rollback failure takes precedence over the original startup error", async () => {
  const calls = [];
  const controller = createExtensionInitializer([
    () => () => { calls.push("rollback"); throw Error("cleanup failure"); },
    () => { throw Error("startup failure"); }
  ]);
  assert.deepEqual(await controller.start(),
    expected("failed", INITIALIZATION_ERROR_CODES.CLEANUP_FAILED));
  assert.deepEqual(calls, ["rollback"]);
});

test("concurrent starts share one initialization without duplicate listeners", async () => {
  let release;
  let starts = 0;
  const blocked = new Promise((resolve) => { release = resolve; });
  const controller = createExtensionInitializer([
    async () => { starts++; await blocked; return () => {}; }
  ]);
  const first = controller.start();
  const second = controller.start();
  assert.strictEqual(first, second);
  assert.deepEqual(controller.state(), expected("initializing"));
  release();
  assert.deepEqual(await first, expected("initialized"));
  assert.equal(starts, 1);
  await controller.stop();
});

test("stop during initialization undoes the current resource and skips later steps", async () => {
  const calls = [];
  let release;
  const blocked = new Promise((resolve) => { release = resolve; });
  const controller = createExtensionInitializer([
    async () => { calls.push("start-a"); await blocked; return () => { calls.push("stop-a"); }; },
    () => { calls.push("must-not-start"); return () => {}; }
  ]);
  const starting = controller.start();
  const stopping = controller.stop();
  release();
  assert.deepEqual(await starting, expected("stopped"));
  assert.deepEqual(await stopping, expected("stopped"));
  assert.deepEqual(calls, ["start-a", "stop-a"]);
});

test("stop before startup permanently prevents activation", async () => {
  let called = false;
  const controller = createExtensionInitializer([
    () => { called = true; return () => {}; }
  ]);
  assert.deepEqual(await controller.stop(), expected("stopped"));
  assert.deepEqual(await controller.start(), expected("stopped"));
  assert.equal(called, false);
});

test("invalid, sparse and getter-based initializers cannot run", () => {
  const getterArray = [];
  Object.defineProperty(getterArray, 0, { get() { throw Error("must not execute"); } });
  for (const value of [null, {}, "start", [1], Array(1), getterArray,
    Array.from({ length: 17 }, () => () => () => {})]) {
    assert.throws(() => createExtensionInitializer(value), TypeError);
  }
});

test("module does not activate downloads, native bridges, scanning or storage", async () => {
  const source = await readFile(new URL("../src/initialization-errors.js", import.meta.url), "utf8");
  const executable = source.replace(/\/\/[^\n]*/g, "");
  for (const forbidden of [
    "browser.", "chrome.", "addListener(", "sendNativeMessage(", "connectNative(",
    "fetch(", "XMLHttpRequest", "WebSocket", "window.open(", "localStorage",
    "sessionStorage", "node:fs", "scan-and-open", "clamscan"
  ]) {
    assert.equal(executable.includes(forbidden), false, forbidden);
  }
});
