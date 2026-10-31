import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  EXTENSION_RESTART_PROTOCOL_VERSION,
  EXTENSION_RESTART_REASONS,
  createPdfInterceptionExtensionRestartGuard
} from "../src/pdf-interception-extension-restart.js";

const context = (patch = {}) => ({
  version: 1, kind: "extension-context-initialized",
  epochId: "epoch_A", reason: "worker-reinitialized", ...patch
});
const proof = (epochId = "epoch_A", reason = "worker-reinitialized") => ({
  kind: "verified-extension-context", epochId, reason, verified: true
});
const cleaned = (epochId = "epoch_A") => ({
  kind: "extension-native-orphans-cancelled", epochId,
  orphanedScansCancelled: true
});
function fixture() {
  const events = [];
  const coordinator = {
    verifyExtensionContextEpoch(c) {
      events.push("verify:" + c.epochId);
      return proof(c.epochId, c.reason);
    },
    quarantinePreviousExtensionHolds(c) {
      events.push("quarantine:" + c.epochId);
      return true;
    },
    cancelOrphanedExtensionScans(c) {
      events.push("cancel:" + c.epochId);
      return Promise.resolve(cleaned(c.epochId));
    }
  };
  return { coordinator, events, guard: createPdfInterceptionExtensionRestartGuard(coordinator) };
}
function assertSafe(value) {
  assert.equal(Object.isFrozen(value), true);
  assert.equal(value.scanVerified, false);
  assert.equal(value.automaticInterceptionEnabled, false);
  assert.equal(value.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(value), /epoch_A|https?:|private|token/i);
}

test("no stale tickets can exist until trusted cleanup completes", async () => {
  const { guard, events } = fixture();
  assert.equal(guard.status, "context-required");
  assert.equal(guard.issueTicket(), null);
  const result = await guard.reconcile(context());
  assert.equal(result.status, "orphan-cleanup-confirmed");
  assert.equal(result.oldContextInvalidated, true);
  assert.equal(result.nativeOrphansCancelled, true);
  assertSafe(result);
  assert.deepEqual(events, ["verify:epoch_A", "quarantine:epoch_A", "cancel:epoch_A"]);
  const ticket = guard.issueTicket();
  assert.equal(typeof ticket, "symbol");
  assert.equal(guard.isCurrent(ticket), true);
  assert.equal(guard.release(ticket), true);
  assert.equal(guard.isCurrent(ticket), false);
  guard.dispose();
});

test("reloading, updating, or replacing the service worker all invalidate old tickets", async () => {
  assert.equal(EXTENSION_RESTART_PROTOCOL_VERSION, 1);
  assert.deepEqual(EXTENSION_RESTART_REASONS,
    ["worker-reinitialized", "extension-reloaded", "extension-updated"]);
  for (const reason of EXTENSION_RESTART_REASONS) {
    const { guard, events } = fixture();
    await guard.reconcile(context());
    const old = guard.issueTicket();
    const newEpoch = guard.reconcile(context({ epochId: "epoch_B", reason }));
    assert.equal(guard.isCurrent(old), false);
    assert.equal(guard.issueTicket(), null);
    const result = await newEpoch;
    assert.equal(result.status, "orphan-cleanup-confirmed");
    assert.equal(guard.isCurrent(old), false);
    assert.notEqual(guard.issueTicket(), null);
    assert.deepEqual(events.slice(-3),
      ["verify:epoch_B", "quarantine:epoch_B", "cancel:epoch_B"]);
    guard.dispose();
  }
});

