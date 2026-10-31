import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createPdfTabScanRegistry, MAX_CONCURRENT_PDF_TAB_SCANS,
  MAX_PDF_TAB_REQUEST_IDS
} from "../src/pdf-tab-scan-registry.js";

const begin = (r, tabId, requestId, cancel = () => {}) =>
  r.begin({ tabId, requestId }, cancel);

test("simultaneous PDF tabs complete independently, including out of order", () => {
  const r = createPdfTabScanRegistry(), cancelled = [];
  const a = begin(r, 1, "a", () => cancelled.push(1));
  const b = begin(r, 2, "b", () => cancelled.push(2));
  const c = begin(r, 3, "c", () => cancelled.push(3));
  assert.equal(r.activeCount, 3);
  assert.equal(r.complete(b), true);
  assert.equal(r.complete(b), false);
  assert.equal(r.isCurrent(a), true);
  assert.equal(r.isCurrent(c), true);
  assert.equal(r.complete(c), true);
  assert.equal(r.complete(a), true);
  assert.equal(r.activeCount, 0);
  assert.deepEqual(cancelled, []);
});

test("same-tab navigation replacement cancels only the previous scan", () => {
  const r = createPdfTabScanRegistry(), calls = [];
  const old = begin(r, 4, "old", () => {
    assert.equal(r.isCurrent(old), false);
    calls.push("old");
  });
  const other = begin(r, 5, "other", () => calls.push("other"));
  const newer = begin(r, 4, "new", () => calls.push("new"));
  assert.deepEqual(calls, ["old"]);
  assert.equal(r.activeCount, 2);
  assert.equal(r.isCurrent(old), false);
  assert.equal(r.complete(old), false);
  assert.equal(r.isCurrent(newer), true);
  assert.equal(r.isCurrent(other), true);
  assert.equal(r.complete(other), true);
  assert.equal(r.complete(newer), true);
  assert.deepEqual(calls, ["old"]);
});

test("invalidating one tab does not invalidate another tab", () => {
  const r = createPdfTabScanRegistry(), cancelled = [];
  const a = begin(r, 0, "left", () => cancelled.push("left"));
  const b = begin(r, 1, "right", () => cancelled.push("right"));
  assert.equal(r.invalidateTab(0), true);
  assert.equal(r.invalidateTab(0), false);
  assert.equal(r.complete(a), false);
  assert.equal(r.isCurrent(b), true);
  assert.equal(r.complete(b), true);
  assert.deepEqual(cancelled, ["left"]);
});

test("duplicate IDs, stale tickets, copied tickets and foreign registry tickets fail closed", () => {
  const r = createPdfTabScanRegistry();
  const a = begin(r, 8, "unique");
  assert.equal(begin(r, 9, "unique"), null);
  assert.equal(begin(r, 8, "unique"), null);
  assert.equal(r.complete(a), true);
  assert.equal(begin(r, 8, "unique"), null);
  const b = begin(r, 8, "new_id");
  assert.equal(r.isCurrent(a), false);
  assert.equal(r.isCurrent({ ...b }), false);
  assert.equal(r.complete({ ...b }), false);
  assert.equal(r.isCurrent(null), false);
  assert.equal(r.isCurrent("new_id"), false);
  assert.equal(createPdfTabScanRegistry().isCurrent(b), false);
  assert.equal(r.isCurrent(b), true);
});

test("tab capacity never evicts another tab; same-tab replacement is allowed", () => {
  const r = createPdfTabScanRegistry();
  assert.equal(MAX_CONCURRENT_PDF_TAB_SCANS, 64);
  const tickets = Array.from({ length: 64 }, (_, id) => begin(r, id, "scan_" + id));
  assert.ok(tickets.every(Boolean));
  assert.equal(begin(r, 100, "overflow"), null);
  assert.equal(r.activeCount, 64);
  const replacement = begin(r, 0, "replacement");
  assert.ok(replacement);
  assert.equal(r.isCurrent(tickets[0]), false);
  assert.equal(r.isCurrent(tickets[1]), true);
  assert.equal(r.activeCount, 64);
  assert.equal(r.invalidateTab(2), true);
  assert.ok(begin(r, 100, "after_release"));
  r.dispose();
});

test("request ID history is bounded and reused identifiers are never accepted", () => {
  const r = createPdfTabScanRegistry();
  assert.equal(MAX_PDF_TAB_REQUEST_IDS, 4096);
  for (let i = 0; i < MAX_PDF_TAB_REQUEST_IDS; i++) {
    const ticket = begin(r, 0, "id_" + i);
    assert.ok(ticket);
    assert.equal(r.complete(ticket), true);
  }
  assert.equal(begin(r, 0, "over_limit"), null);
  assert.equal(begin(r, 0, "id_0"), null);
  assert.equal(r.activeCount, 0);
});

