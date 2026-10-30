import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createNativeReconnectController } from "../src/native-reconnection.js";

const consent = { registrationVerified: true, nativePermissionGranted: true, userApproved: true };
const approvedChromiumId = "abcdefghijklmnopabcdefghijklmnop";
const identity = () => ({
  browserKind: "chromium", browserRuntime: { id: approvedChromiumId },
  approvedExtensionIds: [approvedChromiumId]
});

function fakeScheduler() {
  const tasks = new Map();
  let next = 0;
  return {
    tasks,
    schedule(callback, ms) { const id = ++next; tasks.set(id, { callback, ms }); return id; },
    cancel(id) { tasks.delete(id); },
    runNext() {
      const [id, task] = tasks.entries().next().value ?? [];
      assert.ok(task, "a timer should exist");
      tasks.delete(id);
      task.callback();
      return task.ms;
    },
    pendingDelays() { return [...tasks.values()].map(({ ms }) => ms); }
  };
}

function fakePort() {
  const listeners = { message: [], disconnect: [] };
  const sent = [];
  let disconnected = false;
  return {
    sent,
    get disconnected() { return disconnected; },
    onMessage: { addListener(listener) { listeners.message.push(listener); } },
    onDisconnect: { addListener(listener) { listeners.disconnect.push(listener); } },
    postMessage(message) { sent.push(message); },
    disconnect() { disconnected = true; },
    emitMessage(message) { for (const callback of listeners.message) callback(message); },
    emitDisconnect() { for (const callback of listeners.disconnect) callback(); }
  };
}

function handshakeReply(port, overrides = {}) {
  const { requestId, payload } = port.sent[0];
  return {
    version: 1, kind: "response", topic: "host.handshake", requestId,
    payload: {
      status: "transport-only", protocolVersion: 1,
      clientNonce: payload.clientNonce, scanAvailable: false,
      applicationVersion: null, activeProtectionProfile: "built-in"
    }, ...overrides
  };
}

function rig(connectNative) {
  const scheduler = fakeScheduler();
  const states = [];
  let counter = 0;
  const ports = [];
  const controller = createNativeReconnectController({
    ...identity(),
    connectNative: connectNative ?? ((host) => {
      assert.equal(host, "org.pdfmagic.opener");
      const port = fakePort();
      ports.push(port);
      return port;
    }),
    nonceFactory: () => `Nonce_${String(++counter).padStart(20, "0")}`,
    schedule: scheduler.schedule, cancel: scheduler.cancel,
    onStateChange: (state) => states.push(state)
  });
  return { controller, scheduler, states, ports };
}

test("remains inert without all three independently verified opt-in conditions", () => {
  const { controller, ports, scheduler } = rig();
  for (const denied of [{}, { ...consent, registrationVerified: false },
    { ...consent, nativePermissionGranted: false },
    { ...consent, userApproved: false },
    { ...consent, userApproved: "true" }]) {
    assert.equal(controller.start(denied), false);
  }
  assert.equal(controller.state, "idle");
  assert.deepEqual(ports, []);
  assert.equal(scheduler.tasks.size, 0);
});

test("explicit start sends only a fresh bounded versioned handshake; ready is transport-only", () => {
  const { controller, ports, scheduler, states } = rig();
  assert.equal(controller.start(consent), true);
  assert.equal(controller.start(consent), false);
  assert.equal(ports.length, 1);
  assert.deepEqual(ports[0].sent[0], {
    version: 1, kind: "request", topic: "host.handshake",
    requestId: "hello_Nonce_00000000000000000001",
    payload: { clientNonce: "Nonce_00000000000000000001" }
  });
  ports[0].emitMessage(handshakeReply(ports[0]));
  assert.equal(controller.state, "ready");
  assert.equal(scheduler.tasks.size, 0);
  assert.deepEqual(states, ["connecting", "ready"]);
  assert.equal(ports[0].sent.length, 1, "no scan, opening, or replay message");
});