test("invalid or forged context cannot invoke cleanup or obtain tickets", async () => {
  const invalid = [
    null, undefined, {}, [], context({ kind: "browser-startup" }),
    context({ reason: "browser-restart" }), context({ reason: "onStartup" }),
    context({ epochId: "../secret" }), context({ epochId: "" }),
    context({ version: 2 }), context({ verified: true }),
    context({ url: "https://private.test" }), Object.create(context())
  ];
  for (const value of invalid) {
    const { guard, events } = fixture();
    assert.equal((await guard.reconcile(value)).status, "unavailable");
    assert.deepEqual(events, []);
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
  const getter = context();
  Object.defineProperty(getter, "epochId", { get() { throw Error("private path"); } });
  const { guard, events } = fixture();
  assert.equal((await guard.reconcile(getter)).status, "unavailable");
  assert.deepEqual(events, []);
  guard.dispose();
});

test("native scanner claims and asynchronous identity checks cannot verify restart", async () => {
  for (const value of [
    Promise.resolve(proof()), Promise.reject(Error("private path")),
    null, proof("epoch_OLD"),
    proof("epoch_A", "extension-updated"),
    { ...proof(), verified: false }, { ...proof(), authorizesOpen: true }
  ]) {
    const { guard, coordinator, events } = fixture();
    coordinator.verifyExtensionContextEpoch = () => value;
    const result = await guard.reconcile(context());
    assert.equal(result.status, "unavailable");
    assertSafe(result);
    assert.equal(guard.issueTicket(), null);
    assert.deepEqual(events, []);
    guard.dispose();
  }
});

test("missing coordinator hooks prevent any acceptance", async () => {
  for (const name of [
    "verifyExtensionContextEpoch", "quarantinePreviousExtensionHolds",
    "cancelOrphanedExtensionScans"
  ]) {
    const { guard, coordinator, events } = fixture();
    coordinator[name] = undefined;
    assert.equal((await guard.reconcile(context())).status, "unavailable");
    assert.equal(guard.issueTicket(), null);
    assert.deepEqual(events, []);
    guard.dispose();
  }
  const naked = createPdfInterceptionExtensionRestartGuard();
  assert.equal((await naked.reconcile(context())).status, "unavailable");
  assert.equal(naked.issueTicket(), null);
  naked.dispose();
});

test("failed synchronous quarantine still attempts orphan cancellation but stays blocked", async () => {
  for (const fn of [() => false, async () => true, () => {
    throw Error("private scanner failure");
  }]) {
    const { guard, coordinator, events } = fixture();
    coordinator.quarantinePreviousExtensionHolds = fn;
    const result = await guard.reconcile(context());
    assert.equal(result.status, "unavailable");
    assert.equal(result.oldContextInvalidated, true);
    assertSafe(result);
    assert.deepEqual(events, ["verify:epoch_A", "cancel:epoch_A"]);
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
});

test("native orphan cleanup failure and spoofed correlation block new sessions", async () => {
  for (const reply of [
    null, Promise.resolve({ kind: "accepted" }),
    Promise.resolve(cleaned("epoch_OLD")),
    Promise.resolve({ ...cleaned(), orphanedScansCancelled: false }),
    Promise.resolve({ ...cleaned(), scanVerified: true }),
    Promise.reject(Error("private URL"))
  ]) {
    const { guard, coordinator } = fixture();
    coordinator.cancelOrphanedExtensionScans = () => reply;
    const result = await guard.reconcile(context());
    assert.equal(result.status, "unavailable");
    assert.equal(result.nativeOrphansCancelled, false);
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
});

test("late cleanup from older worker cannot resurrect old tokens", async () => {
  const { guard, coordinator } = fixture();
  let resolveOld;
  coordinator.cancelOrphanedExtensionScans = c => c.epochId === "epoch_A"
    ? new Promise(resolve => { resolveOld = resolve; })
    : Promise.resolve(cleaned(c.epochId));
  const pendingOld = guard.reconcile(context());
  assert.equal(guard.issueTicket(), null);
  const newResult = await guard.reconcile(context({ epochId: "epoch_B" }));
  assert.equal(newResult.status, "orphan-cleanup-confirmed");
  const current = guard.issueTicket();
  resolveOld(cleaned());
  assert.equal((await pendingOld).status, "unavailable");
  assert.equal(guard.isCurrent(current), true);
  guard.dispose();
});

test("a malformed reinitialization attempt cannot resurrect or reuse an old epoch", async () => {
  const { guard, events } = fixture();
  await guard.reconcile(context());
  const ticket = guard.issueTicket();
  assert.equal((await guard.reconcile(context())).status, "unavailable");
  assert.equal(events.filter(x => x === "cancel:epoch_A").length, 1);
  assert.equal(guard.isCurrent(ticket), true);
  guard.dispose();
});

test("dispose while native cleanup pending prevents late success", async () => {
  const { guard, coordinator } = fixture();
  let resolve;
  coordinator.cancelOrphanedExtensionScans = () =>
    new Promise(done => { resolve = done; });
  const pending = guard.reconcile(context());
  guard.dispose();
  resolve(cleaned());
  assert.equal((await pending).status, "unavailable");
  assert.equal(guard.status, "disposed");
  assert.equal(guard.issueTicket(), null);
  assert.equal((await guard.reconcile(context({ epochId: "epoch_B" }))).status,
    "unavailable");
});

test("coordinator substitution invalidates pending and completed tickets", async () => {
  const { guard, coordinator } = fixture();
  await guard.reconcile(context());
  const ticket = guard.issueTicket();
  coordinator.cancelOrphanedExtensionScans = () => Promise.resolve(cleaned());
  assert.equal(guard.isCurrent(ticket), false);
  assert.equal(guard.issueTicket(), null);
  guard.dispose();
});

test("reentrant identity verification does not admit a nested restart", async () => {
  const { guard, coordinator } = fixture();
  let nested;
  coordinator.verifyExtensionContextEpoch = c => {
    nested = guard.reconcile(context({ epochId: "nested" }));
    return proof(c.epochId, c.reason);
  };
  const main = guard.reconcile(context());
  assert.equal((await nested).status, "unavailable");
  assert.equal((await main).status, "orphan-cleanup-confirmed");
  guard.dispose();
});

test("tickets and epochs are bounded, and restoring old PDFs remains forbidden", async () => {
  const { guard } = fixture();
  await guard.reconcile(context());
  const tickets = Array.from({ length: 128 }, () => guard.issueTicket());
  assert.equal(new Set(tickets).size, 128);
  assert.equal(guard.issueTicket(), null);
  assert.equal(guard.release(tickets[0]), true);
  assert.notEqual(guard.issueTicket(), null);
  guard.dispose();
});

test("background, manifests and test runner stay inert and discover the regression file", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [background, manifest, pkg, source] = await Promise.all([
    read("../src/background.js"), read("../manifest.json"),
    read("../package.json"), read("../src/pdf-interception-extension-restart.js")
  ]);
  assert.doesNotMatch(background, /reconcileExtension|cancelOrphanedExtensionScans/);
  const m = JSON.parse(manifest);
  assert.deepEqual(m.permissions, []);
  assert.deepEqual(m.host_permissions, []);
  assert.equal(JSON.parse(pkg).scripts.test,
    "node --test --test-concurrency=1 tests/*.test.mjs");
  assert.doesNotMatch(source, /\btabs\.update\s*\(|\bfetch\s*\(|\bwindow\.location\s*=/);
});

test("dispose invoked within verification is terminal, even with invalid proof", async () => {
  const { guard, coordinator } = fixture();
  coordinator.verifyExtensionContextEpoch = () => {
    guard.dispose();
    return null;
  };
  assert.equal((await guard.reconcile(context())).status, "unavailable");
  assert.equal(guard.status, "disposed");
  assert.equal((await guard.reconcile(context({ epochId: "epoch_B" }))).status,
    "unavailable");
  assert.equal(guard.issueTicket(), null);
});
