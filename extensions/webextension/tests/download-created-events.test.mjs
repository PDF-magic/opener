import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { registerDownloadCreatedEvents } from "../src/download-created-events.js";

function eventSource() {
  const listeners = new Set();
  let added = 0;
  let removed = 0;
  return {
    addListener(callback) { added++; listeners.add(callback); },
    removeListener(callback) { removed++; listeners.delete(callback); },
    emit(payload) { for (const callback of [...listeners]) callback(payload); },
    get size() { return listeners.size; },
    get added() { return added; },
    get removed() { return removed; }
  };
}

function browserFixture(granted = true) {
  const onCreated = eventSource();
  const onChanged = eventSource();
  const onErased = eventSource();
  const onRemoved = eventSource();
  const queries = [];
  const permissions = {
    onRemoved,
    contains(request) { queries.push(request); return Promise.resolve(granted); },
    request() { throw Error("Must never request permissions"); }
  };
  return { downloads: { onCreated, onChanged, onErased }, permissions, queries,
    onCreated, onChanged, onErased, onRemoved };
}

test("opt-in false leaves all browser APIs completely untouched", async () => {
  const untouched = new Proxy({}, {
    get() { throw Error("An inert feature must not read browser APIs"); }
  });
  const stop = await registerDownloadCreatedEvents(untouched, untouched, null);
  stop();
  const otherStop = await registerDownloadCreatedEvents(untouched, untouched, null,
    { monitoringEnabled: false });
  otherStop();
});

test("registers only onCreated after a true current grant, without requesting it", async () => {
  const f = browserFixture();
  const events = [];
  const stop = await registerDownloadCreatedEvents(f.downloads, f.permissions,
    (event) => events.push(event), { monitoringEnabled: true });
  assert.deepEqual(f.queries, [{ permissions: ["downloads"] }]);
  assert.equal(f.onCreated.size, 1);
  assert.equal(f.onRemoved.size, 1);
  assert.equal(f.onChanged.size, 0);
  assert.equal(f.onErased.size, 0);

  f.onCreated.emit({ id: 0, filename: "/tmp/report.pdf", mime: "application/pdf",
    url: "https://secret.invalid/private.pdf", cookies: "secret", referrer: "secret",
    state: "in_progress", danger: "safe" });
  f.onChanged.emit({ id: 0 });
  f.onErased.emit(0);
  f.onCreated.emit({ id: "bad", url: "https://private.invalid" });
  assert.deepEqual(events, [{ kind: "created", id: 0, filename: "/tmp/report.pdf",
    mime: "application/pdf", state: "in_progress", danger: "safe" }]);
  assert.equal(Object.isFrozen(events[0]), true);
  assert.equal(JSON.stringify(events).includes("secret"), false);
  stop();
  stop();
  assert.equal(f.onCreated.size, 0);
  assert.equal(f.onRemoved.size, 0);
  f.onCreated.emit({ id: 2 });
  assert.equal(events.length, 1);
  assert.equal(f.onCreated.removed, 1);
});

test("denied or uncertain permission never attaches an onCreated listener", async () => {
  for (const check of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => undefined, () => true, () => Promise.reject(Error("hidden path")),
    () => { throw Error("permission failure"); }
  ]) {
    const f = browserFixture();
    f.permissions.contains = check;
    const stop = await registerDownloadCreatedEvents(f.downloads, f.permissions,
      () => { throw Error("Must not be invoked"); }, { monitoringEnabled: true });
    stop();
    assert.equal(f.onCreated.size, 0);
    assert.equal(f.onRemoved.size, 0);
  }
  const missing = browserFixture();
  delete missing.permissions.onRemoved;
  const stop = await registerDownloadCreatedEvents(missing.downloads,
    missing.permissions, () => {}, { monitoringEnabled: true });
  stop();
  assert.equal(missing.onCreated.size, 0);
});

test("revocation synchronously stops active event observation without regrant", async () => {
  const f = browserFixture();
  const received = [];
  const stop = await registerDownloadCreatedEvents(f.downloads, f.permissions,
    (event) => received.push(event.id), { monitoringEnabled: true });
  f.onRemoved.emit({ permissions: ["tabs"] });
  assert.equal(f.onCreated.size, 1);
  f.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  assert.equal(f.onCreated.size, 0);
  assert.equal(f.onRemoved.size, 0);
  f.onCreated.emit({ id: 7 });
  assert.deepEqual(received, []);
  stop();
  assert.equal(f.onCreated.removed, 1);
});

test("a revocation while permission check is pending prevents late registration", async () => {
  const f = browserFixture();
  let grant;
  f.permissions.contains = () => new Promise((resolve) => { grant = resolve; });
  const activation = registerDownloadCreatedEvents(f.downloads, f.permissions,
    () => {}, { monitoringEnabled: true });
  f.onRemoved.emit({ permissions: ["downloads"] });
  grant(true);
  const stop = await activation;
  assert.equal(f.onCreated.added, 0);
  assert.equal(f.onCreated.size, 0);
  assert.equal(f.onRemoved.size, 0);
  stop();
});

test("synchronous revocation during listener attachment cannot leak a listener", async () => {
  const f = browserFixture();
  const original = f.onCreated.addListener;
  f.onCreated.addListener = (listener) => {
    original(listener);
    f.onRemoved.emit({ permissions: ["downloads"] });
  };
  const stop = await registerDownloadCreatedEvents(f.downloads, f.permissions,
    () => {}, { monitoringEnabled: true });
  assert.equal(f.onCreated.size, 0);
  assert.equal(f.onRemoved.size, 0);
  stop();
});

test("bad browser APIs, malformed events and consumer exceptions remain isolated", async () => {
  const f = browserFixture();
  const failures = [];
  const received = [];
  const stop = await registerDownloadCreatedEvents(f.downloads, f.permissions,
    (event) => {
      received.push(event.id);
      if (event.id === 1) throw Error("/private/file.pdf");
      if (event.id === 2) return Promise.reject(Error("hidden token"));
    }, { monitoringEnabled: true, onError(error) { failures.push(error.message); } });
  const malicious = Object.defineProperty({}, "id", {
    get() { throw Error("untrusted browser data"); }
  });
  f.onCreated.emit(malicious);
  f.onCreated.emit({ id: 1 });
  f.onCreated.emit({ id: 2 });
  f.onCreated.emit({ id: 3 });
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(received, [1, 2, 3]);
  assert.deepEqual(failures, [
    "Download-created monitoring callback failed",
    "Download-created monitoring callback failed",
    "Download-created monitoring callback failed"
  ]);
  stop();

  const invalid = browserFixture();
  invalid.onCreated.addListener = () => { throw Error("registration failed"); };
  const denied = await registerDownloadCreatedEvents(invalid.downloads,
    invalid.permissions, () => {}, { monitoringEnabled: true });
  denied();
  assert.equal(invalid.onRemoved.size, 0);
});

test("registration is independent of the inert background and cannot scan or open", async () => {
  const source = await readFile(new URL("../src/download-created-events.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const unsafe of [
    "nativeMessaging", "sendNativeMessage(", "connectNative(", "downloads.open(",
    "downloads.search(", "fetch(", "XMLHttpRequest", "localStorage",
    "chrome.downloads", "browser.downloads", "clamscan", "scan_and_open"
  ]) {
    assert.equal(source.includes(unsafe), false, unsafe);
  }
});
