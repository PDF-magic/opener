import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  PDF_INTERCEPTION_RESTART_VERSION,
  createPdfInterceptionBrowserRestartGuard
} from "../src/pdf-interception-browser-restart.js";

const startup = (changes = {}) => ({
  version: 1, kind: "browser-startup", browserId: "firefox",
  startupId: "boot_A", ...changes
});
const reply = (browserId = "firefox", startupId = "boot_A") => ({
  kind: "native-orphaned-interceptions-cancelled", browserId,
  startupId, orphanedScansCancelled: true
});
function rig() {
  const events = [];
  const coordinator = {
    verifyColdBrowserStartup({ browserId, startupId }) {
      events.push("verify:" + startupId);
      return { kind: "verified-cold-browser-startup", browserId, startupId,
        verified: true };
    },
    revokeHeldPdfInterceptions({ startupId }) {
      events.push("revoke:" + startupId);
      return true;
    },
    cancelOrphanedPdfInterceptions({ browserId, startupId }) {
      events.push("cancel:" + startupId);
      return Promise.resolve(reply(browserId, startupId));
    }
  };
  const guard = createPdfInterceptionBrowserRestartGuard(coordinator);
  return { coordinator, events, guard };
}

test("starts blocked and requires actual cold-start reconciliation, not worker wake", () => {
  const { guard, events } = rig();
  assert.equal(PDF_INTERCEPTION_RESTART_VERSION, 1);
  assert.equal(guard.status, "startup-required");
  assert.equal(guard.issueTicket(), null);
  assert.equal(guard.isCurrent(Symbol()), false);
  assert.deepEqual(events, []);
  guard.dispose();
});

test("verified startup revokes old callbacks before native orphan cancellation", async () => {
  const { guard, events } = rig();
  const pending = guard.reconcileStartup(startup());
  assert.equal(guard.status, "reconciling");
  assert.equal(guard.issueTicket(), null);
  assert.deepEqual(events, ["verify:boot_A", "revoke:boot_A", "cancel:boot_A"]);
  const out = await pending;
  assert.deepEqual(out, {
    status: "orphan-cleanup-confirmed",
    oldSessionsInvalidated: true, nativeOrphansCancelled: true,
    scanVerified: false, automaticInterceptionEnabled: false,
    authorizesOpen: false
  });
  assert.ok(Object.isFrozen(out));
  assert.equal(guard.status, "reconciled");
  guard.dispose();
});

test("restart invalidates all old tickets before cancellation callbacks", async () => {
  const { guard, coordinator } = rig();
  await guard.reconcileStartup(startup());
  const a = guard.issueTicket();
  const b = guard.issueTicket();
  assert.equal(guard.isCurrent(a), true);
  assert.equal(guard.isCurrent(b), true);
  coordinator.revokeHeldPdfInterceptions = () => {
    assert.equal(guard.isCurrent(a), false);
    assert.equal(guard.isCurrent(b), false);
    assert.equal(guard.issueTicket(), null);
    return true;
  };
  assert.equal((await guard.reconcileStartup(startup({ startupId: "boot_B" }))).status,
    "orphan-cleanup-confirmed");
  assert.equal(guard.release(a), false);
  assert.equal(guard.isCurrent(b), false);
  const c = guard.issueTicket();
  assert.equal(guard.isCurrent(c), true);
  assert.notEqual(c, a);
  guard.dispose();
});

test("new guard cannot trust prior process ticket, even when the old guard was clean", async () => {
  const prior = rig(), next = rig();
  await prior.guard.reconcileStartup(startup());
  const ticket = prior.guard.issueTicket();
  assert.equal(next.guard.isCurrent(ticket), false);
  assert.equal(next.guard.issueTicket(), null);
  await next.guard.reconcileStartup(startup({ startupId: "boot_B" }));
  assert.equal(next.guard.isCurrent(ticket), false);
  next.guard.dispose();
  prior.guard.dispose();
});

test("native orphan reconciliation occurs with no in-memory scans after cold start", async () => {
  const { guard, events } = rig();
  await guard.reconcileStartup(startup());
  assert.deepEqual(events, ["verify:boot_A", "revoke:boot_A", "cancel:boot_A"]);
  guard.dispose();
});

test("duplicate startup notifications cannot replay cleanup or restore an old ticket", async () => {
  const { guard, events } = rig();
  await guard.reconcileStartup(startup());
  const ticket = guard.issueTicket();
  const count = events.length;
  const out = await guard.reconcileStartup(startup());
  assert.equal(out.status, "unavailable");
  assert.equal(events.length, count);
  assert.equal(guard.isCurrent(ticket), true);
  guard.dispose();
});

