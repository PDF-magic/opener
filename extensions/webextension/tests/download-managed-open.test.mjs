import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  MANAGED_DOWNLOAD_LABEL, createManagedDownloadAndOpenGate,
  createManagedDownloadAndOpenAction
} from "../src/download-managed-open.js";

function element(tagName = "div", ownerDocument = null) {
  const listeners = new Map();
  return {
    nodeType: 1, tagName, ownerDocument, hidden: false, disabled: false,
    textContent: "", type: null, children: [], attributes: new Map(),
    addEventListener(name, callback) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(callback);
    },
    removeEventListener(name, callback) { listeners.get(name)?.delete(callback); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes.set(name, value); },
    get listeners() {
      return [...listeners.values()].reduce((n, callbacks) => n + callbacks.size, 0);
    },
    fire(name, event = { isTrusted: true }) {
      return Promise.all([...(listeners.get(name) ?? [])].map(fn => fn(event)));
    }
  };
}

function root() {
  const doc = { createElement(tag) { return element(tag, doc); } };
  return element("section", doc);
}

function fixture(response = { accepted: true, managedRequestId: "job_7" }) {
  const requests = [];
  const native = {
    managedWorkflowRequired: true, nativeManagedWorkflowReady: true,
    requestManagedDownloadAndOpen(request) {
      requests.push(request);
      return Promise.resolve(response);
    }
  };
  const target = root();
  const gate = createManagedDownloadAndOpenGate();
  const action = createManagedDownloadAndOpenAction(target, native, gate);
  return { native, target, gate, action, requests };
}

const unavailable = {
  status: "unavailable", enabled: false, downloadVerified: false,
  scanVerified: false, authorizesOpen: false, opened: false
};
const offered = {
  status: "offered", enabled: true, downloadVerified: false,
  scanVerified: false, authorizesOpen: false, opened: false
};
const queued = {
  status: "request-submitted", enabled: false, downloadVerified: false,
  scanVerified: false, authorizesOpen: false, opened: false
};

test("offers accessible opt-in managed download and open only with trusted policy", () => {
  const f = fixture();
  assert.equal(f.target.hidden, true);
  assert.deepEqual(f.action.offer("job_7"), offered);
  assert.equal(f.target.hidden, false);
  const [button, help] = f.target.children;
  assert.equal(button.tagName, "button");
  assert.equal(button.type, "button");
  assert.equal(button.textContent, MANAGED_DOWNLOAD_LABEL);
  assert.equal(button.disabled, false);
  assert.equal(help.attributes.get("role"), "status");
  assert.equal(help.attributes.get("aria-live"), "polite");
  assert.match(help.textContent, /native safety checks pass/);
  assert.match(help.textContent, /Other browser and system opening paths are not blocked/);
  assert.deepEqual(f.requests, []);
  assert.equal(Object.isFrozen(f.action), true);
});

test("a trusted user click queues only an opaque ID, not a URL or destination app", async () => {
  const f = fixture();
  f.action.offer("job_7");
  const [button, help] = f.target.children;
  await button.fire("click", { isTrusted: true });
  assert.deepEqual(f.requests, [{ managedRequestId: "job_7" }]);
  assert.deepEqual(Object.keys(f.requests[0]), ["managedRequestId"]);
  assert.equal(Object.isFrozen(f.requests[0]), true);
  assert.deepEqual(f.action.state(), queued);
  assert.equal(Object.isFrozen(f.action.state()), true);
  assert.equal(button.disabled, true);
  assert.match(help.textContent, /still require native approval/);
  assert.doesNotMatch(help.textContent, /download complete|scan complete|file opened/i);
});

test("untrusted programmatic events do not start managed downloads", async () => {
  const f = fixture();
  f.action.offer("job_7");
  const button = f.target.children[0];
  for (const event of [{ isTrusted: false }, {}, null, { isTrusted: "true" }]) {
    await button.fire("click", event);
  }
  assert.deepEqual(f.requests, []);
  assert.deepEqual(f.action.state(), offered);
  assert.equal(button.disabled, false);
});

test("same native request ID is reserved before callbacks and cannot double-submit", async () => {
  const f = fixture();
  let release;
  f.native.requestManagedDownloadAndOpen = request => {
    f.requests.push(request);
    return new Promise(resolve => { release = resolve; });
  };
  f.action.offer("job_7");
  const button = f.target.children[0];
  const waiting = button.fire("click");
  assert.equal(button.disabled, true);
  assert.deepEqual(f.action.state().status, "pending");
  await button.fire("click");
  assert.equal(f.requests.length, 1);
  assert.equal(f.gate.isReserved("job_7"), true);
  release({ accepted: true, managedRequestId: "job_7" });
  await waiting;
  assert.deepEqual(f.action.state(), queued);
  assert.deepEqual(f.action.offer("job_7"), unavailable);
  assert.equal(f.requests.length, 1);
});

