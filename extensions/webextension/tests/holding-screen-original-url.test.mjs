import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createHoldingScreenOriginalUrl, UNKNOWN_HOLDING_ORIGINAL_URL
} from "../src/holding-screen-original-url.js";

const holdingId = "hold_17";
const original = "https://example.test/a%2Fb.pdf?signature=a%2Bb&token=private#page=2";
function element() {
  const attrs = new Map();
  return { id: "holdingScreenOriginalUrl", nodeType: 1, textContent: "",
    attrs, setAttribute(k, v) { attrs.set(k, v); } };
}
function fixture(reply = { holdingId, originalUrl: original }) {
  const target = element(), calls = [];
  const coordinator = {
    trustedHoldingScreenReady: true, selected: holdingId,
    readCurrentHoldingId() { return this.selected; },
    async readOriginalHoldingUrl(context) { calls.push(context); return reply; }
  };
  return { target, coordinator, calls,
    view: createHoldingScreenOriginalUrl(target, coordinator) };
}

test("starts unavailable without coordinator, never claims a verified scan", async () => {
  const target = element();
  const view = createHoldingScreenOriginalUrl(target);
  assert.equal(target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
  assert.equal(target.attrs.get("role"), "status");
  assert.equal((await view.show(holdingId)).authorizesOpen, false);
  assert.equal(target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
  assert.ok(Object.isFrozen(view));
});

test("preserves the original URL byte-for-byte, including signed query and fragment", async () => {
  const f = fixture();
  assert.deepEqual(await f.view.show(holdingId), {
    status: "displayed", displayed: true, authorizesScan: false, authorizesOpen: false
  });
  assert.deepEqual(f.calls, [{ holdingId }]);
  assert.equal(f.target.textContent, original);
  assert.equal(f.target.attrs.get("aria-live"), "polite");
});

test("never substitutes a redirect, referrer, or a different holding session", async () => {
  for (const reply of [
    { holdingId, finalUrl: "https://other.test/final.pdf" },
    { holdingId: "another", originalUrl: original },
    { holdingId, originalUrl: original, finalUrl: "https://other.test/final.pdf" },
    { holdingId, originalUrl: original, referrer: "https://other.test" }
  ]) {
    const f = fixture(reply);
    assert.equal((await f.view.show(holdingId)).displayed, false);
    assert.equal(f.target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
  }
});

test("rejects malformed, privileged and credential-bearing URLs", async () => {
  for (const url of [
    "", 1, null, "http://", "javascript:alert(1)", "file:///tmp/report.pdf",
    "blob:https://example.test/id", "data:application/pdf;base64,xx",
    "https://user:pass@example.test/x.pdf", "https://example.test/a b.pdf",
    "https://example.test/x.pdf\nInjected", "https://example.test/" + "x".repeat(8193)
  ]) {
    const f = fixture({ holdingId, originalUrl: url });
    assert.equal((await f.view.show(holdingId)).displayed, false);
    assert.equal(f.target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
  }
});

test("text display cannot create an executable link or interpret HTML", async () => {
  const url = "https://example.test/%3Cscript%3E.pdf?x=%3Cimg%20src=x%3E";
  const f = fixture({ holdingId, originalUrl: url });
  assert.equal((await f.view.show(holdingId)).displayed, true);
  assert.equal(f.target.textContent, url);
  assert.equal(Object.hasOwn(f.target, "innerHTML"), false);
  assert.equal(Object.hasOwn(f.target, "href"), false);
});

test("stale holds, missing coordinator grants, and invalid IDs are denied", async () => {
  const f = fixture();
  for (const id of ["", "bad id", null, {}, "x".repeat(81)]) {
    assert.equal((await f.view.show(id)).displayed, false);
  }
  f.coordinator.trustedHoldingScreenReady = false;
  assert.equal((await f.view.show(holdingId)).displayed, false);
  f.coordinator.trustedHoldingScreenReady = true;
  f.coordinator.selected = "another";
  assert.equal((await f.view.show(holdingId)).displayed, false);
  assert.equal(f.calls.length, 0);
});

test("in-flight reads cannot resurrect URLs after hold change, clear or disposal", async () => {
  const f = fixture();
  let resolve;
  f.coordinator.readOriginalHoldingUrl = () => new Promise(r => { resolve = r; });
  const pending = f.view.show(holdingId);
  f.coordinator.selected = "other";
  resolve({ holdingId, originalUrl: original });
  assert.equal((await pending).displayed, false);
  assert.equal(f.target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
  f.coordinator.selected = holdingId;
  const second = f.view.show(holdingId);
  f.view.clear();
  resolve({ holdingId, originalUrl: original });
  assert.equal((await second).displayed, false);
  f.view.dispose();
  assert.equal((await f.view.show(holdingId)).displayed, false);
});

test("each new selection erases the prior URL even when subsequent display fails", async () => {
  const f = fixture();
  assert.equal((await f.view.show(holdingId)).displayed, true);
  assert.equal((await f.view.show("different")).displayed, false);
  assert.equal(f.target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
  assert.equal((await f.view.show(holdingId)).displayed, true);
  f.view.clear();
  assert.equal(f.target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
});

test("forged records, getters, proxies and exceptions do not expose URL data", async () => {
  const getter = { holdingId, originalUrl: original };
  Object.defineProperty(getter, "originalUrl", { get() { throw Error(original); } });
  for (const reply of [
    getter, Object.create({ holdingId, originalUrl: original }),
    new Proxy({}, { ownKeys() { throw Error(original); } }),
    [holdingId, original]
  ]) {
    const f = fixture(reply);
    assert.equal((await f.view.show(holdingId)).displayed, false);
    assert.equal(f.target.textContent, UNKNOWN_HOLDING_ORIGINAL_URL);
  }
  const f = fixture();
  f.coordinator.readOriginalHoldingUrl = () => { throw Error(original); };
  assert.equal((await f.view.show(holdingId)).displayed, false);
});

test("CI verifies passive behavior without browser permission or scanner changes", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, doc, background, manifest, safari, ci, pkg] = await Promise.all([
    read("../src/holding-screen-original-url.js"),
    read("../src/holding-screen-original-url.md"),
    read("../src/background.js"),
    read("../manifest.json").then(JSON.parse),
    read("../../safari/manifest.json").then(JSON.parse),
    read("../../../.github/workflows/ci.yml"),
    read("../package.json").then(JSON.parse)
  ]);
  assert.match(doc, /opener-0787/);
  assert.match(doc, /opener-0785/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(safari.host_permissions, []);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /node --test tests\/holding-screen-original-url\.test\.mjs/);
  for (const forbidden of [
    "innerHTML", "outerHTML", "window.open", "location.href", "localStorage",
    "sessionStorage", "console.", "fetch(", "chrome.", "browser.",
    "addListener(", "sendNativeMessage(", "connectNative(", "downloads.open("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
