import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  INTERCEPTED_PDF_SCANNER_TRANSFER_VERSION,
  INTERCEPTED_PDF_SCANNER_TRANSFER_FIELDS,
  describeInterceptedPdfScannerTransfer
} from "../src/intercepted-pdf-scanner-transfer.js";
import {
  MAX_EXPLICIT_PDF_DOWNLOAD_BYTES,
  MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES
} from "../src/explicit-pdf-download-size.js";

const plan = (changes = {}) => ({
  version: 1, browserId: "firefox", source: "response-stream",
  requestId: "request_123", captureId: "capture_456",
  tabId: 4, frameId: 0, maxBytes: 1024, ...changes
});
const describe = changes => describeInterceptedPdfScannerTransfer(plan(changes));
const ids = [
  "brave", "chrome", "chromium", "edge", "vivaldi",
  "opera", "arc", "firefox", "safari"
];
const read = path => readFile(new URL(path, import.meta.url), "utf8");

test("versioned exact-field transfer descriptor contains only bounded correlation metadata", () => {
  assert.equal(INTERCEPTED_PDF_SCANNER_TRANSFER_VERSION, 1);
  assert.deepEqual(INTERCEPTED_PDF_SCANNER_TRANSFER_FIELDS, [
    "version", "browserId", "source", "requestId", "captureId",
    "tabId", "frameId", "maxBytes"
  ]);
  assert.ok(Object.isFrozen(INTERCEPTED_PDF_SCANNER_TRANSFER_FIELDS));
  const result = describe();
  assert.equal(result.browserId, "firefox");
  assert.equal(result.requestId, "request_123");
  assert.equal(result.captureId, "capture_456");
  assert.equal(result.frameId, 0);
  assert.equal(result.maxBytes, 1024);
  assert.equal(result.maxChunkBytes, 1024);
  assert.ok(Object.isFrozen(result));
});

test("Firefox stream design requires an original-response hold and private native quarantine", () => {
  const result = describe();
  assert.equal(result.route, "native-private-quarantine-spool");
  assert.equal(result.status, "conditional-response-stream-design");
  assert.equal(result.requiresOriginalResponseHold, true);
  assert.match(result.steps.join(" "), /hold-original-response/);
  assert.match(result.steps.join(" "), /hard-size-and-time-bounds/);
  assert.match(result.steps.join(" "), /independent-clean-verdict/);
  assert.ok(Object.isFrozen(result.steps));
});

test("unsupported response stream routes cannot silently become downloads", () => {
  for (const browserId of ids.filter(x => x !== "firefox")) {
    assert.equal(describe({ browserId }), null, browserId);
  }
  assert.equal(describe({ browserId: "Firefox" }), null);
  assert.equal(describe({ browserId: "firefox ", source: "response-stream" }), null);
});

test("completed downloads use existing reviewed native handoff without pre-render promises", () => {
  for (const browserId of ids.filter(x => x !== "safari")) {
    const result = describe({
      browserId, source: "completed-download"
    });
    assert.equal(result.route, "existing-verified-completed-download-handoff", browserId);
    assert.equal(result.status, "post-download-scan-only");
    assert.equal(result.requiresOriginalResponseHold, false);
    assert.equal(result.preRenderGuaranteed, false);
    assert.match(result.steps.join(" "), /native-warning-state/);
    assert.ok(Object.isFrozen(result.steps));
  }
  assert.equal(describe({ browserId: "safari", source: "completed-download" }), null);
});

test("no plan alone can enable interception, scan bytes, or authorize a PDF open", () => {
  for (const source of ["response-stream", "completed-download"]) {
    const result = describe({ source });
    for (const key of [
      "scannerTransferReady", "automaticInterceptionEnabled",
      "preRenderGuaranteed", "scanVerified", "authorizesScan", "authorizesOpen"
    ]) assert.equal(result[key], false, key);
    for (const key of [
      "requiresTrustedNativeCoordinator", "requiresCompletePdfBytes",
      "requiresExactRequestAndFileIdentity", "requiresEffectiveRevocablePermissions",
      "requiresNativeQuarantineAndCleanVerdict"
    ]) assert.equal(result[key], true, key);
  }
});

