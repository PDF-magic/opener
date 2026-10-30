import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { subscribeToDownloadRenames as subscribe } from "../src/download-renames.js";

function event() {
  const listeners = new Set();
  return {
    addListener(fn) { listeners.add(fn); },
    removeListener(fn) { listeners.delete(fn); },
    emit(value) { for (const fn of [...listeners]) fn(value); },
    get size() { return listeners.size; }
  };
}
function fixture(callback = () => {}) {
  const api = { onCreated: event(), onChanged: event(), onErased: event() };
  const notices = [], errors = [];
  const stop = subscribe(api, (value) => { notices.push(value); callback(value); },
    { onError: (error) => errors.push(error) });
  return { api, notices, errors, stop };
}
const created = (id = 7, name = "/private/old.pdf") =>
  ({ id, state: "in_progress", filename: name });
const changed = (previous, current, id = 7, state) => ({
  id, filename: { previous, current },
  ...(state ? { state: { current: state } } : {})
});

test("detects in-progress renames by ID without forwarding local paths", () => {
  const f = fixture();
  f.api.onCreated.emit(created());
  f.api.onChanged.emit(changed("/private/old.pdf", "/private/new.pdf"));
  f.api.onChanged.emit(changed("/private/new.pdf", "/private/new.PDF"));
  assert.deepEqual(f.notices, [{ kind: "renamed", id: 7 }, { kind: "renamed", id: 7 }]);
  for (const notice of f.notices) {
    assert.equal(Object.isFrozen(notice), true);
    assert.deepEqual(Object.keys(notice).sort(), ["id", "kind"]);
    assert.equal(JSON.stringify(notice).includes("private"), false);
  }
  assert.deepEqual(f.errors, []);
  f.stop();
});

test("a first filename assignment or unchanged filename is not a rename", () => {
  const f = fixture();
  f.api.onCreated.emit(created());
  for (const delta of [
    { id: 7, filename: { current: "/private/initial.pdf" } },
    { id: 7, filename: { previous: "", current: "/private/initial.pdf" } },
    changed("/private/same.pdf", "/private/same.pdf"),
    { id: 7, filename: { previous: "/private/old.pdf" } },
    { id: 7, danger: { current: "safe" } },
    { id: 7, filename: { previous: "/private/a.pdf", current: "/private/a.pdf", ignored: true } }
  ]) f.api.onChanged.emit(delta);
  assert.deepEqual(f.notices, []);
  f.stop();
});

test("only browser-observed active downloads can trigger a rename", () => {
  const f = fixture();
  f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  f.api.onCreated.emit({ id: 7, state: "complete", filename: "a.pdf" });
  f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  f.api.onCreated.emit({ id: 7, state: "interrupted", filename: "a.pdf" });
  f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  f.api.onCreated.emit(created());
  f.api.onChanged.emit(changed("a.pdf", "b.pdf", 8));
  f.api.onChanged.emit(changed("a.pdf", "b.pdf", 7, "complete"));
  f.api.onChanged.emit(changed("b.pdf", "c.pdf"));
  assert.deepEqual(f.notices, []);
  f.stop();
});

test("interrupt, erasure, and ID reuse reset tracking", () => {
  const f = fixture();
  f.api.onCreated.emit(created());
  f.api.onChanged.emit(changed("a.pdf", "b.pdf", 7, "interrupted"));
  f.api.onChanged.emit(changed("b.pdf", "c.pdf"));
  f.api.onCreated.emit(created());
  f.api.onErased.emit(7);
  f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  f.api.onCreated.emit(created());
  f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  assert.deepEqual(f.notices, [{ kind: "renamed", id: 7 }]);
  f.stop();
});

