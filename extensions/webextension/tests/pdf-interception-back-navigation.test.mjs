import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createPdfInterceptionBackNavigationGuard
} from "../src/pdf-interception-back-navigation.js";

const event = (patch = {}) => ({
  tabId: 7, frameId: 0, leavingEntryId: "holding_19",
  direction: "back", verified: true, ...patch
});
function fixture(cancelPendingScan = () => {}) {
  let cancellations = 0;
  const guard = createPdfInterceptionBackNavigationGuard({
    tabId: 7, holdingEntryId: "holding_19",
    cancelPendingScan() { cancellations++; return cancelPendingScan(); }
  });
  return { guard, cancellations: () => cancellations };
}
function safe(value) {
  assert.equal(Object.isFrozen(value), true);
  assert.equal(value.historyMutationRequested, false);
  assert.equal(value.navigationRequested, false);
  assert.equal(value.autoResumeOnForward, false);
  assert.equal(value.cancelConfirmed, false);
  assert.equal(value.authorizesScan, false);
  assert.equal(value.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(value), /holding_19|example\.test|secret|token/);
}

test("Back leaves the holding entry without overriding browser history", () => {
  const f = fixture();
  assert.equal(f.guard.isCurrentHoldingEntry(), true);
  assert.equal(Object.isFrozen(f.guard), true);
  const outcome = f.guard.onHistoryNavigation(event());
  assert.equal(outcome.status, "back-navigation");
  assert.equal(outcome.cancelRequested, true);
  assert.equal(outcome.holdingActive, false);
  assert.equal(outcome.skipHoldingRedirect, true);
  assert.equal(f.cancellations(), 1);
  assert.equal(f.guard.isCurrentHoldingEntry(), false);
  safe(outcome);
});

test("stale scan completion, duplicate Back and Forward return cannot resume", () => {
  const f = fixture();
  f.guard.onHistoryNavigation(event());
  for (const later of [
    f.guard.onHistoryNavigation(event()),
    f.guard.onHistoryNavigation(event({ direction: "forward" })),
    f.guard.onPageRestore(), f.guard.onPageExit(), f.guard.dispose()
  ]) {
    assert.equal(later.holdingActive, false);
    assert.equal(later.skipHoldingRedirect, true);
    safe(later);
  }
  assert.equal(f.guard.onPageRestore().status, "stale-holding-entry");
  assert.equal(f.cancellations(), 1);
});

test("Back is scoped to the verified top-level holding entry", () => {
  const invalid = [
    event({ tabId: 8 }), event({ frameId: 1 }),
    event({ leavingEntryId: "other" }), event({ verified: false }),
    event({ verified: "true" }), event({ direction: "reload" }),
    event({ direction: "forward_back" }), event({ direction: "BACK" }),
    event({ url: "https://example.test/secret.pdf" }),
    { ...event(), authorizesOpen: true },
    null, {}, [], Object.create(event())
  ];
  const accessor = event();
  Object.defineProperty(accessor, "direction", { get() { throw Error("secret"); } });
  invalid.push(accessor, new Proxy(event(), { ownKeys() { throw Error("secret"); } }));
  const f = fixture();
  for (const value of invalid) {
    const outcome = f.guard.onHistoryNavigation(value);
    assert.equal(outcome.status, "unverified-history-event");
    assert.equal(outcome.holdingActive, true);
    safe(outcome);
  }
  assert.equal(f.cancellations(), 0);
  assert.equal(f.guard.onHistoryNavigation(event()).status, "back-navigation");
});

test("Forward leaving a current holding page also invalidates rather than replaying", () => {
  const f = fixture();
  const result = f.guard.onHistoryNavigation(event({ direction: "forward" }));
  assert.equal(result.status, "forward-navigation");
  assert.equal(result.skipHoldingRedirect, true);
  assert.equal(f.guard.onPageRestore().status, "stale-holding-entry");
  assert.equal(f.cancellations(), 1);
  safe(result);
});

test("page-exit fallback handles Back when the browser cannot identify direction", () => {
  const f = fixture();
  const outcome = f.guard.onPageExit();
  assert.equal(outcome.status, "page-exit");
  assert.equal(outcome.cancelRequested, true);
  assert.equal(f.guard.isCurrentHoldingEntry(), false);
  assert.equal(f.guard.onHistoryNavigation(event()).status, "already-left");
  assert.equal(f.cancellations(), 1);
  safe(outcome);
});

test("cancel exceptions and reentrant history callbacks fail closed exactly once", () => {
  let f;
  f = fixture(() => {
    assert.equal(f.guard.isCurrentHoldingEntry(), false);
    assert.equal(f.guard.onPageExit().status, "already-left");
    throw Error("secret URL");
  });
  const result = f.guard.onHistoryNavigation(event());
  assert.equal(result.status, "back-navigation");
  assert.equal(f.cancellations(), 1);
  safe(result);
});

test("async cancellation rejection cannot revive a stale scan", async () => {
  const f = fixture(() => Promise.reject(Error("secret URL")));
  f.guard.onHistoryNavigation(event());
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(f.guard.isCurrentHoldingEntry(), false);
  assert.equal(f.cancellations(), 1);
});

test("disposal cancels once and no later session event can rearm", () => {
  const f = fixture();
  assert.equal(f.guard.dispose().status, "disposed");
  assert.equal(f.guard.onHistoryNavigation(event()).status, "already-left");
  assert.equal(f.guard.dispose().status, "already-left");
  assert.equal(f.cancellations(), 1);
});

test("rejects forged or unsafe holding-session options", () => {
  const good = { tabId: 7, holdingEntryId: "holding_19", cancelPendingScan() {} };
  for (const invalid of [
    null, undefined, {}, { ...good, tabId: -1 },
    { ...good, tabId: 1.3 }, { ...good, tabId: "7" },
    { ...good, holdingEntryId: "../secret" },
    { ...good, holdingEntryId: "x".repeat(81) },
    { ...good, cancelPendingScan: null },
    { ...good, url: "https://example.test" }, Object.create(good)
  ]) assert.throws(() => createPdfInterceptionBackNavigationGuard(invalid), TypeError);
  const accessor = { ...good };
  Object.defineProperty(accessor, "tabId", { get() { throw Error("secret"); } });
  assert.throws(() => createPdfInterceptionBackNavigationGuard(accessor), TypeError);
});

test("separate holding entries never share navigation or cancellation state", () => {
  const first = fixture();
  const second = fixture();
  first.guard.onHistoryNavigation(event());
  assert.equal(second.guard.isCurrentHoldingEntry(), true);
  assert.equal(second.cancellations(), 0);
  second.guard.dispose();
});

test("source stays passive; CI picks up this regression without broader permissions", async () => {
  const source = await readFile(new URL("../src/pdf-interception-back-navigation.js", import.meta.url), "utf8");
  for (const forbidden of [
    "globalThis.", "window.", "history.back(", "history.go(",
    "history.pushState(", "history.replaceState(", "tabs.goBack(",
    "addListener(", "permissions.request(", "connectNative(",
    "downloads.open(", "location.href", "fetch(", "localStorage", "sessionStorage"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
