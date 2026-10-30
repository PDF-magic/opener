import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  ORIGINAL_PAGE_PRESERVATION_POLICY,
  createExplicitPdfOriginalPagePreservation
} from "../src/explicit-pdf-original-page.js";

const request = (patch = {}) => ({
  version: 1, requestId: "attempt_1", source: "pdf-link",
  tabId: 17, frameId: 0, selectionId: "selected_1",
  userInitiated: true, ...patch
});
const page = (patch = {}) => ({
  requestId: "attempt_1", tabId: 17, frameId: 0,
  selectionId: "selected_1", pageId: "original_8",
  documentRevision: 32, pageKind: "html-page",
  verified: true, permissionGranted: true, ...patch
});
function fixture({
  read = () => page(), submit = async () => ({ accepted: true }),
  ready = true
} = {}) {
  const calls = [];
  const coordinator = {
    originalPagePreservationReady: ready,
    readVerifiedOriginalPage(reference) {
      calls.push(["read", reference]);
      return read(reference);
    },
    requestPdfScanWithoutNavigation(reference) {
      calls.push(["submit", reference]);
      return submit(reference);
    }
  };
  return {
    calls, coordinator,
    keeper: createExplicitPdfOriginalPagePreservation(coordinator)
  };
}
function safe(result) {
  assert.equal(Object.isFrozen(result), true);
  assert.equal(result.navigationRequested, false);
  assert.equal(result.scanVerified, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(result),
    /https?:|token|filename|original_8|selected_1|attempt_1/i);
}

test("preserves the original HTML page while submitting a non-navigating scan request", async () => {
  const f = fixture();
  assert.equal(ORIGINAL_PAGE_PRESERVATION_POLICY, "leave-original-tab-open");
  assert.equal(f.calls.length, 0);
  assert.equal(Object.isFrozen(f.keeper), true);
  const pending = f.keeper.requestScan(request());
  assert.deepEqual(f.calls.map(x => x[0]), ["read", "submit"]);
  const result = await pending;
  assert.deepEqual(result, {
    status: "request-submitted",
    originalPageApplicable: true,
    originalPagePreserved: true,
    navigationRequested: false,
    scanVerified: false, authorizesScan: false, authorizesOpen: false
  });
  safe(result);
  assert.deepEqual(f.calls.map(x => x[0]), ["read", "submit", "read"]);
  assert.ok(Object.isFrozen(f.calls[0][1]));
  assert.ok(Object.isFrozen(f.calls[1][1]));
  assert.deepEqual(f.calls[1][1], {
    requestId: "attempt_1", source: "pdf-link",
    tabId: 17, frameId: 0, selectionId: "selected_1",
    pageId: "original_8", documentRevision: 32,
    preservationPolicy: "leave-original-tab-open"
  });
  assert.equal(Object.hasOwn(f.calls[1][1], "url"), false);
});

test("embedded iframe PDFs preserve their original top-level webpage", async () => {
  const f = fixture({ read: () => page({ frameId: 3 }) });
  const result = await f.keeper.requestScan(request({
    source: "embedded-pdf", frameId: 3
  }));
  assert.equal(result.status, "request-submitted");
  assert.equal(result.originalPagePreserved, true);
  assert.equal(f.calls[1][1].tabId, 17);
  assert.equal(f.calls[1][1].frameId, 3);
  safe(result);
});

test("toolbar on HTML pages preserves the page; standalone PDF viewer is not applicable", async () => {
  const html = fixture();
  const htmlResult = await html.keeper.requestScan(request({
    source: "toolbar", frameId: 0
  }));
  assert.equal(htmlResult.originalPageApplicable, true);
  assert.equal(htmlResult.originalPagePreserved, true);
  const viewer = fixture({ read: () => page({ pageKind: "pdf-viewer" }) });
  const view = await viewer.keeper.requestScan(request({
    source: "toolbar", frameId: 0
  }));
  assert.equal(view.status, "request-submitted");
  assert.equal(view.originalPageApplicable, false);
  assert.equal(view.originalPagePreserved, false);
  assert.equal(view.navigationRequested, false);
  safe(view);
});

test("never treats the PDF viewer as an original HTML page for links or embeds", async () => {
  for (const source of ["pdf-link", "embedded-pdf"]) {
    const f = fixture({ read: () => page({ pageKind: "pdf-viewer" }) });
    assert.equal((await f.keeper.requestScan(request({ source }))).status,
      "unavailable");
    assert.deepEqual(f.calls.map(x => x[0]), ["read"]);
  }
});

