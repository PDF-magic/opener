import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { verifyBrowserNativeMalwareWarning as verify } from "../src/download-browser-warning.js";

const notice = (id = 7) => Object.freeze({ kind: "completed", id });
function events() {
  const subscribers = new Set();
  return {
    addListener(fn) { subscribers.add(fn); },
    removeListener(fn) { subscribers.delete(fn); },
    emit(payload) { for (const fn of [...subscribers]) fn(payload); },
    get size() { return subscribers.size; }
  };
}
function fixture(...values) {
  const danger = values.length === 0 ? "safe" : values[0];
  const searches = [], grants = [];
  const downloads = {
    search(query) {
      searches.push(query);
      return Promise.resolve([{ id: query.id, state: "complete", exists: true,
        danger, filename: "/private/secret.pdf", url: "https://secret.invalid/",
        cookies: "secret", authorizesOpen: true, scanVerified: true }]);
    },
    acceptDanger() { throw Error("must never accept browser warnings"); },
    open() { throw Error("must never open a download"); },
    removeFile() { throw Error("must never remove a download"); },
    erase() { throw Error("must never erase a download"); }
  };
  const permissions = {
    onRemoved: events(),
    contains(query) { grants.push(query); return Promise.resolve(true); },
    request() { throw Error("must never request browser privileges"); }
  };
  return { downloads, permissions, searches, grants };
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test("only explicit safe browser classifications pass without modifying warnings", async () => {
  for (const danger of ["safe", "deepScannedSafe"]) {
    const f = fixture(danger);
    const result = await verify(f.downloads, f.permissions, notice());
    assert.deepEqual(result, {
      id: 7, browserDanger: danger, authorizesScan: false, authorizesOpen: false
    });
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(f.searches, [{ id: 7 }]);
    assert.deepEqual(f.grants, [{ permissions: ["downloads"] }]);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
});

test("native browser warnings, bypassed warnings and unknown classifications block handoff", async () => {
  for (const danger of ["file", "url", "content", "uncommon", "host", "unwanted",
    "accepted", "allowlistedByPolicy", "asyncScanning", "asyncLocalPasswordScanning",
    "passwordProtected", "sensitiveContentWarning", "sensitiveContentBlock",
    "deepScannedOpenedDangerous", "promptForScanning", "blockedTooLarge",
    "blockedPasswordProtected", "", undefined, null, "futureBrowserState"]) {
    const f = fixture(danger);
    assert.equal(await verify(f.downloads, f.permissions, notice()), null, String(danger));
    assert.deepEqual(f.searches, [{ id: 7 }]);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
});

test("missing, erased, interrupted, stale or ambiguous download records fail closed", async () => {
  const cases = [
    [], null, {}, [null],
    [{ id: 8, state: "complete", exists: true, danger: "safe" }],
    [{ id: 7, state: "in_progress", exists: true, danger: "safe" }],
    [{ id: 7, state: "interrupted", exists: true, danger: "safe" }],
    [{ id: 7, state: "complete", exists: false, danger: "safe" }],
    [{ id: 7, state: "complete", exists: true }],
    [{ id: 7, state: "complete", exists: true, danger: "safe" },
      { id: 7, state: "complete", exists: true, danger: "safe" }]
  ];
  for (const value of cases) {
    const f = fixture();
    f.downloads.search = () => Promise.resolve(value);
    assert.equal(await verify(f.downloads, f.permissions, notice()), null);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
});

test("malformed or forged completion events never access privileged browser APIs", async () => {
  const f = fixture();
  let accessors = 0;
  const accessor = { kind: "completed" };
  Object.defineProperty(accessor, "id", { get() { accessors++; throw Error("private"); } });
  for (const value of [null, {}, [], "completed", accessor,
    { kind: "created", id: 7 }, { kind: "completed", id: "7" },
    { kind: "completed", id: -1 }, { kind: "completed", id: 7, filename: "private" },
    Object.assign(Object.create({ kind: "completed" }), { id: 7 })]) {
    assert.equal(await verify(f.downloads, f.permissions, value), null);
  }
  assert.deepEqual(f.searches, []);
  assert.deepEqual(f.grants, []);
  assert.equal(accessors, 0);
});

test("permission denial, missing observer and browser errors cannot waive a warning", async () => {
  for (const contains of [
    () => Promise.resolve(false), () => Promise.resolve(null),
    () => Promise.reject(Error("/private/browser/profile")),
    () => false, () => undefined, () => { throw Error("private"); }
  ]) {
    const f = fixture();
    f.permissions.contains = contains;
    assert.equal(await verify(f.downloads, f.permissions, notice()), null);
    assert.deepEqual(f.searches, []);
    assert.equal(f.permissions.onRemoved.size, 0);
  }
  const f = fixture();
  delete f.permissions.onRemoved;
  assert.equal(await verify(f.downloads, f.permissions, notice()), null);
  const next = fixture();
  next.downloads.search = () => Promise.reject(Error("confidential download path"));
  assert.equal(await verify(next.downloads, next.permissions, notice()), null);
  assert.equal(next.permissions.onRemoved.size, 0);
});

test("permission revocation during grant or lookup discards late safe results", async () => {
  const f = fixture();
  let grant;
  f.permissions.contains = () => new Promise(resolve => { grant = resolve; });
  const pending = verify(f.downloads, f.permissions, notice());
  f.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  grant(true);
  assert.equal(await pending, null);
  assert.deepEqual(f.searches, []);
  assert.equal(f.permissions.onRemoved.size, 0);

  const second = fixture();
  let finish;
  second.downloads.search = query => {
    second.searches.push(query);
    return new Promise(resolve => { finish = resolve; });
  };
  const waiting = verify(second.downloads, second.permissions, notice());
  await tick();
  assert.deepEqual(second.searches, [{ id: 7 }]);
  second.permissions.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  finish([{ id: 7, state: "complete", exists: true, danger: "safe" }]);
  assert.equal(await waiting, null);
  assert.equal(second.permissions.onRemoved.size, 0);
});

test("hostile result getters, array accessors and exceptions never surface private data", async () => {
  let called = 0;
  const item = { id: 7, state: "complete", exists: true };
  Object.defineProperty(item, "danger", {
    get() { called++; throw Error("private malware warning"); }
  });
  const f = fixture();
  f.downloads.search = () => Promise.resolve([item]);
  assert.equal(await verify(f.downloads, f.permissions, notice()), null);
  const arr = [null];
  Object.defineProperty(arr, "0", { get() { called++; throw Error("private"); } });
  f.downloads.search = () => Promise.resolve(arr);
  assert.equal(await verify(f.downloads, f.permissions, notice()), null);
  assert.equal(called, 0);
});

test("the module never acknowledges or changes native browser malware warnings", async () => {
  const code = await readFile(new URL("../src/download-browser-warning.js", import.meta.url), "utf8");
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["acceptDanger(", "removeFile(", "downloads.open(",
    "downloads.erase(", "open(", "connectNative(", "sendNativeMessage(",
    "clamscan", "fetch(", "permissions.request(", "storage.local", "node:fs"]) {
    assert.equal(code.includes(forbidden), false, forbidden);
  }
});
