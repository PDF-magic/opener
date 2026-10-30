import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectCompletedDownloadPdfMime as detect } from "../src/download-pdf-mime.js";
import { retrieveCompletedDownloadMime } from "../src/download-mime.js";

function expected(id, yes) {
  return { id, isPdfMime: yes, evidence: yes ? "mime-type" : "none",
    authorizesOpen: false };
}

test("recognizes PDF media types using the shared detector, including parameters and case", () => {
  for (const mime of ["application/pdf", "APPLICATION/PDF", "application/x-pdf",
    "Application/X-PDF; charset=UTF-8", "application/pdf; charset=\"binary\""]) {
    const result = detect({ id: 123, mime });
    assert.deepEqual(result, expected(123, true));
    assert.equal(Object.isFrozen(result), true);
    assert.equal("mime" in result, false);
  }
});

test("valid non-PDF types are classified as non-PDF without filename inference", () => {
  for (const mime of ["application/octet-stream", "binary/octet-stream",
    "text/plain", "image/png", "application/json", "application/pdf+json",
    "application/vnd.adobe.xfdf"]) {
    assert.deepEqual(detect({ id: 7, mime }), expected(7, false));
  }
  assert.equal(detect({ id: 7, mime: "text/plain", filename: "fake.pdf" }), null);
  assert.equal(detect({ id: 7, mime: "application/octet-stream",
    url: "https://private.invalid/document.pdf" }), null);
});

test("invalid MIME declarations fail closed instead of treating an extension as proof", () => {
  for (const mime of [null, undefined, "", "application", "application/",
    "application/pdf\nCookie: private", "application/pdf; invalid",
    "application/pdf; charset=UTF-8\r", "text/html, application/pdf",
    "application/pdf ".repeat(22), "application/pdf; q=1; q=\"unterminated",
    "https://private.invalid/document.pdf", 7, { toString() { throw Error("private"); } }]) {
    assert.equal(detect({ id: 5, mime }), null);
  }
});

test("requires exactly the trusted metadata-only completion MIME record shape", () => {
  const inherited = Object.assign(Object.create({ id: 7 }), { mime: "application/pdf" });
  const symbol = { id: 7, mime: "application/pdf" };
  symbol[Symbol("secret")] = true;
  for (const data of [null, undefined, "", 3, [], {}, inherited, symbol,
    { id: -1, mime: "application/pdf" },
    { id: 0.5, mime: "application/pdf" },
    { id: "7", mime: "application/pdf" },
    { id: Number.MAX_SAFE_INTEGER + 1, mime: "application/pdf" },
    { id: 7, mime: "application/pdf", scanVerified: true },
    { id: 7, mime: "application/pdf", filename: "/private/file" }]) {
    assert.equal(detect(data), null);
  }
  assert.deepEqual(detect(Object.assign(Object.create(null),
    { id: 0, mime: "application/pdf" })), expected(0, true));
});

test("does not invoke accessors or disclose hostile proxy metadata", () => {
  let invoked = 0;
  const accessor = { id: 7 };
  Object.defineProperty(accessor, "mime", { enumerable: true,
    get() { invoked++; throw Error("private download metadata"); } });
  assert.equal(detect(accessor), null);
  const proxy = new Proxy({ id: 7, mime: "application/pdf" }, {
    ownKeys() { throw Error("private browser info"); }
  });
  assert.equal(detect(proxy), null);
  assert.equal(invoked, 0);
});

test("classifies only the MIME returned by an authorized completed-ID browser lookup", async () => {
  let searched = 0, checked = 0;
  const revocations = new Set();
  const permissionsApi = {
    onRemoved: {
      addListener(listener) { revocations.add(listener); },
      removeListener(listener) { revocations.delete(listener); }
    },
    contains({ permissions }) {
      checked++;
      assert.deepEqual(permissions, ["downloads"]);
      return Promise.resolve(true);
    }
  };
  const downloadsApi = {
    search({ id }) {
      searched++;
      assert.equal(id, 42);
      return Promise.resolve([{
        id, state: "complete", mime: "application/pdf",
        filename: "/private/account.pdf",
        url: "https://private.invalid/account",
        danger: "dangerous", scanVerified: true
      }]);
    }
  };
  const mime = await retrieveCompletedDownloadMime(downloadsApi, permissionsApi,
    Object.freeze({ kind: "completed", id: 42 }));
  const result = detect(mime);
  assert.deepEqual(result, expected(42, true));
  assert.equal(checked, 1);
  assert.equal(searched, 1);
  assert.equal(revocations.size, 0);
  assert.equal(JSON.stringify(result).includes("private"), false);
  assert.equal("filename" in result, false);
});

test("missing permissions, non-complete state or revoked grants never classify", async () => {
  let searches = 0;
  const revokedListeners = new Set();
  const permissionsApi = {
    onRemoved: {
      addListener(listener) { revokedListeners.add(listener); },
      removeListener(listener) { revokedListeners.delete(listener); }
    },
    contains() { return Promise.resolve(false); }
  };
  const downloadsApi = {
    search() { searches++; return Promise.resolve([]); }
  };
  const completion = { kind: "completed", id: 1 };
  assert.equal(detect(await retrieveCompletedDownloadMime(downloadsApi, permissionsApi, completion)), null);
  assert.equal(searches, 0);
  permissionsApi.contains = () => Promise.resolve(true);
  downloadsApi.search = () => Promise.resolve([{ id: 1, state: "interrupted", mime: "application/pdf" }]);
  assert.equal(detect(await retrieveCompletedDownloadMime(downloadsApi, permissionsApi, completion)), null);
  let release;
  downloadsApi.search = () => new Promise(resolve => { release = resolve; });
  const pending = retrieveCompletedDownloadMime(downloadsApi, permissionsApi, completion);
  await new Promise(resolve => setImmediate(resolve));
  for (const listener of revokedListeners) listener({ permissions: ["downloads"] });
  release([{ id: 1, state: "complete", mime: "application/pdf" }]);
  assert.equal(detect(await pending), null);
  assert.equal(revokedListeners.size, 0);
});

test("does not activate browser monitoring, request permissions or grant native/PDF access", async () => {
  const source = await readFile(new URL("../src/download-pdf-mime.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["addListener(", "permissions.request(", "downloads.open(",
    "sendNativeMessage(", "connectNative(", "fetch(", "ClamAV", "window.open("]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
  const result = detect({ id: 99, mime: "application/pdf" });
  assert.deepEqual(Object.keys(result).sort(),
    ["authorizesOpen", "evidence", "id", "isPdfMime"]);
  assert.equal(result.authorizesOpen, false);
});