test("a lost host connection retries with a new process, nonce and handshake", () => {
  const { controller, ports, scheduler } = rig();
  controller.start(consent);
  ports[0].emitMessage(handshakeReply(ports[0]));
  ports[0].emitDisconnect();
  assert.equal(controller.state, "reconnecting");
  assert.deepEqual(scheduler.pendingDelays(), [250]);
  assert.equal(ports[0].disconnected, true);
  assert.equal(scheduler.runNext(), 250);
  assert.equal(controller.state, "connecting");
  assert.equal(ports.length, 2);
  assert.notEqual(ports[1].sent[0].requestId, ports[0].sent[0].requestId);
  ports[0].emitMessage(handshakeReply(ports[0]));
  ports[0].emitDisconnect();
  assert.equal(controller.state, "connecting", "stale process events cannot change new state");
  ports[1].emitMessage(handshakeReply(ports[1]));
  assert.equal(controller.state, "ready");
  assert.equal(scheduler.tasks.size, 0);
  assert.equal(ports[1].sent.length, 1);
});

test("failed handshakes retry at bounded backoff and then stop without looping", () => {
  const { controller, ports, scheduler } = rig();
  controller.start(consent);
  const delays = [];
  for (let i = 0; i < 3; i++) {
    ports[i].emitDisconnect();
    delays.push(scheduler.runNext());
  }
  ports[3].emitDisconnect();
  assert.deepEqual(delays, [250, 500, 1000]);
  assert.equal(controller.state, "unavailable");
  assert.equal(scheduler.tasks.size, 0);
  assert.equal(ports.length, 4);
  assert.equal(ports.every((port) => port.sent.length === 1), true);
});

test("connectNative throws are privacy-safe and exhaust the same retry budget", () => {
  const scheduler = fakeScheduler();
  let attempts = 0;
  const controller = createNativeReconnectController({
    ...identity(),
    connectNative() { attempts++; throw Error("/private/secret/native-host"); },
    nonceFactory: () => "Nonce_12345678901234567890",
    schedule: scheduler.schedule, cancel: scheduler.cancel
  });
  controller.start(consent);
  assert.equal(controller.state, "reconnecting");
  for (const delay of [250, 500, 1000]) assert.equal(scheduler.runNext(), delay);
  assert.equal(controller.state, "unavailable");
  assert.equal(attempts, 4);
  assert.equal(scheduler.tasks.size, 0);
});

test("handshake timeout triggers reconnect but never implicitly trusts a new process", () => {
  const { controller, ports, scheduler } = rig();
  controller.start(consent);
  assert.deepEqual(scheduler.pendingDelays(), [5000]);
  assert.equal(scheduler.runNext(), 5000);
  assert.equal(ports[0].disconnected, true);
  assert.equal(controller.state, "reconnecting");
  assert.equal(scheduler.runNext(), 250);
  assert.equal(controller.state, "connecting");
  assert.deepEqual(ports[1].sent.map((m) => m.topic), ["host.handshake"]);
  assert.equal(scheduler.tasks.size, 1);
});

test("bad, forged, privileged and stale handshake replies fail closed without retry", () => {
  for (const change of [
    (reply) => ({ ...reply, requestId: "old_session" }),
    (reply) => ({ ...reply, version: 2 }),
    (reply) => ({ ...reply, kind: "event" }),
    (reply) => ({ ...reply, topic: "scan.result" }),
    (reply) => ({ ...reply, payload: { ...reply.payload, scanAvailable: true } }),
    (reply) => ({ ...reply, payload: { ...reply.payload, scanVerified: true } }),
    (reply) => ({ ...reply, payload: { ...reply.payload, authorizesOpen: true } }),
    (reply) => ({ ...reply, payload: { ...reply.payload, clientNonce: "bad" } }),
    (reply) => ({ ...reply, payload: { ...reply.payload, protocolVersion: 2 } }),
    (reply) => ({ ...reply, payload: { ...reply.payload, activeProtectionProfile: "off" } }),
    (reply) => ({ ...reply, payload: { ...reply.payload, applicationVersion: "/private/file" } })
  ]) {
    const { controller, ports, scheduler } = rig();
    controller.start(consent);
    ports[0].emitMessage(change(handshakeReply(ports[0])));
    assert.equal(controller.state, "protocol-error");
    assert.equal(ports[0].disconnected, true);
    assert.equal(scheduler.tasks.size, 0);
    assert.equal(ports.length, 1);
  }
});

