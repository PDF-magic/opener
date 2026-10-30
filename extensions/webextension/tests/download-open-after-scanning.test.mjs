import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createDownloadOpenAfterScanningAction as createAction,
  OPEN_AFTER_SCANNING_LABEL
} from "../src/download-open-after-scanning.js";

function element(tagName = "div", ownerDocument = null) {
  const listeners = new Map();
  return {
    nodeType: 1, tagName, ownerDocument, hidden: false, disabled: false,
    type: null, textContent: "", children: [], attrs: new Map(),
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
    },
    removeEventListener(type, fn) { listeners.get(type)?.delete(fn); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attrs.set(name, value); },
    get listenerCount() {
      return [...listeners.values()].reduce((total, s) => total + s.size, 0);
    },
    fire(type, event = { isTrusted: true }) {
      return Promise.all([...listeners.get(type) ?? []].map(fn => fn(event)));
    }
  };
}
function root() {
  const doc = { createElement(tag) { return element(tag, doc); } };
  return element("section", doc);
}
function fixture(response = { accepted: true }) {
  const calls = [];
  const native = {
    nativeOpenAfterScanningReady: true,
    requestOpenAfterScanning(request) {
      calls.push(request);
      return Promise.resolve(response);
    }
  };
  const target = root();
  return { target, native, calls, action: createAction(target, native) };
}
const unavailable = {
  status: "unavailable", enabled: false, scanVerified: false, authorizesOpen: false
};
const offered = {
  status: "offered", enabled: true, scanVerified: false, authorizesOpen: false
};
const requested = {
  status: "request-submitted", enabled: false, scanVerified: false, authorizesOpen: false
};

test("explicitly offers a visible accessible Open After Scanning button", () => {
  const f = fixture();
  assert.deepEqual(f.action.state(), unavailable);
  assert.equal(f.target.hidden, true);
  assert.deepEqual(f.action.offer("scan_42"), offered);
  assert.equal(f.target.hidden, false);
  assert.equal(f.target.children.length, 2);
  const [button, help] = f.target.children;
  assert.equal(button.tagName, "button");
  assert.equal(button.type, "button");
  assert.equal(button.textContent, OPEN_AFTER_SCANNING_LABEL);
  assert.equal(button.disabled, false);
  assert.equal(help.attrs.get("role"), "status");
  assert.equal(help.attrs.get("aria-live"), "polite");
  assert.match(help.textContent, /native scanning, file integrity, quarantine/);
  assert.equal(f.calls.length, 0, "offering must not initiate a native request");
  assert.equal(Object.isFrozen(f.action), true);
});

test("trusted click requests a native future open by scan ID only", async () => {
  const f = fixture({ accepted: true, authorizesOpen: true, scanVerified: true });
  f.action.offer("scan_42");
  const [button, help] = f.target.children;
  await button.fire("click", { isTrusted: true });
  assert.deepEqual(f.calls, [{ scanRequestId: "scan_42" }]);
  assert.deepEqual(Object.keys(f.calls[0]), ["scanRequestId"]);
  assert.equal(Object.isFrozen(f.calls[0]), true);
  assert.equal(button.disabled, true);
  assert.deepEqual(f.action.state(), requested);
  assert.equal(Object.isFrozen(f.action.state()), true);
  assert.match(help.textContent, /native scanner must still approve opening/);
  assert.doesNotMatch(help.textContent, /opened successfully|safe to open/i);
  assert.equal(f.action.state().authorizesOpen, false);
  assert.equal(f.action.state().scanVerified, false);
});

test("synthetic programmatic clicks and non-click interactions never request opening", async () => {
  const f = fixture();
  f.action.offer("scan_42");
  const button = f.target.children[0];
  for (const event of [{ isTrusted: false }, {}, null, { isTrusted: "true" }]) {
    await button.fire("click", event);
  }
  await button.fire("mouseover", { isTrusted: true });
  assert.deepEqual(f.calls, []);
  assert.deepEqual(f.action.state(), offered);
  assert.equal(button.disabled, false);
});

test("synchronously disables the button and suppresses repeated clicks while native request is pending", async () => {
  const f = fixture();
  let release;
  f.native.requestOpenAfterScanning = (request) => {
    f.calls.push(request);
    return new Promise((resolve) => { release = resolve; });
  };
  f.action.offer("scan_42");
  const button = f.target.children[0];
  const first = button.fire("click", { isTrusted: true });
  assert.equal(button.disabled, true);
  assert.equal(f.action.state().status, "pending");
  await button.fire("click", { isTrusted: true });
  assert.equal(f.calls.length, 1);
  release({ accepted: true });
  await first;
  assert.deepEqual(f.action.state(), requested);
  await button.fire("click", { isTrusted: true });
  assert.equal(f.calls.length, 1);
});

test("native refusal and false or missing acceptance never authorize opening", async () => {
  for (const reply of [
    { accepted: false }, { accepted: "true" },
    { scanVerified: true }, { authorizesOpen: true },
    { opened: true }, null, undefined
  ]) {
    const f = fixture(reply);
    f.action.offer("scan_42");
    const [button, help] = f.target.children;
    await button.fire("click", { isTrusted: true });
    assert.deepEqual(f.action.state(), unavailable);
    assert.equal(button.disabled, true);
    assert.match(help.textContent, /unavailable/);
    assert.doesNotMatch(help.textContent, /private|opened successfully/i);
  }
});