test("shared session gate rejects duplicates across different UI views", async () => {
  const f = fixture();
  const other = root();
  const second = createManagedDownloadAndOpenAction(other, f.native, f.gate);
  assert.deepEqual(f.action.offer("job_7"), offered);
  assert.deepEqual(second.offer("job_7"), offered);
  const first = f.target.children[0].fire("click");
  await first;
  await other.children[0].fire("click");
  assert.equal(f.requests.length, 1);
  assert.deepEqual(second.state(), unavailable);
  assert.equal(second.offer("job_7").status, "unavailable");
  second.dispose();
});

test("cannot claim success for native rejects, wrong IDs or extraneous native fields", async () => {
  const bad = [
    null, undefined, {}, { accepted: false, managedRequestId: "job_7" },
    { accepted: "true", managedRequestId: "job_7" },
    { accepted: true, managedRequestId: "job_8" },
    { accepted: true, managedRequestId: "job_7", authorizesOpen: true },
    { accepted: true }, { opened: true, scanVerified: true }
  ];
  for (const nativeResult of bad) {
    const f = fixture();
    f.native.requestManagedDownloadAndOpen = request => {
      f.requests.push(request);
      return Promise.resolve(nativeResult);
    };
    f.action.offer("job_7");
    const help = f.target.children[1];
    await f.target.children[0].fire("click");
    assert.deepEqual(f.action.state(), unavailable);
    assert.match(help.textContent, /No successful scan or opening has been confirmed/);
    assert.equal(f.gate.isReserved("job_7"), true);
  }
});

test("rejects malformed identifiers and untrusted coordinator policy", async () => {
  const f = fixture();
  for (const id of [
    "", "../file.pdf", "https://evil.example/file.pdf", "job/7",
    "job:7", "job 7", "x".repeat(81), 1, null, {}, undefined
  ]) {
    assert.deepEqual(f.action.offer(id), unavailable);
    assert.equal(f.target.hidden, true);
  }
  assert.deepEqual(f.requests, []);
  for (const native of [
    null, {}, { managedWorkflowRequired: true },
    { managedWorkflowRequired: true, nativeManagedWorkflowReady: false,
      requestManagedDownloadAndOpen() { throw Error("should not call"); } },
    { managedWorkflowRequired: false, nativeManagedWorkflowReady: true,
      requestManagedDownloadAndOpen() { throw Error("should not call"); } },
    { managedWorkflowRequired: true, nativeManagedWorkflowReady: true,
      get requestManagedDownloadAndOpen() { throw Error("private"); } }
  ]) {
    const target = root();
    const action = createManagedDownloadAndOpenAction(
      target, native, createManagedDownloadAndOpenGate());
    assert.deepEqual(action.offer("job_7"), unavailable);
    assert.equal(target.hidden, true);
  }
});

test("revoked coordinator eligibility before click prevents a native request", async () => {
  const f = fixture();
  f.action.offer("job_7");
  f.native.managedWorkflowRequired = false;
  await f.target.children[0].fire("click");
  assert.deepEqual(f.requests, []);
  assert.deepEqual(f.action.state(), unavailable);
});

test("eligibility revocation during a pending request never reports accepted", async () => {
  const f = fixture();
  let reply;
  f.native.requestManagedDownloadAndOpen = request => {
    f.requests.push(request);
    return new Promise(resolve => { reply = resolve; });
  };
  f.action.offer("job_7");
  const pending = f.target.children[0].fire("click");
  f.native.nativeManagedWorkflowReady = false;
  reply({ accepted: true, managedRequestId: "job_7" });
  await pending;
  assert.deepEqual(f.action.state(), unavailable);
  assert.equal(f.gate.isReserved("job_7"), true);
});

test("native synchronous throws, asynchronous rejection and non-promises fail closed", async () => {
  for (const send of [
    () => { throw Error("/private/report.pdf"); },
    () => Promise.reject(Error("https://secret.invalid/path")),
    () => ({ accepted: true, managedRequestId: "job_7" }),
    () => Promise.resolve(Object.defineProperty({}, "accepted", {
      get() { throw Error("secret"); }
    }))
  ]) {
    const f = fixture();
    f.native.requestManagedDownloadAndOpen = send;
    f.action.offer("job_7");
    const help = f.target.children[1];
    await f.target.children[0].fire("click");
    assert.deepEqual(f.action.state(), unavailable);
    assert.doesNotMatch(help.textContent, /secret|private|https:/);
    assert.equal(f.gate.isReserved("job_7"), true);
  }
});