test("reuses existing strict 100 MiB total and 8 MiB chunk caps", () => {
  assert.equal(MAX_EXPLICIT_PDF_DOWNLOAD_BYTES, 100 * 1024 * 1024);
  assert.equal(MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES, 8 * 1024 * 1024);
  assert.equal(describe({ maxBytes: MAX_EXPLICIT_PDF_DOWNLOAD_BYTES }).maxChunkBytes,
    MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES);
  for (const maxBytes of [0, -1, 1.1, NaN, Infinity, "1024",
    MAX_EXPLICIT_PDF_DOWNLOAD_BYTES + 1, Number.MAX_SAFE_INTEGER]) {
    assert.equal(describe({ maxBytes }), null, String(maxBytes));
  }
  assert.equal(describe({ maxBytes: 1 }).maxChunkBytes, 1);
});

test("untrusted or incomplete navigation and capture metadata fail closed", () => {
  for (const change of [
    { version: 2 }, { version: "1" },
    { source: "redirect" }, { source: "download-created" },
    { requestId: "" }, { requestId: "a".repeat(81) },
    { requestId: "path/to/pdf" }, { captureId: "request_123" },
    { captureId: "" }, { captureId: "https://host/a.pdf" },
    { tabId: -1 }, { tabId: 1.5 }, { tabId: "4" },
    { frameId: 1 }, { frameId: undefined },
    { browserId: null }, { browserId: {} }
  ]) assert.equal(describe(change), null, JSON.stringify(change));
});

test("extra browser URLs, filesystem paths and forged authorization claims are rejected", () => {
  for (const change of [
    { url: "https://secret.example/abc" }, { localPath: "/private/secret.pdf" },
    { verified: true }, { bytes: new Uint8Array([37, 80]) },
    { authorizesOpen: true }, { scanVerified: true },
    { userConsent: true }, { mime: "application/pdf" }
  ]) assert.equal(describe(change), null);
  assert.doesNotMatch(JSON.stringify(describe()), /https?:|\/private|file:|secret/);
});

test("getters, inherited fields, arrays and throwing Proxies cannot forge transfer plans", () => {
  const input = plan();
  assert.equal(describeInterceptedPdfScannerTransfer(Object.create(input)), null);
  assert.equal(describeInterceptedPdfScannerTransfer([input]), null);
  assert.equal(describeInterceptedPdfScannerTransfer(null), null);
  assert.equal(describeInterceptedPdfScannerTransfer({ ...input,
    get captureId() { throw Error("private path"); }
  }), null);
  assert.equal(describeInterceptedPdfScannerTransfer(
    new Proxy(input, { ownKeys() { throw Error("private URL"); } })
  ), null);
  assert.equal(describeInterceptedPdfScannerTransfer(
    new Proxy(input, { getPrototypeOf() { throw Error("private bytes"); } })
  ), null);
});

test("return values are detached, immutable and cannot be turned into authorizations", () => {
  const input = plan();
  const result = describeInterceptedPdfScannerTransfer(input);
  input.requestId = "changed";
  assert.equal(result.requestId, "request_123");
  assert.throws(() => { result.authorizesScan = true; }, TypeError);
  assert.throws(() => { result.steps.push("release-without-verdict"); }, TypeError);
});

test("shipped extension remains inactive with unchanged permissions and preferences", async () => {
  const [source, manifest, background, workflow, pkg] = await Promise.all([
    read("../src/intercepted-pdf-scanner-transfer.js"),
    read("../manifest.json").then(JSON.parse),
    read("../src/background.js"),
    read("../../../.github/workflows/ci.yml"),
    read("../package.json").then(JSON.parse)
  ]);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.match(background, /void 0;/);
  assert.match(workflow, /npm test/);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  for (const forbidden of [
    "sendNativeMessage(", "connectNative(", "permissions.request(",
    "downloads.download(", "downloads.open(", "window.open(",
    "fetch(", "node:fs", "localStorage", "sessionStorage",
    "addListener(", "navigator.userAgent", "globalThis."
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});

test("handoff documentation explains two routes and missing real browser-to-native bridge", async () => {
  const doc = await read("../src/intercepted-pdf-scanner-transfer.md");
  for (const word of [
    "opener-0784", "Firefox", "response filter", "native",
    "quarantine", "100 MiB", "8 MiB", "ClamAV", "signed",
    "redirect", "revocation", "timeout", "download",
    "no pre-render", "not implemented", "user preferences"
  ]) assert.ok(doc.toLowerCase().includes(word.toLowerCase()), word);
  assert.match(doc, /submitCompletedPdfDownloadToNative/);
  assert.match(doc, /copyExplicitPdfWithinSizeLimit/);
});