test("invalid IDs, state transitions, filenames and hostile accessors fail closed", () => {
  const f = fixture();
  f.api.onCreated.emit(created());
  const hostile = { previous: "a.pdf" };
  let invoked = 0;
  Object.defineProperty(hostile, "current", { get() { invoked++; throw Error("private path"); } });
  const badItems = [
    changed("a.pdf", "b.pdf", -1), changed("a.pdf", "b.pdf", 1.5),
    changed("a.pdf", "b.pdf", "7"),
    changed("a.pdf", "b.pdf", Number.MAX_SAFE_INTEGER + 1),
    { id: 7, filename: hostile },
    { id: 7, filename: { previous: "a.pdf", current: "b\n.pdf" } },
    changed("a.pdf", "x".repeat(4097)),
    { id: 7, filename: { previous: "a.pdf", current: 7 } },
    { id: 7, state: { current: "unknown" }, filename: { previous: "a.pdf", current: "b.pdf" } },
    { id: 7, state: { previous: "in_progress" }, filename: { previous: "a.pdf", current: "b.pdf" } },
    Object.assign(Object.create({ id: 7 }), { filename: { previous: "a.pdf", current: "b.pdf" } }),
    { id: 7, filename: new Proxy({}, { getPrototypeOf() { throw Error("private"); } }) }
  ];
  for (const item of badItems) f.api.onChanged.emit(item);
  assert.deepEqual(f.notices, []);
  assert.equal(invoked, 0);
  f.stop();
});

test("created invalid objects and spoofed IDs are not tracked", () => {
  const f = fixture();
  let reads = 0;
  const hostile = { state: "in_progress" };
  Object.defineProperty(hostile, "id", { get() { reads++; throw Error("private"); } });
  for (const item of [hostile, { id: -1, state: "in_progress" },
    { id: "7", state: "in_progress" }, { id: 7, state: "complete" },
    { id: 7 }, Object.assign(Object.create({ id: 7 }), { state: "in_progress" })]) {
    f.api.onCreated.emit(item);
    f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  }
  assert.equal(reads, 0);
  assert.deepEqual(f.notices, []);
  f.stop();
});

test("limit active IDs and evict oldest without retaining filenames", () => {
  const f = fixture();
  for (let id = 0; id <= 256; id++) f.api.onCreated.emit(created(id));
  f.api.onChanged.emit(changed("a.pdf", "b.pdf", 0));
  f.api.onChanged.emit(changed("a.pdf", "b.pdf", 256));
  assert.deepEqual(f.notices, [{ kind: "renamed", id: 256 }]);
  f.stop();
});

test("callback failures are contained and errors are sanitized", () => {
  const f = fixture(() => { throw Error("private browser profile path"); });
  f.api.onCreated.emit(created());
  f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  assert.deepEqual(f.notices, [{ kind: "renamed", id: 7 }]);
  assert.equal(f.errors.length, 1);
  assert.equal(f.errors[0].message.includes("private"), false);
  f.stop();
});

test("registration rolls back and unsubscribe detaches listeners exactly once", () => {
  const f = fixture();
  f.api.onCreated.emit(created());
  f.stop();
  f.stop();
  for (const e of Object.values(f.api)) assert.equal(e.size, 0);
  f.api.onChanged.emit(changed("a.pdf", "b.pdf"));
  assert.deepEqual(f.notices, []);
  const bad = { onCreated: event(), onChanged: event(), onErased: event() };
  bad.onChanged.addListener = () => { throw Error("secret"); };
  assert.throws(() => subscribe(bad, () => {}), /Cannot register/);
  assert.equal(bad.onCreated.size, 0);
});

test("module stays dormant without filesystem, browser globals, scan or open actions", async () => {
  const source = await readFile(new URL("../src/download-renames.js", import.meta.url), "utf8");
  assert.equal(source.includes("globalThis.browser"), false);
  for (const forbidden of ["nativeMessaging", "connectNative(", "sendNativeMessage(",
    "downloads.open(", "node:fs", "clamscan", "scan_and_open", "fetch(",
    "localStorage", "permissions.request("]) assert.equal(source.includes(forbidden), false, forbidden);
});