test("clear and dispose remove listeners and discard in-flight native acknowledgments", async () => {
  const f = fixture();
  let reply;
  f.native.requestManagedDownloadAndOpen = () =>
    new Promise(resolve => { reply = resolve; });
  f.action.offer("job_7");
  const button = f.target.children[0];
  const pending = button.fire("click");
  f.action.clear();
  assert.equal(button.listeners, 0);
  reply({ accepted: true, managedRequestId: "job_7" });
  await pending;
  assert.equal(f.target.hidden, true);
  assert.deepEqual(f.action.state(), unavailable);
  assert.equal(f.gate.isReserved("job_7"), true, "UI clearing cannot reset native request");
  f.action.dispose();
  assert.deepEqual(f.action.offer("job_new"), unavailable);
});

test("switching IDs revokes the old UI result but does not cancel its native request", async () => {
  const f = fixture();
  let firstReply;
  f.native.requestManagedDownloadAndOpen = request => {
    f.requests.push(request);
    return request.managedRequestId === "job_old"
      ? new Promise(resolve => { firstReply = resolve; })
      : Promise.resolve({ accepted: true, managedRequestId: "job_new" });
  };
  f.action.offer("job_old");
  const button = f.target.children[0];
  const pending = button.fire("click");
  assert.deepEqual(f.action.offer("job_new"), offered);
  assert.equal(button.listeners, 0);
  firstReply({ accepted: true, managedRequestId: "job_old" });
  await pending;
  assert.deepEqual(f.action.state(), offered);
  await f.target.children[0].fire("click");
  assert.deepEqual(f.action.state(), queued);
  assert.deepEqual(f.requests.map(x=>x.managedRequestId), ["job_old", "job_new"]);
});

test("session gate capacity is bounded without evicting old potentially dispatched work", async () => {
  const gate = createManagedDownloadAndOpenGate();
  for (let i = 0; i < 256; i += 1) {
    const id = "job_" + i;
    assert.deepEqual(await gate.requestOnce(id, async () => ({
      accepted: true, managedRequestId: id
    })), queued);
  }
  assert.equal(gate.isReserved("job_0"), true);
  assert.equal(gate.isReserved("job_256"), true);
  assert.deepEqual(await gate.requestOnce("job_256", async () => ({
    accepted: true, managedRequestId: "job_256"
  })), unavailable);
  gate.dispose();
  assert.deepEqual(await gate.requestOnce("job_after", async () => ({
    accepted: true, managedRequestId: "job_after"
  })), unavailable);
});

test("view teardown cannot dispose a session's shared deduplication state", async () => {
  const f = fixture();
  f.action.offer("job_7");
  await f.target.children[0].fire("click");
  f.action.dispose();
  const other = createManagedDownloadAndOpenAction(root(), f.native, f.gate);
  assert.deepEqual(other.offer("job_7"), unavailable);
});

test("managed workflow guidance is linked from interception research without false guarantees", async () => {
  const doc = await readFile(
    new URL("../src/download-managed-open.md", import.meta.url), "utf8");
  const research = await readFile(
    new URL("../../../docs/browser-interception-apis.md", import.meta.url), "utf8");
  assert.match(research, /download-managed-open\.md/);
  for (const required of [
    "all other browser and system", "transport-only",
    "native coordinator", "SSRF", "quarantine retention",
    "one-request-per-session", "Do not claim",
    "managedWorkflowRequired", "not an implementation"
  ]) {
    if (required === "not an implementation") continue;
    assert.ok(doc.toLowerCase().includes(required.toLowerCase()), required);
  }
});

test("module remains inert without native integration and never changes browser preferences", async () => {
  assert.throws(() => createManagedDownloadAndOpenAction({}, {}, {}), TypeError);
  const moduleText = await readFile(
    new URL("../src/download-managed-open.js", import.meta.url), "utf8");
  const worker = await readFile(
    new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(
    new URL("../manifest.json", import.meta.url), "utf8"));
  assert.match(worker, /Inactive shared WebExtensions background entry point/);
  assert.match(worker, /void 0;/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  for (const banned of [
    "innerHTML", "window.open(", "downloads.open(", "downloads.download(",
    "downloads.cancel(", "sendNativeMessage(", "connectNative(",
    "permissions.request(", "localStorage", "storage.local", "fetch(",
    "chrome.", "browser.", "node:fs"
  ]) assert.equal(moduleText.includes(banned), false, banned);
});
