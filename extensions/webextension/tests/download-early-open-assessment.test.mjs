import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  assessDownloadOpeningBeforeMonitoringCompletes as assess
} from "../src/download-early-open-assessment.js";

function eventSource() {
  const listeners = new Set();
  return {
    addListener(listener) { listeners.add(listener); },
    removeListener(listener) { listeners.delete(listener); },
    emit(value) { for (const listener of [...listeners]) listener(value); },
    get size() { return listeners.size; }
  };
}

const pending = (id = 7) => Object.freeze({ kind: "monitoring-pending", id });
const result = (status, possible = null) => ({
  status, browserMayOpenBeforeMonitoringCompletes: possible,
  openingBlocked: false, scanVerified: false, authorizesOpen: false
});
const tick = () => new Promise(resolve => setImmediate(resolve));

function fixture() {
  const searches = [];
  const row = {
    id: 7, state: "complete", exists: true, paused: false,
    canResume: false, url: "https://private.example/secret.pdf",
    filename: "/private/secret.pdf", danger: "safe", referrer: "secret"
  };
  const downloads = {
    onCreated: eventSource(), onChanged: eventSource(), onErased: eventSource(),
    search(query) {
      searches.push(query);
      return Promise.resolve([{ ...row }]);
    },
    open() { throw Error("Never open a download"); },
    pause() { throw Error("Never pause a download"); },
    cancel() { throw Error("Never cancel a download"); },
    setUiOptions() { throw Error("Never disable browser UI"); }
  };
  const permissions = {
    onRemoved: eventSource(),
    contains() { return Promise.resolve(true); },
    request() { throw Error("Never request downloads permission"); }
  };
  return { downloads, permissions, searches, row };
}

function assertCleaned(f) {
  assert.equal(f.downloads.onCreated.size, 0);
  assert.equal(f.downloads.onChanged.size, 0);
  assert.equal(f.downloads.onErased.size, 0);
  assert.equal(f.permissions.onRemoved.size, 0);
}

test("completed download can be openable while monitoring remains pending, never authorized", async () => {
  const f = fixture();
  const status = await assess(f.downloads, f.permissions, pending());
  assert.deepEqual(status, result("opening-possible", true));
  assert.equal(Object.isFrozen(status), true);
  assert.deepEqual(f.searches, [{ id: 7 }]);
  assertCleaned(f);
  assert.equal(JSON.stringify(status).includes("secret"), false);
});

test("in-progress transfers cannot be declared protected against external opening", async () => {
  const f = fixture();
  f.row.state = "in_progress";
  assert.deepEqual(await assess(f.downloads, f.permissions, pending()),
    result("transfer-in-progress"));
  assertCleaned(f);
});

test("interrupted transfers cannot be declared safely blocked or clean", async () => {
  const f = fixture();
  f.row.state = "interrupted";
  assert.deepEqual(await assess(f.downloads, f.permissions, pending()),
    result("transfer-interrupted"));
  assertCleaned(f);
});

test("missing, malformed or ambiguous browser items never establish opening eligibility", async () => {
  for (const rows of [
    null, undefined, {}, [], [null],
    [{ id: 8, state: "complete", exists: true, paused: false, canResume: false }],
    [{ id: 7, state: "complete", exists: true, paused: false, canResume: false },
      { id: 7, state: "complete", exists: true, paused: false, canResume: false }],
    [{ id: 7, state: "unknown", exists: true, paused: false, canResume: false }]
  ]) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve(rows);
    assert.deepEqual(await assess(f.downloads, f.permissions, pending()),
      result("unknown"));
    assertCleaned(f);
  }
});

test("complete but absent, paused, resumable or error-marked items fail to unknown", async () => {
  for (const changed of [
    { exists: false }, { exists: null }, { paused: true },
    { paused: undefined }, { canResume: true }, { canResume: undefined },
    { error: "NETWORK_FAILED" }, { state: "COMPLETED" }
  ]) {
    const f = fixture();
    Object.assign(f.row, changed);
    assert.deepEqual(await assess(f.downloads, f.permissions, pending()),
      result("unknown"), JSON.stringify(changed));
    assertCleaned(f);
  }
});

test("native danger labels do not certify a safe download or opening authorization", async () => {
  for (const danger of ["safe", "accepted", "dangerous", "content", "url", "uncommon", "unknown"]) {
    const f = fixture();
    f.row.danger = danger;
    const state = await assess(f.downloads, f.permissions, pending());
    assert.equal(state.openingBlocked, false);
    assert.equal(state.scanVerified, false);
    assert.equal(state.authorizesOpen, false);
    assert.equal(state.browserMayOpenBeforeMonitoringCompletes, true);
    assertCleaned(f);
  }
});