test("invalid and unrecognized startup payloads never call privileged coordinator", async () => {
  const invalid = [
    null, {}, [], startup({ kind: "service-worker-wake" }),
    startup({ kind: "tabs.onUpdated" }), startup({ version: 2 }),
    startup({ version: "1" }), startup({ browserId: "Firefox" }),
    startup({ browserId: "unsupported" }), startup({ startupId: "" }),
    startup({ startupId: "a".repeat(81) }),
    startup({ startupId: "../../secret" }), startup({ authorizesOpen: true }),
    startup({ url: "https://secret.invalid/a.pdf" }),
    Object.create(startup()),
    { ...startup(), get startupId() { throw Error("secret file"); } },
    new Proxy(startup(), { ownKeys() { throw Error("secret"); } })
  ];
  for (const value of invalid) {
    const { guard, events } = rig();
    const out = await guard.reconcileStartup(value);
    assert.equal(out.status, "unavailable");
    assert.deepEqual(events, []);
    assert.equal(guard.status, "startup-required");
    guard.dispose();
  }
});

test("forged, incomplete and asynchronous cold-start attestations fail closed", async () => {
  for (const verdict of [
    null, Promise.resolve({ verified: true }),
    { kind: "verified-cold-browser-startup", browserId: "firefox",
      startupId: "boot_A", verified: false },
    { kind: "verified-cold-browser-startup", browserId: "firefox",
      startupId: "boot_OLD", verified: true },
    { kind: "verified-cold-browser-startup", browserId: "chrome",
      startupId: "boot_A", verified: true },
    { kind: "verified-cold-browser-startup", browserId: "firefox",
      startupId: "boot_A", verified: true, scanVerified: true }
  ]) {
    const { guard, coordinator, events } = rig();
    coordinator.verifyColdBrowserStartup = () => verdict;
    assert.equal((await guard.reconcileStartup(startup())).status, "unavailable");
    assert.equal(events.length, 0);
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
});

test("missing trusted coordinator hooks and thrown verification never grant tickets", async () => {
  for (const name of [
    "verifyColdBrowserStartup", "revokeHeldPdfInterceptions",
    "cancelOrphanedPdfInterceptions"
  ]) {
    const { guard, coordinator, events } = rig();
    coordinator[name] = null;
    assert.equal((await guard.reconcileStartup(startup())).status, "unavailable");
    assert.equal(events.length, 0);
    guard.dispose();
  }
  const { guard, coordinator } = rig();
  coordinator.verifyColdBrowserStartup = () => { throw Error("/private/secret.pdf"); };
  assert.equal((await guard.reconcileStartup(startup())).status, "unavailable");
  guard.dispose();
});

test("failed synchronous revocation does not skip native orphan cancellation", async () => {
  for (const revoke of [() => false,
    async () => true,
    () => { throw Error("/private/secret.pdf"); }]) {
    const { guard, coordinator, events } = rig();
    coordinator.revokeHeldPdfInterceptions = revoke;
    const out = await guard.reconcileStartup(startup());
    assert.equal(out.status, "unavailable");
    assert.equal(out.oldSessionsInvalidated, true);
    assert.equal(guard.status, "unavailable");
    assert.equal(guard.issueTicket(), null);
    assert.deepEqual(events, ["verify:boot_A", "cancel:boot_A"]);
    guard.dispose();
  }
});

test("no native cleanup, wrong acknowledgement and rejected cleanup remain blocked", async () => {
  for (const cleanup of [
    () => null, () => ({ status: "accepted" }),
    () => Promise.resolve(reply("chrome", "boot_A")),
    () => Promise.resolve(reply("firefox", "boot_OLD")),
    () => Promise.resolve({ ...reply(), orphanedScansCancelled: "true" }),
    () => Promise.resolve({ ...reply(), authorizesOpen: true }),
    () => Promise.reject(Error("signed secret URL"))
  ]) {
    const { guard, coordinator } = rig();
    coordinator.cancelOrphanedPdfInterceptions = cleanup;
    const out = await guard.reconcileStartup(startup());
    assert.equal(out.status, "unavailable");
    assert.equal(out.nativeOrphansCancelled, false);
    assert.equal(guard.issueTicket(), null);
    guard.dispose();
  }
});

test("late native success after a newer restart cannot resurrect earlier generation", async () => {
  const { guard, coordinator } = rig();
  let resolveOld;
  coordinator.cancelOrphanedPdfInterceptions = ({ browserId, startupId }) =>
    startupId === "boot_A" ? new Promise(resolve => { resolveOld = resolve; }) :
      Promise.resolve(reply(browserId, startupId));
  const older = guard.reconcileStartup(startup());
  assert.equal(guard.status, "reconciling");
  const newer = await guard.reconcileStartup(startup({ startupId: "boot_B" }));
  assert.equal(newer.status, "orphan-cleanup-confirmed");
  const valid = guard.issueTicket();
  resolveOld(reply());
  assert.equal((await older).status, "unavailable");
  assert.equal(guard.isCurrent(valid), true);
  guard.dispose();
});

test("dispose while cleanup is pending revokes tickets and defeats late reply", async () => {
  const { guard, coordinator } = rig();
  let resolve;
  coordinator.cancelOrphanedPdfInterceptions = () =>
    new Promise(done => { resolve = done; });
  const pending = guard.reconcileStartup(startup());
  guard.dispose();
  resolve(reply());
  assert.equal((await pending).status, "unavailable");
  assert.equal(guard.status, "disposed");
  assert.equal(guard.issueTicket(), null);
  assert.equal((await guard.reconcileStartup(startup({ startupId: "boot_B" }))).status,
    "unavailable");
});

test("callback substitution during pending cleanup invalidates reconciliation", async () => {
  const { guard, coordinator } = rig();
  let resolve;
  coordinator.cancelOrphanedPdfInterceptions = () =>
    new Promise(done => { resolve = done; });
  const pending = guard.reconcileStartup(startup());
  coordinator.verifyColdBrowserStartup = () => null;
  resolve(reply());
  assert.equal((await pending).status, "unavailable");
  assert.equal(guard.issueTicket(), null);
  guard.dispose();
});

test("startup authentication cannot reenter and forge a second generation", async () => {
  const { guard, coordinator } = rig();
  let nested;
  coordinator.verifyColdBrowserStartup = ({ browserId, startupId }) => {
    nested = guard.reconcileStartup(startup({ startupId: "nested" }));
    return { kind: "verified-cold-browser-startup", browserId, startupId,
      verified: true };
  };
  const pending = guard.reconcileStartup(startup());
  assert.equal((await nested).status, "unavailable");
  assert.equal((await pending).status, "orphan-cleanup-confirmed");
  guard.dispose();
});

test("lifetime tickets are bounded and completed tickets cannot be replayed", async () => {
  const { guard } = rig();
  await guard.reconcileStartup(startup());
  const tickets = Array.from({ length: 128 }, () => guard.issueTicket());
  assert.equal(new Set(tickets).size, 128);
  assert.equal(guard.issueTicket(), null);
  assert.equal(guard.release(tickets[0]), true);
  assert.equal(guard.release(tickets[0]), false);
  assert.equal(guard.isCurrent(tickets[0]), false);
  assert.notEqual(guard.issueTicket(), null);
  guard.dispose();
});

test("every supported browser can scope native cleanup without assuming interception works", async () => {
  for (const browserId of [
    "brave", "chrome", "chromium", "edge", "vivaldi",
    "opera", "arc", "firefox", "safari"
  ]) {
    const { guard } = rig();
    const out = await guard.reconcileStartup(startup({ browserId }));
    assert.equal(out.status, "orphan-cleanup-confirmed", browserId);
    assert.equal(out.automaticInterceptionEnabled, false);
    assert.equal(out.authorizesOpen, false);
    guard.dispose();
  }
});

test("no startup repair is permission to resume a PDF, load a URL, scan or open", async () => {
  const { guard } = rig();
  const out = await guard.reconcileStartup(startup());
  assert.equal(out.scanVerified, false);
  assert.equal(out.authorizesOpen, false);
  assert.equal(out.automaticInterceptionEnabled, false);
  assert.equal(Object.keys(out).some(k => /url|path|bytes|pdf/i.test(k)), false);
  guard.dispose();
});

test("no browser APIs, startup listeners, persisted scan state or user preferences are changed", async () => {
  const [source, background, manifest, pkg, ci, doc] = await Promise.all([
    readFile(new URL("../src/pdf-interception-browser-restart.js", import.meta.url), "utf8"),
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8").then(JSON.parse),
    readFile(new URL("../package.json", import.meta.url), "utf8").then(JSON.parse),
    readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8"),
    readFile(new URL("../src/pdf-interception-browser-restart.md", import.meta.url), "utf8")
  ]);
  assert.match(background, /void 0;/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const forbidden of [
    "runtime.onStartup.addListener(", "addListener(", "connectNative(",
    "sendNativeMessage(", "downloads.open(", "downloads.download(",
    "permissions.request(", "fetch(", "window.open(", "node:fs",
    "localStorage", "sessionStorage", "chrome.", "browser."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  for (const phrase of ["opener-0793", "cold", "service worker",
    "native", "orphan", "quarantine", "restart", "fail closed",
    "not implemented", "user preferences"]) {
    assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
  }
  const prefs = Object.freeze({ pdfViewer: "selected-app", scanBeforeOpen: true });
  const snapshot = JSON.stringify(prefs);
  const { guard } = rig();
  await guard.reconcileStartup(startup());
  guard.dispose();
  assert.equal(JSON.stringify(prefs), snapshot);
});
