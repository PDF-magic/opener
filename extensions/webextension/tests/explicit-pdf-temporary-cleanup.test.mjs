import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createExplicitPdfTemporaryCleanup } from "../src/explicit-pdf-temporary-cleanup.js";

const request = (patch = {}) => ({
  version: 1, requestId: "attempt_1", source: "pdf-link", tabId: 4,
  frameId: 2, selectionId: "selected_1", userInitiated: true, ...patch
});
const lease = (patch = {}) => ({
  requestId: "attempt_1", selectionId: "selected_1",
  downloadId: 12, leaseId: "lease_7",
  scope: "explicit-pdf-temporary", policy: "delete-after-use",
  state: "retired", appOwned: true, identityVerified: true,
  scanActive: false, openActive: false, quarantineHold: false,
  userOwned: false, verified: true, ...patch
});
const input = (patch = {}) => ({
  request: request(), downloadId: 12, leaseId: "lease_7", ...patch
});
const unavailable = {
  status: "unavailable", removed: false, scanVerified: false, authorizesOpen: false
};
const deferred = {
  status: "deferred", removed: false, scanVerified: false, authorizesOpen: false
};
const retained = {
  status: "retained", removed: false, scanVerified: false, authorizesOpen: false
};
const success = {
  status: "removed", removed: true, scanVerified: false, authorizesOpen: false
};
function fixture(initial = lease()) {
  const calls = [];
  const coordinator = {
    nativeTemporaryCleanupReady: true, selected: "selected_1",
    readCurrentSelectionId() { return this.selected; },
    readVerifiedTemporaryPdfLease(reference) {
      calls.push(["read", reference]); return initial;
    },
    async removeVerifiedTemporaryPdfLease(reference) {
      calls.push(["remove", reference]);
      return { leaseId: reference.leaseId, removed: true };
    },
    async verifyTemporaryPdfLeaseRemoved(reference) {
      calls.push(["confirm", reference]);
      return { leaseId: reference.leaseId, absent: true };
    }
  };
  return { coordinator, calls, guard: createExplicitPdfTemporaryCleanup(coordinator) };
}

test("deletes only a retired app-private lease after native removal and absence verification", async () => {
  const f = fixture();
  const output = await f.guard.cleanup(input());
  assert.deepEqual(output, success);
  assert.equal(Object.isFrozen(output), true);
  assert.deepEqual(f.calls.map(([kind]) => kind), ["read", "read", "remove", "confirm"]);
  for (const [, reference] of f.calls) {
    assert.deepEqual(reference, {
      requestId: "attempt_1", selectionId: "selected_1", downloadId: 12,
      leaseId: "lease_7"
    });
    assert.equal(Object.isFrozen(reference), true);
  }
  assert.deepEqual(await f.guard.cleanup(input()), unavailable);
  assert.equal(f.calls.filter(([kind]) => kind === "remove").length, 1);
});

test("retains user-selected browser downloads and previously existing PDFs", async () => {
  for (const scope of ["user-selected-download", "existing-local-pdf"]) {
    const f = fixture(lease({ scope, policy: "retain",
      appOwned: false, userOwned: true }));
    assert.deepEqual(await f.guard.cleanup(input()), retained);
    assert.deepEqual(f.calls.map(([kind]) => kind), ["read"]);
  }
});

test("retains private files when trusted retention policy applies", async () => {
  const f = fixture(lease({ policy: "retain" }));
  assert.deepEqual(await f.guard.cleanup(input()), retained);
  assert.deepEqual(f.calls.map(([kind]) => kind), ["read"]);
});

test("defers deletion while a scan, opening or quarantine claim is active", async () => {
  for (const patch of [
    { state: "active" }, { scanActive: true }, { openActive: true },
    { quarantineHold: true }
  ]) {
    const f = fixture(lease(patch));
    assert.deepEqual(await f.guard.cleanup(input()), deferred);
    assert.equal(f.calls.some(([kind]) => kind === "remove"), false);
  }
});

test("never deletes another user's file, an unowned lease, or uncertain ownership", async () => {
  for (const patch of [
    { appOwned: false }, { userOwned: true },
    { identityVerified: false }, { verified: false },
    { scope: "downloads-directory" }, { scope: "existing-local-pdf" },
    { scope: "user-selected-download", policy: "delete-after-use" },
    { policy: "delete-always" }, { state: "unknown" }
  ]) {
    const f = fixture(lease(patch));
    assert.deepEqual(await f.guard.cleanup(input()), unavailable);
    assert.equal(f.calls.some(([kind]) => kind === "remove"), false);
  }
});

test("rejects uncorrelated browser ID, selection, request or temporary lease", async () => {
  for (const patch of [
    { downloadId: 13 }, { leaseId: "other" }, { selectionId: "different" },
    { requestId: "different" }, { filePath: "/private/user.pdf" }
  ]) {
    const f = fixture(lease(patch));
    assert.deepEqual(await f.guard.cleanup(input()), unavailable);
    assert.deepEqual(f.calls.map(([kind]) => kind), ["read"]);
  }
});

