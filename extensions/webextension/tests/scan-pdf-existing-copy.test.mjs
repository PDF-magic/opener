import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { findExistingDownloadedPdfCopy as findCopy } from "../src/scan-pdf-existing-copy.js";

const URL = "https://example.test/private/document.pdf?token=secret";
const selected = (url = URL) => ({ kind: "trusted-current-pdf-source", url });
const row = (overrides = {}) => ({
  id: 17, url: URL, state: "complete",
  filename: "/Users/example/Downloads/document.pdf",
  exists: true, paused: false, canResume: false,
  bytesReceived: 512, totalBytes: 512, danger: "safe",
  ...overrides
});

function event() {
  const listeners = new Set();
  return {
    addListener(fn) { listeners.add(fn); },
    removeListener(fn) { listeners.delete(fn); },
    emit(value) { for (const fn of [...listeners]) fn(value); },
    get size() { return listeners.size; }
  };
}
function fixture(records = [row()]) {
  const calls = [], onRemoved = event(), onCreated = event(),
    onChanged = event(), onErased = event();
  const downloads = {
    onCreated, onChanged, onErased,
    search(query) {
      calls.push(query);
      return Promise.resolve(typeof records === "function" ? records(query) : records);
    },
    open() { throw Error("unapproved browser opening"); },
    download() { throw Error("unapproved browser download"); }
  };
  const permissions = {
    onRemoved,
    contains(query) {
      assert.deepEqual(query, { permissions: ["downloads"] });
      return Promise.resolve(true);
    },
    request() { throw Error("must not request permissions"); }
  };
  const all = [onRemoved, onCreated, onChanged, onErased];
  return { downloads, permissions, calls, onRemoved, onChanged,
    onErased, onCreated,
    assertDetached() { assert.deepEqual(all.map(x => x.size), [0, 0, 0, 0]); } };
}
const expected = {
  kind: "existing-browser-download-candidate",
  downloadId: 17, browserReportsExistingCopy: true,
  nativeFileVerified: false, requiresNativeRevalidation: true,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
};

test("matches one existing completed copy with exact URL and final fresh preflight", async () => {
  const f = fixture();
  const result = await findCopy(f.downloads, f.permissions, selected(URL + "#page=3"));
  assert.deepEqual(result, expected);
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(f.calls.slice(1), [{ id: 17 }, { id: 17 }, { id: 17 }]);
  assert.equal(f.calls.length, 4);
  assert.equal(f.calls[0].limit, 16);
  assert.equal(new RegExp(f.calls[0].url).test(URL), true);
  assert.equal(new RegExp(f.calls[0].url).test(URL + "/other"), false);
  assert.equal(new RegExp(f.calls[0].url).test(URL.replace("?", "X")), false);
  assert.doesNotMatch(JSON.stringify(result), /secret|private|Users|example.test/);
  f.assertDetached();
});

test("missing, ambiguous, incomplete or deleted browser history is unavailable", async () => {
  for (const records of [
    [], [row(), row({ id: 18 })],
    [row({ id: "17" })], [row({ id: -1 })],
    [row({ url: "https://other.test/document.pdf" })],
    [row({ state: "in_progress" })], [row({ exists: false })],
    [row({ exists: undefined })], [row({ paused: true })],
    [row({ canResume: true })], [row({ error: "FILE_FAILED" })],
    [row({ totalBytes: 999 })], [row({ bytesReceived: 0 })],
    [row({ filename: "document.pdf" })],
    [row({ filename: "/tmp/document.pdf.crdownload" })],
    [row({ filename: "/tmp/../private.pdf" })]
  ]) {
    const f = fixture(records);
    assert.equal(await findCopy(f.downloads, f.permissions, selected()), null,
      JSON.stringify(records).slice(0, 180));
    f.assertDetached();
  }
});

test("rejects unsupported, credential-bearing, hostile or page-authored selections before APIs", async () => {
  const invalid = [
    undefined, null, [], {}, { url: URL },
    { kind: "trusted-current-pdf-source" },
    { kind: "trusted-current-pdf-source", url: URL, isPdfCandidate: true },
    Object.assign(Object.create({ kind: "trusted-current-pdf-source" }), { url: URL }),
    selected("blob:https://example.test/a.pdf"),
    selected("data:application/pdf,abc"),
    selected("file:///Users/private/document.pdf"),
    selected("https://user:pass@example.test/document.pdf"),
    selected("https://example.test/document.pdf\nbad"),
    selected("https://example.test/" + "a".repeat(8193)),
    selected("not a url")
  ];
  const getter = { kind: "trusted-current-pdf-source" };
  Object.defineProperty(getter, "url", { get() { throw Error("getter"); } });
  invalid.push(getter, new Proxy({}, { getPrototypeOf() { throw Error("proxy"); } }));
  const f = fixture();
  for (const selection of invalid) {
    assert.equal(await findCopy(f.downloads, f.permissions, selection), null);
  }
  assert.deepEqual(f.calls, []);
  f.assertDetached();
});