test("unsolicited messages after readiness cannot grant scans or trigger reconnection", () => {
  const { controller, ports, scheduler } = rig();
  controller.start(consent);
  ports[0].emitMessage(handshakeReply(ports[0]));
  ports[0].emitMessage({ kind: "response", topic: "scan.result", payload: { scanVerified: true } });
  assert.equal(controller.state, "protocol-error");
  assert.equal(scheduler.tasks.size, 0);
  assert.equal(ports[0].sent.length, 1);
});

test("explicit stop cancels pending reconnects and late old-port events", () => {
  const { controller, ports, scheduler } = rig();
  controller.start(consent);
  ports[0].emitDisconnect();
  assert.equal(scheduler.tasks.size, 1);
  controller.stop();
  assert.equal(controller.state, "stopped");
  assert.equal(scheduler.tasks.size, 0);
  ports[0].emitDisconnect();
  ports[0].emitMessage(handshakeReply(ports[0]));
  assert.equal(ports.length, 1);
  assert.equal(controller.start({ ...consent, userApproved: false }), false);
  assert.equal(controller.start(consent), true, "restart requires a fresh affirmative gate");
  assert.equal(ports.length, 2);
});

test("existing inactive background and user preferences remain untouched", async () => {
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.includes("native-reconnection"), false);
  const userPrefs = Object.freeze({ selectedPDFApplication: "chosen-viewer", scanBeforeOpen: true });
  const prior = JSON.stringify(userPrefs);
  const { controller } = rig();
  controller.start(consent);
  controller.stop();
  assert.equal(JSON.stringify(userPrefs), prior);
});

test("successful handshakes do not reset the retry budget during a crash loop", () => {
  const { controller, ports, scheduler } = rig();
  controller.start(consent);
  for (let i = 0; i < 3; i++) {
    ports[i].emitMessage(handshakeReply(ports[i]));
    ports[i].emitDisconnect();
    assert.equal(scheduler.runNext(), [250, 500, 1000][i]);
  }
  ports[3].emitMessage(handshakeReply(ports[3]));
  ports[3].emitDisconnect();
  assert.equal(controller.state, "unavailable");
  assert.equal(scheduler.tasks.size, 0);
  assert.equal(ports.length, 4);
});

test("user stop in a connecting-state callback prevents a late native connection", () => {
  let connections = 0;
  let controller;
  controller = createNativeReconnectController({
    ...identity(),
    connectNative() { connections++; return fakePort(); },
    onStateChange(state) { if (state === "connecting") controller.stop(); }
  });
  assert.equal(controller.start(consent), true);
  assert.equal(connections, 0);
  assert.equal(controller.state, "stopped");
});

test("invalid handshake challenges do not get sent or retried", () => {
  const { controller, ports, scheduler } = rig();
  const invalid = createNativeReconnectController({
    ...identity(),
    connectNative() { const port = fakePort(); ports.push(port); return port; },
    nonceFactory: () => "../../private.pdf",
    schedule: scheduler.schedule, cancel: scheduler.cancel
  });
  assert.equal(invalid.start(consent), true);
  assert.equal(invalid.state, "unavailable");
  assert.equal(ports[0].sent.length, 0);
  assert.equal(ports[0].disconnected, true);
  assert.equal(scheduler.tasks.size, 0);
  assert.equal(controller.state, "idle");
});
