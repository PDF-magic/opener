import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  PDF_WORKER_SUSPENSION_VERSION, createPdfInterceptionWorkerSuspensionGuard
} from "../src/pdf-interception-worker-suspension.js";

const wake = (patch = {}) => ({
  version: 1, kind: "service-worker-activation",
  browserId: "firefox", activationId: "worker_A", ...patch
});
const receipt = (browserId = "firefox", activationId = "worker_A") => ({
  kind: "native-worker-orphans-cancelled", browserId, activationId,
  orphanedScansCancelled: true
});
function fixture() {
  const actions = [];
  const coordinator = {
    verifyWorkerActivation({ browserId, activationId }) {
      actions.push("verify:" + activationId);
      return { kind: "verified-service-worker-activation",
        browserId, activationId, verified: true };
    },
    revokePreviousWorkerHolds({ activationId }) {
      actions.push("revoke:" + activationId);
      return true;
    },
    cancelOrphanedWorkerScans({ browserId, activationId }) {
      actions.push("cancel:" + activationId);
      return Promise.resolve(receipt(browserId, activationId));
    }
  };
  const guard = createPdfInterceptionWorkerSuspensionGuard(coordinator);
  return { actions, coordinator, guard };
}
function assertNoApproval(value) {
  assert.equal(value.authorizesOpen, false);
  assert.equal(value.authorizesScan, false);
  assert.equal(value.scanVerified, false);
  assert.equal(value.automaticInterceptionEnabled, false);
  assert.ok(Object.isFrozen(value));
  assert.doesNotMatch(JSON.stringify(value), /secret|private|\.pdf|https?:|path|url/i);
}

test("starts unavailable and never issues a ticket before independently reconciled wake", () => {
  const { guard, actions } = fixture();
  assert.equal(PDF_WORKER_SUSPENSION_VERSION, 1);
  assert.equal(guard.status, "wake-required");
  assert.equal(guard.issueTicket(), null);
  assert.equal(guard.isCurrent(Symbol()), false);
  assert.deepEqual(actions, []);
  guard.dispose();
});

test("first real worker activation revokes old holds before native orphan cleanup", async () => {
  const { guard, actions } = fixture();
  const pending = guard.reconcileWake(wake());
  assert.equal(guard.status, "reconciling");
  assert.equal(guard.issueTicket(), null);
  assert.deepEqual(actions, ["verify:worker_A", "revoke:worker_A", "cancel:worker_A"]);
  const result = await pending;
  assert.deepEqual(result, {
    status: "orphan-cleanup-confirmed", workerReconciled: true,
    scanVerified: false, automaticInterceptionEnabled: false,
    authorizesScan: false, authorizesOpen: false
  });
  assertNoApproval(result);
  assert.equal(guard.status, "reconciled");
  guard.dispose();
});

test("onSuspend invalidates every token synchronously before cleanup callback", async () => {
  const { guard, coordinator, actions } = fixture();
  await guard.reconcileWake(wake());
  const old = guard.issueTicket();
  coordinator.revokePreviousWorkerHolds = ({ activationId }) => {
    assert.equal(activationId, "worker_A");
    assert.equal(guard.isCurrent(old), false);
    assert.equal(guard.issueTicket(), null);
    return true;
  };
  guard.suspend();
  assert.equal(guard.status, "suspended");
  assert.equal(guard.isCurrent(old), false);
  assert.equal(guard.release(old), false);
  assert.equal(guard.issueTicket(), null);
  assert.equal(actions.at(-1), "cancel:worker_A");
  guard.suspend();
  guard.dispose();
});