test("denied permissions and unsupported browser APIs perform no history search", async () => {
  for (const contains of [
    () => Promise.resolve(false), () => false,
    () => Promise.reject(Error("private")), () => { throw Error("private"); }
  ]) {
    const f = fixture();
    f.permissions.contains = contains;
    assert.equal(await findCopy(f.downloads, f.permissions, selected()), null);
    assert.deepEqual(f.calls, []);
    f.assertDetached();
  }
  const f = fixture();
  delete f.downloads.onErased;
  assert.equal(await findCopy(f.downloads, f.permissions, selected()), null);
  const g = fixture();
  g.downloads.search = () => false;
  assert.equal(await findCopy(g.downloads, g.permissions, selected()), null);
  g.assertDetached();
});

test("permission revocation during a browser search drops the matching copy", async () => {
  const f = fixture();
  let resolveFirst;
  f.downloads.search = (query) => {
    f.calls.push(query);
    if (!Object.hasOwn(query, "url")) return Promise.resolve([row()]);
    return new Promise(resolve => { resolveFirst = resolve; });
  };
  const pending = findCopy(f.downloads, f.permissions, selected());
  await new Promise(resolve => setImmediate(resolve));
  f.onRemoved.emit({ permissions: ["downloads"], origins: [] });
  resolveFirst([row()]);
  assert.equal(await pending, null);
  assert.equal(f.calls.length, 1);
  f.assertDetached();
});

test("rename, erasure or ID reuse during lookup invalidates the candidate", async () => {
  for (const [source, payload] of [
    ["onChanged", { id: 17, filename: { current: "/other.pdf" } }],
    ["onErased", 17],
    ["onCreated", row()]
  ]) {
    const f = fixture();
    let finish, count = 0;
    f.downloads.search = (query) => {
      f.calls.push(query);
      count++;
      if (count === 2) return new Promise(resolve => { finish = resolve; });
      return Promise.resolve([row()]);
    };
    const pending = findCopy(f.downloads, f.permissions, selected());
    await new Promise(resolve => setImmediate(resolve));
    f[source].emit(payload);
    finish([row()]);
    assert.equal(await pending, null, source);
    f.assertDetached();
  }
});

test("hostile history records, accessors and browser exceptions fail privately", async () => {
  const bad = row();
  Object.defineProperty(bad, "url", { get() { throw Error("getter"); } });
  for (const records of [
    [bad], [Object.create({ id: 17, url: URL })], Array(1),
    new Proxy([], { get(_, key) { if (key === "length") throw Error("secret"); } })
  ]) {
    const f = fixture(records);
    assert.equal(await findCopy(f.downloads, f.permissions, selected()), null);
    f.assertDetached();
  }
  const f = fixture();
  f.downloads.search = () => Promise.reject(Error("/Users/secret/private.pdf"));
  assert.equal(await findCopy(f.downloads, f.permissions, selected()), null);
  f.assertDetached();
});

test("rechecked source URL must still match the selected document", async () => {
  let count = 0;
  const f = fixture(() => {
    count++;
    return [count === 3 ? row({ url: "https://other.test/file.pdf" }) : row()];
  });
  assert.equal(await findCopy(f.downloads, f.permissions, selected()), null);
  f.assertDetached();
});

test("no import-time privileges, scanner bypasses, or preference changes", async () => {
  const load = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, background, manifestText, safariText, ci] = await Promise.all([
    load("../src/scan-pdf-existing-copy.js"), load("../src/background.js"),
    load("../manifest.json"), load("../../safari/manifest.json"),
    load("../../../.github/workflows/ci.yml")
  ]);
  const manifest = JSON.parse(manifestText), safari = JSON.parse(safariText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(ci, /node --test tests\/scan-pdf-existing-copy\.test\.mjs/);
  for (const forbidden of [
    "permissions.request(", "sendNativeMessage(", "connectNative(",
    "fetch(", "XMLHttpRequest", "downloads.open(", "window.open(",
    "node:fs", "scan-and-open", "clamscan(", "console."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
