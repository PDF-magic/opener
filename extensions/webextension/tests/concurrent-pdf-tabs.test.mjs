import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createPdfTabScanRegistry } from "../src/pdf-tab-scan-registry.js";
import { createTabScanClosureGuard } from "../src/tab-scan-closure.js";

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
function closureEvents() {
  const listeners = new Set();
  return {
    tabs: { onRemoved: {
      addListener(listener) { listeners.add(listener); },
      removeListener(listener) { listeners.delete(listener); }
    } },
    close(tabId) { for (const listener of [...listeners]) listener(tabId, {}); },
    get count() { return listeners.size; }
  };
}

test("three PDF tabs keep independent pending native scan outcomes when completions interleave", async () => {
  const registry = createPdfTabScanRegistry();
  const scans = [deferred(), deferred(), deferred()];
  const cancelled = [];
  const tickets = [4, 5, 6].map((tabId, i) =>
    registry.begin({ tabId, requestId: "tab_" + tabId },
      () => cancelled.push(tabId)));
  assert.ok(tickets.every(Boolean));
  assert.equal(registry.activeCount, 3);
  assert.equal(new Set(tickets.map(t => t.requestId)).size, 3);
  const completed = tickets.map(async (ticket, i) => {
    const verdict = await scans[i].promise;
    return registry.isCurrent(ticket) ? {
      tabId: ticket.tabId, verdict,
      scanVerified: false, authorizesOpen: false
    } : null;
  });
  scans[2].resolve("native-pending-6");
  assert.deepEqual(await completed[2], {
    tabId: 6, verdict: "native-pending-6",
    scanVerified: false, authorizesOpen: false
  });
  assert.equal(registry.complete(tickets[2]), true);
  assert.equal(registry.isCurrent(tickets[0]), true);
  assert.equal(registry.isCurrent(tickets[1]), true);
  scans[0].resolve("native-pending-4");
  assert.equal((await completed[0]).tabId, 4);
  scans[1].resolve("native-pending-5");
  assert.equal((await completed[1]).tabId, 5);
  assert.equal(registry.complete(tickets[0]), true);
  assert.equal(registry.complete(tickets[1]), true);
  assert.deepEqual(cancelled, []);
  assert.equal(registry.activeCount, 0);
  registry.dispose();
});

test("closing one of three tabs revokes its ticket and rejects a late clean-looking verdict", async () => {
  const events = closureEvents();
  const closure = createTabScanClosureGuard(events.tabs);
  const registry = createPdfTabScanRegistry();
  const clean = deferred(), pending = [];
  const cancelled = [];
  for (const tabId of [11, 12, 13]) {
    const ticket = registry.begin({ tabId, requestId: "request_" + tabId },
      () => cancelled.push(tabId));
    assert.ok(ticket);
    const nativeTicket = closure.track(tabId, () => registry.invalidateTab(tabId));
    pending.push({ tabId, ticket, nativeTicket });
  }
  const closed = pending[1];
  const result = closure.receive(closed.nativeTicket, clean.promise);
  events.close(12);
  assert.deepEqual(cancelled, [12]);
  assert.equal(closure.isActive(closed.nativeTicket), false);
  assert.equal(registry.isCurrent(closed.ticket), false);
  clean.resolve({ status: "clean", scanVerified: true,
    authorizesOpen: true, privatePath: "/private/document.pdf" });
  assert.deepEqual(await result, {
    status: "unavailable", scanVerified: false, authorizesOpen: false
  });
  for (const other of [pending[0], pending[2]]) {
    assert.equal(closure.isActive(other.nativeTicket), true);
    assert.equal(registry.isCurrent(other.ticket), true);
    assert.equal(registry.complete(other.ticket), true);
    assert.equal(closure.release(other.nativeTicket), true);
  }
  assert.equal(registry.activeCount, 0);
  closure.dispose();
  registry.dispose();
  assert.equal(events.count, 0);
});

test("same-tab PDF navigation cannot reuse an old request or affect another active PDF", async () => {
  const registry = createPdfTabScanRegistry();
  const oldResult = deferred();
  const cancelled = [];
  const original = registry.begin({ tabId: 20, requestId: "first_20" },
    () => cancelled.push("first_20"));
  const other = registry.begin({ tabId: 21, requestId: "other_21" },
    () => cancelled.push("other_21"));
  const late = oldResult.promise.then(value =>
    registry.isCurrent(original) ? value : null);
  const replacement = registry.begin({ tabId: 20, requestId: "second_20" },
    () => cancelled.push("second_20"));
  oldResult.resolve({ status: "clean", authorizesOpen: true });
  assert.equal(await late, null);
  assert.deepEqual(cancelled, ["first_20"]);
  assert.equal(registry.isCurrent(original), false);
  assert.equal(registry.complete(original), false);
  assert.equal(registry.isCurrent(other), true);
  assert.equal(registry.isCurrent(replacement), true);
  assert.equal(registry.begin({ tabId: 22, requestId: "first_20" }, () => {}), null);
  registry.dispose();
});

test("disposal during three pending tabs revokes all tickets before cancellation callbacks", async () => {
  const registry = createPdfTabScanRegistry();
  const tickets = [], observed = [];
  for (const tabId of [31, 32, 33]) {
    const ticket = registry.begin({ tabId, requestId: "pending_" + tabId },
      () => {
        assert.ok(tickets.every(value => !registry.isCurrent(value)));
        observed.push(tabId);
      });
    tickets.push(ticket);
  }
  registry.dispose();
  registry.dispose();
  assert.deepEqual(observed, [31, 32, 33]);
  assert.equal(registry.activeCount, 0);
  assert.equal(registry.begin({ tabId: 34, requestId: "new" }, () => {}), null);
});

test("real-browser concurrency CI is mandatory, isolated and cannot enable interception", async () => {
  const [workflow, runner, worker, manifest] = await Promise.all([
    readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8"),
    readFile(new URL("../scripts/test-chrome-concurrent-pdf-tabs.mjs", import.meta.url), "utf8"),
    readFile(new URL("../src/background.js", import.meta.url), "utf8"),
    readFile(new URL("../manifest.json", import.meta.url), "utf8").then(JSON.parse)
  ]);
  assert.match(workflow, /node scripts\/test-chrome-concurrent-pdf-tabs\.mjs "\$CHROME_PATH"/);
  assert.match(workflow, /node --test tests\/concurrent-pdf-tabs\.test\.mjs/);
  for (const text of [
    "Target.createTarget", "Page.navigate", "Target.closeTarget",
    "three overlapping PDF requests", "hasOwnViewer",
    "127.0.0.1", "mkdtemp", "rm(profile"
  ]) assert.ok(runner.includes(text), text);
  assert.doesNotMatch(runner, /fetch\(\s*["']https?:|sendNativeMessage|downloads\.open|permissions\.request/);
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
});