test("rejects malformed, inherited, accessor-backed and hostile native records", async () => {
  const getter = lease();
  Object.defineProperty(getter, "state", {
    get() { throw Error("/private/secret.pdf"); }
  });
  for (const snapshot of [
    null, [], {}, Object.create(lease()), getter,
    new Proxy({}, { ownKeys() { throw Error("secret"); } }),
    { ...lease(), [Symbol("secret")]: true }
  ]) {
    const f = fixture(snapshot);
    assert.deepEqual(await f.guard.cleanup(input()), unavailable);
    assert.equal(f.calls.some(([kind]) => kind === "remove"), false);
  }
});

test("requires verified explicit user intent and matching current selection", async () => {
  const f = fixture();
  for (const bad of [
    { request: request({ userInitiated: false }) },
    { request: request({ source: "download" }) },
    { request: request({ url: "https://example.test/secret.pdf" }) },
    { downloadId: -1 }, { downloadId: "12" },
    { leaseId: "/private/file.pdf" }, { leaseId: "x".repeat(81) }
  ]) {
    assert.deepEqual(await f.guard.cleanup(input(bad)), unavailable);
  }
  assert.deepEqual(f.calls, []);
  f.coordinator.selected = "different";
  assert.deepEqual(await f.guard.cleanup(input()), unavailable);
  assert.deepEqual(f.calls, []);
});

test("missing coordinator, method, or readiness cannot remove a file", async () => {
  for (const changed of [
    { nativeTemporaryCleanupReady: false },
    { readVerifiedTemporaryPdfLease: null },
    { removeVerifiedTemporaryPdfLease: null },
    { verifyTemporaryPdfLeaseRemoved: null },
    { readCurrentSelectionId: null }
  ]) {
    const f = fixture();
    Object.assign(f.coordinator, changed);
    assert.deepEqual(await f.guard.cleanup(input()), unavailable);
    assert.equal(f.calls.some(([kind]) => kind === "remove"), false);
  }
  assert.deepEqual(await createExplicitPdfTemporaryCleanup().cleanup(input()), unavailable);
});

test("rechecks lease ownership and active scan/open claims before native deletion", async () => {
  for (const next of [
    lease({ scanActive: true }), lease({ quarantineHold: true }),
    lease({ appOwned: false }), lease({ leaseId: "other" }),
    lease({ policy: "retain" })
  ]) {
    const f = fixture();
    let reads = 0;
    f.coordinator.readVerifiedTemporaryPdfLease = reference => {
      f.calls.push(["read", reference]);
      return ++reads === 1 ? lease() : next;
    };
    const result = await f.guard.cleanup(input());
    assert.equal(result.removed, false);
    assert.equal(f.calls.some(([kind]) => kind === "remove"), false);
  }
});

test("does not retry uncertain removal acknowledgements or native failures", async () => {
  for (const answer of [
    null, { removed: false, leaseId: "lease_7" },
    { removed: true, leaseId: "other" },
    { removed: true, leaseId: "lease_7", path: "/secret" }
  ]) {
    const f = fixture();
    f.coordinator.removeVerifiedTemporaryPdfLease = async () => answer;
    assert.deepEqual(await f.guard.cleanup(input()), unavailable);
    assert.deepEqual(await f.guard.cleanup(input()), unavailable);
    assert.equal(f.calls.filter(([kind]) => kind === "read").length, 2);
  }
  const f = fixture();
  f.coordinator.removeVerifiedTemporaryPdfLease = async () => {
    throw Error("/private/secret.pdf");
  };
  assert.deepEqual(await f.guard.cleanup(input()), unavailable);
  assert.doesNotMatch(JSON.stringify(await f.guard.cleanup(input())), /private|secret/);
});

test("does not claim cleanup from an unverified or stale post-delete check", async () => {
  for (const answer of [
    null, false, { leaseId: "lease_7", absent: false },
    { leaseId: "other", absent: true },
    { leaseId: "lease_7", absent: true, url: "https://example.test/" }
  ]) {
    const f = fixture();
    f.coordinator.verifyTemporaryPdfLeaseRemoved = async () => answer;
    assert.deepEqual(await f.guard.cleanup(input()), unavailable);
    assert.equal(f.calls.filter(([kind]) => kind === "remove").length, 1);
  }
});

test("disposal and native session loss invalidate in-flight acknowledgements", async () => {
  const f = fixture();
  let finish;
  f.coordinator.removeVerifiedTemporaryPdfLease = () =>
    new Promise(resolve => { finish = resolve; });
  const pending = f.guard.cleanup(input());
  f.guard.dispose();
  finish({ leaseId: "lease_7", removed: true });
  assert.deepEqual(await pending, unavailable);
  assert.deepEqual(await f.guard.cleanup(input()), unavailable);
  const g = fixture();
  g.coordinator.removeVerifiedTemporaryPdfLease = async () => {
    g.coordinator.nativeTemporaryCleanupReady = false;
    return { leaseId: "lease_7", removed: true };
  };
  assert.deepEqual(await g.guard.cleanup(input()), unavailable);
});

test("import and invocation remain path-free, permission-free and cannot open PDF files", async () => {
  const source = await readFile(new URL("../src/explicit-pdf-temporary-cleanup.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  const ci = await readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(ci, /node --test tests\/explicit-pdf-temporary-cleanup\.test\.mjs/);
  for (const forbidden of [
    "innerHTML", "globalThis.", "chrome.", "browser.", "fetch(",
    "downloads.removeFile(", "downloads.erase(", "downloads.open(",
    "permissions.request(", "sendNativeMessage(", "connectNative(",
    "node:fs", "window.open(", "clamscan("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
