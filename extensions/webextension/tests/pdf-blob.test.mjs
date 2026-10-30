import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { detectBlobPdfContent as detect } from "../src/pdf-blob.js";

const NONE = { isPdfCandidate: false, evidence: "none", authorizesOpen: false };
const PDF = { isPdfCandidate: true, evidence: "blob-signature", authorizesOpen: false };
const ID = "123e4567-e89b-12d3-a456-426614174000";
const event = (url = "blob:https://example.test/" + ID, extra = {}) =>
  ({ tabId: 7, frameId: 0, url, ...extra });
const content = (bytes = "%PDF-1.7\nmock", type = "application/pdf") =>
  new Blob([bytes], { type });

test("finds signed PDF content in accessible top and embedded-frame Blobs", async () => {
  for (const url of ["blob:https://example.test/" + ID,
    "blob:http://localhost:8080/" + ID, "blob:null/" + ID]) {
    for (const frameId of [0, 2]) {
      assert.deepEqual(await detect(event(url, { frameId }), content()), PDF);
    }
  }
  for (const type of ["", "application/x-pdf", "application/octet-stream",
    "binary/octet-stream"]) {
    assert.deepEqual(await detect(event(), content("%PDF-1.4", type)), PDF);
  }
});

test("MIME and URL claims do not replace actual PDF signature bytes", async () => {
  for (const value of [null, undefined, {}, "application/pdf", new Uint8Array([37,80,68,70,45])]) {
    assert.deepEqual(await detect(event(), value), NONE);
  }
  for (const bytes of ["", "%PDF", "PDF-1.7", "<html>PDF</html>", "not pdf"]) {
    assert.deepEqual(await detect(event(), content(bytes)), NONE);
  }
  for (const type of ["text/html", "image/png", "application/pdf+json"]) {
    assert.deepEqual(await detect(event(), content("%PDF-1.7", type)), NONE);
  }
});

test("rejects forged, noncanonical and unsupported URL forms", async () => {
  for (const url of [
    "https://example.test/report.pdf", "data:application/pdf,%PDF-",
    "blob:ftp://example.test/" + ID, "blob:file:///tmp/" + ID,
    "blob:https://user:password@example.test/" + ID,
    "blob:https://example.test/path/" + ID,
    "blob:https://example.test/report.pdf",
    "blob:https://example.test/" + ID + "?name=report.pdf",
    "blob:https://example.test/" + ID + "#page=1",
    "blob:https://example.test/" + ID + "%2Fescape",
    "blob:https://example.test/" + ID + "\n",
    "blob:https://example.test:443/" + ID,
    "blob:null/" + ID + "/extra", "blob:NULL/" + ID,
    "blob:https://example.test/" + "a".repeat(8200)
  ]) assert.deepEqual(await detect(event(url), content()), NONE, url);
});

test("rejects invalid tab/frame metadata and hostile input", async () => {
  for (const patch of [{ tabId: -1 }, { tabId: "7" }, { tabId: undefined },
    { tabId: 1.5 }, { frameId: -1 }, { frameId: "0" },
    { frameId: undefined }, { frameId: null }]) {
    assert.deepEqual(await detect(event(undefined, patch), content()), NONE);
  }
  for (const input of [null, undefined, [], new Date(), Object.create(event())]) {
    assert.deepEqual(await detect(input, content()), NONE);
  }
  let getterCalls = 0;
  const bad = event();
  Object.defineProperty(bad, "url", {
    get() { getterCalls++; return "blob:null/" + ID; }
  });
  assert.deepEqual(await detect(bad, content()), NONE);
  const actual = content();
  for (const field of ["size", "type", "slice", "arrayBuffer"]) {
    Object.defineProperty(actual, field, {
      get() { getterCalls++; throw Error("untrusted"); }
    });
  }
  assert.deepEqual(await detect(event(), actual), PDF);
  assert.deepEqual(await detect(new Proxy({}, {
    getPrototypeOf() { throw Error("untrusted"); }
  }), content()), NONE);
  assert.equal(getterCalls, 0);
});

test("frozen candidate responses cannot leak URLs or authorize opening", async () => {
  for (const blob of [content(), content("not PDF")]) {
    const result = await detect(event("blob:https://private.test/" + ID), blob);
    assert.equal(Object.isFrozen(result), true);
    assert.deepEqual(Object.keys(result).sort(),
      ["authorizesOpen", "evidence", "isPdfCandidate"]);
    assert.equal(result.authorizesOpen, false);
    assert.equal(JSON.stringify(result).includes("private"), false);
    assert.equal(JSON.stringify(result).includes(ID), false);
  }
});

test("required CI covers blob candidates and background stays inactive", async () => {
  const read = file => readFile(new URL(file, import.meta.url), "utf8");
  const [source, ci, bg, shared, safari] = await Promise.all([
    read("../src/pdf-blob.js"), read("../../../.github/workflows/ci.yml"),
    read("../src/background.js"), read("../manifest.json"),
    read("../../safari/manifest.json")
  ]);
  assert.match(ci, /node --test tests\/pdf-blob\.test\.mjs/);
  assert.ok(bg.trimEnd().endsWith("void 0;"));
  for (const manifest of [JSON.parse(shared), JSON.parse(safari)]) {
    assert.deepEqual(manifest.host_permissions, []);
    assert.equal(manifest.permissions.includes("webNavigation"), false);
    assert.equal(manifest.permissions.includes("webRequest"), false);
  }
  for (const forbidden of ["addListener(", "fetch(", "XMLHttpRequest",
    "permissions.request", "connectNative(", "sendNativeMessage(",
    "downloads.open(", "window.open(", "scan-and-open", "console."]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