test("missing readiness or trusted native coordinator prevents offering any action", () => {
  for (const native of [
    null, {}, { nativeOpenAfterScanningReady: true },
    { nativeOpenAfterScanningReady: false,
      requestOpenAfterScanning() { throw Error("must not call"); } },
    { nativeOpenAfterScanningReady: true,
      get requestOpenAfterScanning() { throw Error("private"); } },
    new Proxy({}, { getOwnPropertyDescriptor() { throw Error("private"); } })
  ]) {
    const target = root();
    const action = createAction(target, native);
    assert.deepEqual(action.offer("scan_42"), unavailable);
    assert.equal(target.hidden, true);
    assert.equal(target.children.length, 0);
  }
});

test("invalid and untrusted scan identifiers never make an action available", () => {
  const f = fixture();
  for (const id of [
    null, undefined, 42, {}, "", "../private", "scan/path",
    "scan:42", "scan 42", "scan\n42", "x".repeat(81)
  ]) {
    assert.deepEqual(f.action.offer(id), unavailable);
    assert.equal(f.target.hidden, true);
    assert.equal(f.calls.length, 0);
  }
});

test("a coordinator that becomes unavailable before click rejects without a native request", async () => {
  const f = fixture();
  f.action.offer("scan_42");
  const button = f.target.children[0];
  f.native.nativeOpenAfterScanningReady = false;
  await button.fire("click", { isTrusted: true });
  assert.deepEqual(f.calls, []);
  assert.deepEqual(f.action.state(), unavailable);
});

test("readiness lost after an asynchronous acknowledgment never becomes accepted", async () => {
  const f = fixture();
  let release;
  f.native.requestOpenAfterScanning = (request) => {
    f.calls.push(request);
    return new Promise(resolve => { release = resolve; });
  };
  f.action.offer("scan_42");
  const request = f.target.children[0].fire("click", { isTrusted: true });
  f.native.nativeOpenAfterScanningReady = false;
  release({ accepted: true });
  await request;
  assert.deepEqual(f.action.state(), unavailable);
});

test("native exceptions, promise rejections and non-Promise responses are private and fail closed", async () => {
  for (const send of [
    () => { throw Error("/private/download.pdf"); },
    () => Promise.reject(Error("https://private.invalid/document.pdf")),
    () => ({ accepted: true }),
    () => Promise.resolve({
      get accepted() { throw Error("secret"); }
    })
  ]) {
    const f = fixture();
    f.native.requestOpenAfterScanning = send;
    f.action.offer("scan_42");
    const help = f.target.children[1];
    await f.target.children[0].fire("click", { isTrusted: true });
    assert.deepEqual(f.action.state(), unavailable);
    assert.match(help.textContent, /unavailable/);
    assert.doesNotMatch(help.textContent, /private|secret|https:/);
  }
});

test("clear removes listeners and invalidates in-flight native acknowledgments", async () => {
  const f = fixture();
  let release;
  f.native.requestOpenAfterScanning = () =>
    new Promise(resolve => { release = resolve; });
  f.action.offer("scan_42");
  const button = f.target.children[0];
  const pending = button.fire("click", { isTrusted: true });
  f.action.clear();
  assert.equal(button.listenerCount, 0);
  release({ accepted: true });
  await pending;
  assert.deepEqual(f.action.state(), unavailable);
  assert.equal(f.target.hidden, true);
  assert.deepEqual(f.target.children, []);
});

test("changing active scan ID invalidates old buttons and stale native requests", async () => {
  const f = fixture();
  let release;
  f.native.requestOpenAfterScanning = request => {
    f.calls.push(request);
    if (f.calls.length === 1) return new Promise(resolve => { release = resolve; });
    return Promise.resolve({ accepted: true });
  };
  f.action.offer("scan_old");
  const old = f.target.children[0];
  const pending = old.fire("click", { isTrusted: true });
  assert.deepEqual(f.action.offer("scan_new"), offered);
  assert.equal(old.listenerCount, 0);
  release({ accepted: true });
  await pending;
  assert.deepEqual(f.action.state(), offered);
  await f.target.children[0].fire("click", { isTrusted: true });
  assert.deepEqual(f.calls, [
    { scanRequestId: "scan_old" },
    { scanRequestId: "scan_new" }
  ]);
  assert.deepEqual(f.action.state(), requested);
});

test("dispose unbinds the action, is idempotent and blocks subsequent offers", async () => {
  const f = fixture();
  f.action.offer("scan_42");
  const button = f.target.children[0];
  f.action.dispose();
  f.action.dispose();
  assert.equal(button.listenerCount, 0);
  assert.equal(f.target.hidden, true);
  assert.deepEqual(f.action.offer("scan_next"), unavailable);
  await button.fire("click", { isTrusted: true });
  assert.deepEqual(f.calls, []);
});

test("module has no startup, browser, native, filesystem or opening side effects", async () => {
  assert.throws(() => createAction({}, {}), TypeError);
  const source = await readFile(
    new URL("../src/download-open-after-scanning.js", import.meta.url), "utf8");
  const worker = await readFile(
    new URL("../src/background.js", import.meta.url), "utf8");
  const popup = await readFile(
    new URL("../src/popup.html", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.match(popup, /Not active/);
  assert.match(popup, /disabled aria-disabled="true"/);
  for (const forbidden of [
    "innerHTML", "document.write", "sendNativeMessage(", "connectNative(",
    "scan_and_open", "clamscan", "downloads.open(", "window.open(",
    "permissions.request(", "chrome.", "browser.", "storage.local", "fetch(",
    "node:fs"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