test("invalid intent, unsolicited metadata, and forged gestures do not submit", async () => {
  for (const invalid of [
    undefined, null, {}, { ...request(), url: "https://host.test/?secret" },
    request({ userInitiated: false }), request({ userInitiated: "true" }),
    request({ selectionId: "/private/report.pdf" }),
    request({ requestId: "../report" }),
    request({ frameId: -1 }), request({ source: "download" }),
    request({ scanVerified: true }),
    request({ source: "toolbar", frameId: 7 })
  ]) {
    const f = fixture();
    const outcome = await f.keeper.requestScan(invalid);
    assert.equal(outcome.status, "not-requested");
    safe(outcome);
    assert.deepEqual(f.calls, []);
  }
});

test("requires a separately verified coordinator and no side effects without it", async () => {
  const absent = createExplicitPdfOriginalPagePreservation();
  const result = await absent.requestScan(request());
  assert.equal(result.status, "unavailable");
  safe(result);
  const disabled = fixture({ ready: false });
  assert.equal((await disabled.keeper.requestScan(request())).status, "unavailable");
  assert.deepEqual(disabled.calls, []);
  for (const key of [
    "readVerifiedOriginalPage", "requestPdfScanWithoutNavigation"
  ]) {
    const f = fixture();
    f.coordinator[key] = undefined;
    assert.equal((await f.keeper.requestScan(request())).status, "unavailable");
    assert.deepEqual(f.calls, []);
  }
});

test("unverified, stale or mismatched original document evidence cannot submit", async () => {
  for (const changed of [
    { requestId: "other" }, { tabId: 18 }, { frameId: 2 },
    { selectionId: "selected_2" }, { pageId: "" },
    { pageId: "/Users/private" }, { pageId: "attempt_1" },
    { pageId: "selected_1" }, { documentRevision: -1 },
    { documentRevision: 1.5 }, { documentRevision: "32" },
    { pageKind: "popup" }, { verified: false },
    { verified: "true" }, { permissionGranted: false },
    { permissionGranted: "true" }, { url: "https://host.test?secret" },
    { cookie: "token" }, { authorizesOpen: true }
  ]) {
    const f = fixture({ read: () => page(changed) });
    assert.equal((await f.keeper.requestScan(request())).status, "unavailable",
      JSON.stringify(changed));
    assert.deepEqual(f.calls.map(x => x[0]), ["read"]);
  }
});

test("page navigation, reload, and tab replacement during async submission fail closed", async () => {
  for (const changed of [
    { pageId: "other_1" }, { documentRevision: 33 },
    { tabId: 18 }, { selectionId: "other_selection" },
    { pageKind: "pdf-viewer" }, { verified: false },
    { permissionGranted: false }
  ]) {
    let reads = 0;
    const f = fixture({
      read: () => page(++reads === 1 ? {} : changed)
    });
    const outcome = await f.keeper.requestScan(request());
    assert.equal(outcome.status, "unavailable");
    assert.equal(outcome.originalPagePreserved, false);
    safe(outcome);
    assert.deepEqual(f.calls.map(x => x[0]), ["read", "submit", "read"]);
  }
});

test("revoked coordinator readiness or swapped methods invalidate in-flight requests", async () => {
  for (const mutate of [
    f => { f.coordinator.originalPagePreservationReady = false; },
    f => { f.coordinator.readVerifiedOriginalPage = () => page(); },
    f => { f.coordinator.requestPdfScanWithoutNavigation = async () =>
      ({ accepted: true }); }
  ]) {
    let resume;
    const waiting = new Promise(resolve => { resume = resolve; });
    const f = fixture({ submit: () => waiting });
    const pending = f.keeper.requestScan(request());
    mutate(f);
    resume({ accepted: true });
    const outcome = await pending;
    assert.equal(outcome.status, "unavailable");
    assert.deepEqual(f.calls.map(x => x[0]), ["read", "submit"]);
    safe(outcome);
  }
});