test("forged pending notices are rejected before querying or acquiring permission", async () => {
  const f = fixture();
  let calls = 0, getters = 0;
  f.permissions.contains = () => { calls++; return Promise.resolve(true); };
  const accessor = { kind: "monitoring-pending" };
  Object.defineProperty(accessor, "id", { get() {
    getters++;
    throw Error("/private/secret.pdf");
  } });
  const symbol = { kind: "monitoring-pending", id: 7 };
  symbol[Symbol("private")] = "secret";
  for (const value of [
    undefined, null, [], "pending", {}, { kind: "completed", id: 7 },
    { kind: "monitoring-pending", id: "7" },
    { kind: "monitoring-pending", id: -1 },
    { kind: "monitoring-pending", id: 1.5 },
    { kind: "monitoring-pending", id: Number.MAX_SAFE_INTEGER + 1 },
    { kind: "monitoring-pending", id: 7, filename: "/private/file.pdf" },
    Object.assign(Object.create({ kind: "monitoring-pending" }), { id: 7 }),
    accessor, symbol
  ]) assert.deepEqual(await assess(f.downloads, f.permissions, value), result("unknown"));
  assert.equal(calls, 0);
  assert.equal(getters, 0);
  assert.deepEqual(f.searches, []);
  assertCleaned(f);
});

test("denied, missing, synchronous or rejected permissions fail closed without querying", async () => {
  for (const contains of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => true, () => undefined,
    () => Promise.reject(Error("secret download path"))
  ]) {
    const f = fixture();
    f.permissions.contains = contains;
    assert.deepEqual(await assess(f.downloads, f.permissions, pending()),
      result("unknown"));
    assert.deepEqual(f.searches, []);
    assertCleaned(f);
  }
  for (const missing of ["contains", "search", "onRemoved", "onCreated", "onChanged", "onErased"]) {
    const f = fixture();
    delete (missing === "contains" || missing === "onRemoved" ? f.permissions : f.downloads)[missing];
    assert.deepEqual(await assess(f.downloads, f.permissions, pending()),
      result("unknown"));
  }
});

test("permission revocation during pending grant cancels any opening assessment", async () => {
  const f = fixture();
  let release;
  f.permissions.contains = () => new Promise(resolve => { release = resolve; });
  const pendingResult = assess(f.downloads, f.permissions, pending());
  f.permissions.onRemoved.emit({ permissions: ["downloads"] });
  release(true);
  assert.deepEqual(await pendingResult, result("unknown"));
  assert.deepEqual(f.searches, []);
  assertCleaned(f);
});

test("permission revocation while search is pending discards its completed result", async () => {
  const f = fixture();
  let release;
  f.downloads.search = q => {
    f.searches.push(q);
    return new Promise(resolve => { release = resolve; });
  };
  const pendingResult = assess(f.downloads, f.permissions, pending());
  await tick();
  assert.deepEqual(f.searches, [{ id: 7 }]);
  f.permissions.onRemoved.emit({ permissions: ["tabs"] });
  f.permissions.onRemoved.emit({ permissions: ["downloads"] });
  release([{ ...f.row }]);
  assert.deepEqual(await pendingResult, result("unknown"));
  assertCleaned(f);
});

test("download changes or ID reuse while query is pending invalidate a stale conclusion", async () => {
  for (const kind of ["onCreated", "onChanged", "onErased"]) {
    const f = fixture();
    let release;
    f.downloads.search = () => new Promise(resolve => { release = resolve; });
    const pendingResult = assess(f.downloads, f.permissions, pending());
    await tick();
    const item = kind === "onErased" ? 7 :
      kind === "onCreated" ? { id: 7, state: "in_progress" } :
      { id: 7, state: { current: "interrupted" } };
    f.downloads[kind].emit(item);
    release([{ ...f.row }]);
    assert.deepEqual(await pendingResult, result("unknown"), kind);
    assertCleaned(f);
  }
});

test("unrelated download updates never invalidate a scoped opening assessment", async () => {
  const f = fixture();
  let release;
  f.downloads.search = () => new Promise(resolve => { release = resolve; });
  const pendingResult = assess(f.downloads, f.permissions, pending());
  await tick();
  f.downloads.onChanged.emit({ id: 8, state: { current: "interrupted" } });
  release([{ ...f.row }]);
  assert.deepEqual(await pendingResult, result("opening-possible", true));
  assertCleaned(f);
});

test("hostile browser data accessors and rejected searches are swallowed without exposing secrets", async () => {
  const f = fixture();
  let getterCalled = 0;
  const bad = { id: 7, exists: true, paused: false, canResume: false };
  Object.defineProperty(bad, "state", { get() {
    getterCalled++;
    throw Error("secret");
  } });
  f.downloads.search = () => Promise.resolve([bad]);
  assert.deepEqual(await assess(f.downloads, f.permissions, pending()), result("unknown"));
  assert.equal(getterCalled, 0);
  f.downloads.search = () => Promise.reject(Error("private://download"));
  assert.deepEqual(await assess(f.downloads, f.permissions, pending()), result("unknown"));
  assertCleaned(f);
});

test("never opens, pauses, cancels, requests permissions or activates inactive extension", async () => {
  const f = fixture();
  await assess(f.downloads, f.permissions, pending());
  const source = await readFile(new URL("../src/download-early-open-assessment.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = await readFile(new URL("../manifest.json", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.equal(JSON.parse(manifest).permissions.includes("downloads.open"), false);
  for (const forbidden of [
    "downloads.open(", "downloads.pause(", "downloads.cancel(", "downloads.removeFile(",
    "setUiOptions(", "sendNativeMessage(", "connectNative(", "scan_and_open",
    "clamscan", "fetch(", "node:fs", "storage.local", "permissions.request("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