test("suspend cleanup rejection or throw never restores active tokens", async () => {
  for (const failing of [
    () => { throw Error("/private/sensitive.pdf"); },
    () => Promise.reject(Error("secret PDF")),
    () => Promise.resolve(true),
    () => false
  ]) {
    const { guard, coordinator } = fixture();
    await guard.reconcileWake(wake());
    const ticket = guard.issueTicket();
    coordinator.revokePreviousWorkerHolds = failing;
    coordinator.cancelOrphanedWorkerScans = failing;
    assert.doesNotThrow(() => guard.suspend());
    assert.equal(guard.isCurrent(ticket), false);
    assert.equal(guard.status, "suspended");
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
});

test("new worker process cannot import old in-memory tokens even without onSuspend", async () => {
  const old = fixture(), fresh = fixture();
  await old.guard.reconcileWake(wake());
  const ticket = old.guard.issueTicket();
  assert.equal(old.guard.isCurrent(ticket), true);
  assert.equal(fresh.guard.issueTicket(), null);
  assert.equal(fresh.guard.isCurrent(ticket), false);
  assert.equal((await fresh.guard.reconcileWake(wake({
    activationId: "worker_B"
  }))).status, "orphan-cleanup-confirmed");
  assert.equal(fresh.guard.isCurrent(ticket), false);
  assert.notEqual(fresh.guard.issueTicket(), ticket);
  fresh.guard.dispose();
  old.guard.dispose();
});

test("new activation after suspend must reconcile orphaned native jobs again", async () => {
  const { guard, actions } = fixture();
  await guard.reconcileWake(wake());
  const old = guard.issueTicket();
  guard.suspend();
  const resumed = guard.reconcileWake(wake({ activationId: "worker_B" }));
  assert.equal(guard.issueTicket(), null);
  assertNoApproval(await resumed);
  assert.equal(guard.isCurrent(old), false);
  assert.deepEqual(actions.slice(-3), [
    "verify:worker_B", "revoke:worker_B", "cancel:worker_B"
  ]);
  assert.equal(guard.status, "reconciled");
  guard.dispose();
});

test("late old worker cleanup cannot re-enable a suspended worker", async () => {
  const { guard, coordinator } = fixture();
  let finish;
  coordinator.cancelOrphanedWorkerScans = ({ browserId, activationId }) =>
    new Promise(resolve => { finish = () => resolve(receipt(browserId, activationId)); });
  const pending = guard.reconcileWake(wake());
  const finishOriginal = finish;
  guard.suspend();
  finishOriginal();
  assertNoApproval(await pending);
  assert.equal(guard.status, "suspended");
  assert.equal(guard.issueTicket(), null);
  guard.dispose();
});

test("later worker activation fences earlier in-flight cleanup acknowledgements", async () => {
  const { guard, coordinator } = fixture();
  let resolveOld;
  coordinator.cancelOrphanedWorkerScans = ({ browserId, activationId }) =>
    activationId === "worker_A" ?
      new Promise(resolve => { resolveOld = resolve; }) :
      Promise.resolve(receipt(browserId, activationId));
  const previous = guard.reconcileWake(wake());
  assert.equal((await guard.reconcileWake(wake({ activationId: "worker_B" }))).status,
    "orphan-cleanup-confirmed");
  const fresh = guard.issueTicket();
  resolveOld(receipt());
  assertNoApproval(await previous);
  assert.equal(guard.isCurrent(fresh), true);
  guard.dispose();
});

test("missing, failed or asynchronous synchronous revocation stays unavailable", async () => {
  for (const revoke of [() => false, async () => true,
    () => { throw Error("/private/secret.pdf"); }]) {
    const { guard, coordinator, actions } = fixture();
    coordinator.revokePreviousWorkerHolds = revoke;
    const result = await guard.reconcileWake(wake());
    assertNoApproval(result);
    assert.equal(result.status, "unavailable");
    assert.equal(guard.status, "unavailable");
    assert.equal(guard.issueTicket(), null);
    assert.deepEqual(actions, ["verify:worker_A", "cancel:worker_A"]);
    guard.dispose();
  }
});

test("missing and mismatched native orphan receipts never enable the worker", async () => {
  const bad = [
    () => undefined, () => receipt(),
    () => Promise.resolve({ status: "accepted" }),
    () => Promise.resolve(receipt("chrome", "worker_A")),
    () => Promise.resolve(receipt("firefox", "worker_B")),
    () => Promise.resolve({ ...receipt(), orphanedScansCancelled: "true" }),
    () => Promise.resolve({ ...receipt(), authorizesOpen: true }),
    () => Promise.reject(Error("private URL"))
  ];
  for (const cleanup of bad) {
    const { guard, coordinator } = fixture();
    coordinator.cancelOrphanedWorkerScans = cleanup;
    const out = await guard.reconcileWake(wake());
    assertNoApproval(out);
    assert.equal(out.status, "unavailable");
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
});

test("malformed, inherited, getter, replayed or browser-forged wake events fail closed", async () => {
  const malformed = [
    null, [], {}, wake({ version: 2 }), wake({ version: "1" }),
    wake({ kind: "browser-startup" }), wake({ kind: "onSuspend" }),
    wake({ browserId: "FireFox" }), wake({ browserId: "unknown" }),
    wake({ activationId: "" }), wake({ activationId: "../secret" }),
    wake({ activationId: "x".repeat(81) }),
    wake({ url: "https://private.test/document.pdf" }),
    wake({ authorizesOpen: true }), Object.create(wake()),
    { ...wake(), get activationId() { throw Error("secret"); } },
    new Proxy(wake(), { ownKeys() { throw Error("private"); } })
  ];
  for (const input of malformed) {
    const { guard, actions } = fixture();
    const result = await guard.reconcileWake(input);
    assertNoApproval(result);
    assert.deepEqual(actions, []);
    assert.equal(guard.status, "wake-required");
    guard.dispose();
  }
  const { guard, actions } = fixture();
  await guard.reconcileWake(wake());
  const count = actions.length, ticket = guard.issueTicket();
  assert.equal((await guard.reconcileWake(wake())).status, "unavailable");
  assert.equal(actions.length, count);
  assert.equal(guard.isCurrent(ticket), true);
  guard.dispose();
});

test("untrusted, asynchronous or re-entrant proof cannot establish worker lifetime", async () => {
  for (const verify of [
    () => Promise.resolve({ verified: true }),
    () => null,
    () => ({ kind: "verified-service-worker-activation",
      browserId: "chrome", activationId: "worker_A", verified: true }),
    () => ({ kind: "verified-service-worker-activation",
      browserId: "firefox", activationId: "worker_B", verified: true }),
    () => ({ kind: "verified-service-worker-activation",
      browserId: "firefox", activationId: "worker_A", verified: true,
      scanVerified: true }),
    () => { throw Error("secret URL"); }
  ]) {
    const { guard, coordinator } = fixture();
    coordinator.verifyWorkerActivation = verify;
    assert.equal((await guard.reconcileWake(wake())).status, "unavailable");
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
  const { guard, coordinator } = fixture();
  let inner;
  coordinator.verifyWorkerActivation = ({ browserId, activationId }) => {
    inner = guard.reconcileWake(wake({ activationId: "worker_B" }));
    return { kind: "verified-service-worker-activation",
      browserId, activationId, verified: true };
  };
  assert.equal((await guard.reconcileWake(wake())).status,
    "orphan-cleanup-confirmed");
  assert.equal((await inner).status, "unavailable");
  guard.dispose();
});

test("suspend or dispose during synchronous verification cannot re-enable worker", async () => {
  for (const action of ["suspend", "dispose"]) {
    const { guard, coordinator } = fixture();
    coordinator.verifyWorkerActivation = ({ browserId, activationId }) => {
      guard[action]();
      return { kind: "verified-service-worker-activation",
        browserId, activationId, verified: true };
    };
    assert.equal((await guard.reconcileWake(wake())).status, "unavailable");
    assert.equal(guard.issueTicket(), null);
    assert.equal(guard.status, action === "suspend" ? "suspended" : "disposed");
    guard.dispose();
  }
});

test("changed coordinator callback during native wait invalidates readiness", async () => {
  const { guard, coordinator } = fixture();
  let finish;
  coordinator.cancelOrphanedWorkerScans = () =>
    new Promise(resolve => { finish = resolve; });
  const pending = guard.reconcileWake(wake());
  coordinator.verifyWorkerActivation = () => null;
  finish(receipt());
  assert.equal((await pending).status, "unavailable");
  assert.equal(guard.issueTicket(), null);
  guard.dispose();
});

test("tickets are bounded and single-use, not proof of clean scan or opening", async () => {
  const { guard } = fixture();
  await guard.reconcileWake(wake());
  const tickets = Array.from({ length: 128 }, () => guard.issueTicket());
  assert.equal(new Set(tickets).size, 128);
  assert.equal(guard.issueTicket(), null);
  assert.equal(guard.release(tickets[0]), true);
  assert.equal(guard.release(tickets[0]), false);
  assert.equal(guard.isCurrent(tickets[0]), false);
  assert.notEqual(guard.issueTicket(), null);
  guard.dispose();
});

test("all registered browsers can reconcile without claiming actual interception", async () => {
  for (const browserId of ["brave", "chrome", "chromium", "edge",
    "vivaldi", "opera", "arc", "firefox", "safari"]) {
    const { guard } = fixture();
    const result = await guard.reconcileWake(wake({ browserId }));
    assert.equal(result.status, "orphan-cleanup-confirmed", browserId);
    assertNoApproval(result);
    guard.dispose();
  }
});

test("unavailable callbacks and disposal always fail closed", async () => {
  for (const name of ["verifyWorkerActivation", "revokePreviousWorkerHolds",
    "cancelOrphanedWorkerScans"]) {
    const { guard, coordinator } = fixture();
    coordinator[name] = null;
    assert.equal((await guard.reconcileWake(wake())).status, "unavailable");
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
  const { guard } = fixture();
  guard.dispose();
  assert.equal(guard.status, "disposed");
  assert.equal((await guard.reconcileWake(wake())).status, "unavailable");
  assert.equal(guard.issueTicket(), null);
  assert.doesNotThrow(() => guard.suspend());
});

test("no extension listeners, network, native calls, persistent state or user settings are changed", async () => {
  const [source, background, manifest, pkg, workflow, doc] = await Promise.all([
    readFile(new URL("../src/pdf-interception-worker-suspension.js", import.meta.url), "utf8"),
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8").then(JSON.parse),
    readFile(new URL("../package.json", import.meta.url), "utf8").then(JSON.parse),
    readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8"),
    readFile(new URL("../src/pdf-interception-worker-suspension.md", import.meta.url), "utf8")
  ]);
  assert.match(background, /void 0;/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(workflow, /node --test tests\/pdf-interception-worker-suspension\.test\.mjs/);
  const executable = source.replace(/\/\*[\s\S]*?\*\//gu, "").replace(/^\s*\/\/.*$/gmu, "");
  for (const forbidden of ["addListener(", "connectNative(", "sendNativeMessage(",
    "downloads.open(", "permissions.request(", "fetch(", "window.open(",
    "localStorage", "sessionStorage", "chrome.", "browser.", "node:fs"]) {
    assert.equal(executable.includes(forbidden), false, forbidden);
  }
  for (const phrase of ["opener-0795", "runtime.onSuspend", "native",
    "lease", "fail closed", "not implemented", "browser restart",
    "user preferences", "quarantine"]) {
    assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
  }
});