test("a failed, malformed, or forged acknowledgment never claims preservation", async () => {
  for (const submit of [
    async () => ({ accepted: false }),
    async () => ({ accepted: "true" }),
    async () => ({ accepted: true, scanVerified: true }),
    async () => ({ accepted: true, navigationRequested: true }),
    async () => null, async () => true,
    () => ({ accepted: true }),
    () => undefined,
    async () => { throw Error("https://host.test/?token=secret"); }
  ]) {
    const f = fixture({ submit });
    const outcome = await f.keeper.requestScan(request());
    assert.equal(outcome.status, "unavailable");
    safe(outcome);
    assert.deepEqual(f.calls.map(x => x[0]), ["read", "submit"]);
    assert.equal((await f.keeper.requestScan(request())).status, "duplicate");
  }
});

test("duplicates and concurrent gestures never initiate another scan", async () => {
  let resume;
  const waiting = new Promise(resolve => { resume = resolve; });
  const f = fixture({ submit: () => waiting });
  const first = f.keeper.requestScan(request());
  const second = await f.keeper.requestScan(request());
  assert.equal(second.status, "duplicate");
  resume({ accepted: true });
  assert.equal((await first).status, "request-submitted");
  assert.equal((await f.keeper.requestScan(request())).status, "duplicate");
  assert.equal(f.calls.filter(x => x[0] === "submit").length, 1);
});

test("disposal prevents late results from claiming preserved access", async () => {
  let resume;
  const waiting = new Promise(resolve => { resume = resolve; });
  const f = fixture({ submit: () => waiting });
  const first = f.keeper.requestScan(request());
  assert.equal(f.keeper.dispose().status, "ended");
  resume({ accepted: true });
  assert.equal((await first).status, "unavailable");
  assert.equal((await f.keeper.requestScan(request({
    requestId: "attempt_2"
  }))).status, "ended");
  assert.equal(f.keeper.dispose().status, "ended");
});

test("hostile accessors, symbols, proxies and inherited snapshots fail closed", async () => {
  let getterCalls = 0;
  const accessor = page();
  Object.defineProperty(accessor, "pageId", { get() {
    getterCalls++;
    return "original_8";
  } });
  const symbol = page();
  symbol[Symbol("url")] = "https://secret.test";
  const inherited = Object.create(page());
  const proxy = new Proxy(page(), { ownKeys() { throw Error("private"); } });
  for (const invalid of [accessor, symbol, inherited, proxy,
    [], null, Promise.resolve(page())]) {
    const f = fixture({ read: () => invalid });
    assert.equal((await f.keeper.requestScan(request())).status, "unavailable");
    assert.equal(f.calls.some(x => x[0] === "submit"), false);
  }
  assert.equal(getterCalls, 0);
  const f = fixture({ read: () => Object.assign(Object.create(null), page()) });
  assert.equal((await f.keeper.requestScan(request())).status, "request-submitted");
});

test("bounded request IDs fail closed without unbounded replay caching", async () => {
  const f = fixture({ read: ref => page({ requestId: ref.requestId }) });
  for (let i = 0; i < 128; i++) {
    assert.equal((await f.keeper.requestScan(request({
      requestId: "attempt_" + i
    }))).status, "request-submitted");
  }
  assert.equal((await f.keeper.requestScan(request({
    requestId: "attempt_overflow"
  }))).status, "unavailable");
  assert.equal(f.calls.filter(x => x[0] === "submit").length, 128);
});

test("does not navigate the original tab, use browser privileges, or bypass the scanner", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, acquisition, background, manifest, pkg, ci] = await Promise.all([
    read("../src/explicit-pdf-original-page.js"),
    read("../src/explicit-pdf-download-acquisition.js"),
    read("../src/background.js"), read("../manifest.json"),
    read("../package.json"), read("../../../.github/workflows/ci.yml")
  ]);
  assert.deepEqual(JSON.parse(manifest).permissions, []);
  assert.deepEqual(JSON.parse(manifest).host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(pkg).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  assert.match(acquisition, /saveAs: true, conflictAction: "uniquify"/);
  assert.equal(acquisition.includes("tabs.update("), false);
  assert.equal(acquisition.includes("tabs.remove("), false);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "fetch(", "XMLHttpRequest",
    "downloads.download(", "downloads.open(", "tabs.update(", "tabs.remove(",
    "tabs.create(", "window.open(", "permissions.request(",
    "connectNative(", "sendNativeMessage(", "location.href",
    "localStorage", "sessionStorage", "node:fs", "scan-and-open",
    "clamscan("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