test("invalid or page-controlled identity never creates a session", () => {
  const r = createPdfTabScanRegistry();
  let reads = 0;
  const getter = { tabId: 1 };
  Object.defineProperty(getter, "requestId", { get() { reads++; return "foo"; } });
  const symbol = { tabId: 1, requestId: "foo" };
  symbol[Symbol("secret")] = true;
  for (const bad of [
    undefined, null, [], {}, { tabId: -1, requestId: "foo" },
    { tabId: 1.5, requestId: "foo" },
    { tabId: Number.MAX_SAFE_INTEGER + 1, requestId: "foo" },
    { tabId: "1", requestId: "foo" }, { tabId: 1, requestId: "" },
    { tabId: 1, requestId: "../file.pdf" },
    { tabId: 1, requestId: "invalid id" },
    { tabId: 1, requestId: "x".repeat(81) },
    { tabId: 1, requestId: 42 },
    { tabId: 1, requestId: "foo", url: "https://secret.test/a.pdf" },
    Object.create({ tabId: 1, requestId: "foo" }),
    getter, symbol, new Proxy({ tabId: 1, requestId: "foo" }, {
      ownKeys() { throw Error("secret data"); }
    })
  ]) assert.equal(r.begin(bad, () => {}), null);
  assert.equal(r.begin({ tabId: 1, requestId: "foo" }, null), null);
  assert.equal(reads, 0);
  assert.equal(r.activeCount, 0);
  assert.ok(r.begin(Object.assign(Object.create(null), {
    tabId: 1, requestId: "safe"
  }), () => {}));
});

test("failed and async-rejected cancellation cannot interfere with other tabs", async () => {
  const r = createPdfTabScanRegistry();
  begin(r, 1, "throw", () => { throw Error("private path"); });
  begin(r, 2, "reject", () => Promise.reject(Error("scanner secret")));
  const keep = begin(r, 3, "keep");
  assert.equal(r.invalidateTab(1), true);
  assert.equal(r.invalidateTab(2), true);
  await Promise.resolve();
  assert.equal(r.isCurrent(keep), true);
  assert.equal(r.complete(keep), true);
});

test("reentrant cancellation cannot restore an old ticket", () => {
  const r = createPdfTabScanRegistry();
  let latest;
  const old = begin(r, 1, "old", () => {
    latest = begin(r, 1, "reentrant");
  });
  const middle = begin(r, 1, "middle");
  assert.equal(r.isCurrent(old), false);
  assert.equal(r.isCurrent(middle), false);
  assert.equal(r.isCurrent(latest), true);
  assert.equal(r.activeCount, 1);
});

test("disposal invalidates all outstanding tabs before callbacks execute", () => {
  const r = createPdfTabScanRegistry(), calls = [], tickets = [];
  for (const id of [1, 2, 3]) {
    tickets.push(begin(r, id, "scan_" + id, () => {
      assert.equal(r.activeCount, 0);
      assert.ok(tickets.every(t => !r.isCurrent(t)));
      assert.equal(begin(r, 9, "resurrect"), null);
      calls.push(id);
    }));
  }
  r.dispose();
  r.dispose();
  assert.deepEqual(calls, [1, 2, 3]);
  assert.equal(r.complete(tickets[0]), false);
  assert.equal(r.invalidateTab(2), false);
});

test("tickets never authorize scanning/opening and the background stays inert", async () => {
  const r = createPdfTabScanRegistry(), ticket = begin(r, 11, "opaque");
  assert.ok(Object.isFrozen(r));
  assert.ok(Object.isFrozen(ticket));
  assert.equal(ticket.scanVerified, false);
  assert.equal(ticket.authorizesScan, false);
  assert.equal(ticket.authorizesOpen, false);
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, worker, manifest, safari, pkg, ci, docs] = await Promise.all([
    read("../src/pdf-tab-scan-registry.js"), read("../src/background.js"),
    read("../manifest.json").then(JSON.parse),
    read("../../safari/manifest.json").then(JSON.parse),
    read("../package.json").then(JSON.parse),
    read("../../../.github/workflows/ci.yml"),
    read("../src/pdf-tab-scan-registry.md")
  ]);
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  assert.match(docs, /opener-0792/);
  for (const forbidden of [
    "chrome.", "browser.", "addListener(", "connectNative(",
    "sendNativeMessage(", "downloads.open(", "fetch(", "node:fs",
    "storage.local", "permissions.request(", "clamscan"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
