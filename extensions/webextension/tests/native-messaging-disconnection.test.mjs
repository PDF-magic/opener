import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createNativeReconnectController } from "../src/native-reconnection.js";
import { createNativeScanDisconnectGuard } from "../src/native-scan-disconnect.js";

// Browser-compatible Port events, with no host registration or native permission.
const extensionId = "abcdefghijklmnopabcdefghijklmnop";
const consent = {
  registrationVerified: true, nativePermissionGranted: true, userApproved: true
};

function clock() {
  const tasks = new Map();
  let nextId = 0;
  return {
    tasks,
    schedule(callback, ms) {
      const id = ++nextId;
      tasks.set(id, { callback, ms });
      return id;
    },
    cancel(id) { tasks.delete(id); },
    advance() {
      const [id, task] = tasks.entries().next().value ?? [];
      assert.ok(task, "expected a scheduled native retry");
      tasks.delete(id);
      task.callback();
      return task.ms;
    },
    delays() { return [...tasks.values()].map(({ ms }) => ms); }
  };
}

function nativePort() {
  const messageListeners = new Set();
  const disconnectListeners = new Set();
  const sent = [];
  let closeCalls = 0;
  return {
    sent,
    get closeCalls() { return closeCalls; },
    onMessage: { addListener(fn) { messageListeners.add(fn); } },
    onDisconnect: {
      addListener(fn) { disconnectListeners.add(fn); },
      removeListener(fn) { disconnectListeners.delete(fn); }
    },
    postMessage(message) { sent.push(message); },
    disconnect() { closeCalls++; },
    emitMessage(message) {
      for (const listener of [...messageListeners]) listener(message);
    },
    // Models host termination or a browser-side native Port disconnection.
    emitDisconnect() {
      for (const listener of [...disconnectListeners]) listener(this);
    }
  };
}

function handshakeReply(port) {
  const request = port.sent[0];
  assert.equal(request.topic, "host.handshake");
  return {
    version: 1, kind: "response", topic: "host.handshake",
    requestId: request.requestId,
    payload: {
      status: "transport-only", protocolVersion: 1,
      clientNonce: request.payload.clientNonce, scanAvailable: false,
      applicationVersion: null, activeProtectionProfile: "built-in"
    }
  };
}

function session() {
  const scheduler = clock();
  const ports = [];
  let nonce = 0;
  const controller = createNativeReconnectController({
    browserKind: "chromium", browserRuntime: { id: extensionId },
    approvedExtensionIds: [extensionId],
    connectNative(host) {
      assert.equal(host, "org.pdfmagic.opener");
      const port = nativePort();
      ports.push(port);
      return port;
    },
    nonceFactory: () => "nonce_" + String(++nonce).padStart(20, "0"),
    schedule: scheduler.schedule, cancel: scheduler.cancel
  });
  return { controller, ports, scheduler };
}

test("native host loss cancels tracked work before a new session can become ready", () => {
  const { controller, ports, scheduler } = session();
  assert.equal(controller.start(consent), true);
  const oldPort = ports[0];
  oldPort.emitMessage(handshakeReply(oldPort));
  assert.equal(controller.state, "ready");

  const guard = createNativeScanDisconnectGuard(oldPort);
  const cancelled = [];
  const oldToken = guard.track(() => {
    assert.equal(guard.connectionLost(), true);
    assert.equal(guard.isActive(oldToken), false);
    cancelled.push("old-scan");
  });
  oldPort.emitDisconnect();
  assert.deepEqual(cancelled, ["old-scan"]);
  assert.equal(guard.isActive(oldToken), false);
  assert.equal(guard.release(oldToken), false);
  assert.throws(() => guard.track(() => {}), /unavailable/);
  assert.equal(controller.state, "reconnecting");
  assert.deepEqual(scheduler.delays(), [250]);
  assert.equal(oldPort.closeCalls, 1);
  assert.deepEqual(oldPort.sent.map(({ topic }) => topic), ["host.handshake"]);

  assert.equal(scheduler.advance(), 250);
  const freshPort = ports[1];
  assert.notEqual(freshPort.sent[0].requestId, oldPort.sent[0].requestId);
  assert.equal(controller.state, "connecting");
  oldPort.emitMessage(handshakeReply(oldPort));
  oldPort.emitDisconnect();
  assert.equal(controller.state, "connecting", "old host callbacks cannot revive a session");
  freshPort.emitMessage(handshakeReply(freshPort));
  assert.equal(controller.state, "ready");
  assert.deepEqual(cancelled, ["old-scan"], "reconnection cannot replay old work");
  assert.deepEqual(freshPort.sent.map(({ topic }) => topic), ["host.handshake"]);

  const freshGuard = createNativeScanDisconnectGuard(freshPort);
  assert.equal(freshGuard.isActive(oldToken), false);
  const freshToken = freshGuard.track(() => {});
  assert.equal(freshGuard.isActive(freshToken), true);
  freshGuard.dispose();
  controller.stop();
  guard.dispose();
  assert.equal(scheduler.tasks.size, 0);
});

test("native disconnect before handshake and browser shutdown cannot leave retry work", async () => {
  const { controller, ports, scheduler } = session();
  assert.equal(controller.start(consent), true);
  const port = ports[0];
  assert.deepEqual(scheduler.delays(), [5000]);
  port.emitDisconnect();
  assert.equal(controller.state, "reconnecting");
  assert.deepEqual(scheduler.delays(), [250]);
  controller.stop();
  assert.equal(controller.state, "stopped");
  assert.equal(scheduler.tasks.size, 0);
  port.emitMessage(handshakeReply(port));
  port.emitDisconnect();
  assert.equal(controller.state, "stopped");
  assert.equal(ports.length, 1);
  assert.deepEqual(port.sent.map(({ topic }) => topic), ["host.handshake"]);

  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.equal(background.includes("native-reconnection"), false);
  assert.equal(background.includes("native-scan-disconnect"), false);
  assert.equal(manifest.permissions.includes("nativeMessaging"), false);
  assert.equal(manifest.optional_permissions.includes("nativeMessaging"), false);
});
