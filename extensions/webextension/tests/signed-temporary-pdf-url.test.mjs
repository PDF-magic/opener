import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  SIGNED_PDF_URL_MIN_REMAINING_MS,
  createSignedTemporaryPdfUrlHandoff
} from "../src/signed-temporary-pdf-url.js";

const signedUrl =
  "https://cdn.example.test/report.pdf?X-Amz-Signature=Ab%2Fc" +
  "&X-Amz-Date=20261030T230000Z&X-Amz-Signature=second";
const request = (patch = {}) => ({
  version: 1, requestId: "attempt_1", source: "pdf-link",
  tabId: 10, frameId: 2, selectionId: "selection_1",
  userInitiated: true, ...patch
});
// Keep both trusted selection reads at the exact same default expiry.
// A fresh Date.now() on each read makes this consent test race at ms boundaries.
const stableExpiryMs = Date.now() + 300_000;
const selected = (patch = {}) => ({
  requestId: "attempt_1", tabId: 10, frameId: 2,
  selectionId: "selection_1", resourceId: "signed_resource_1",
  url: signedUrl, siteOrigin: "https://cdn.example.test",
  expiresAtMs: stableExpiryMs,
  verified: true, signatureVerified: true, permissionGranted: true,
  ...patch
});
function fixture({ read = () => selected(), consume = async () => true,
  submit = async () => ({ accepted: true }), ready = true } = {}) {
  const events = [];
  const coordinator = {
    signedTemporaryPdfReady: ready,
    readVerifiedSignedPdfSelection(reference) {
      events.push(["read", reference]);
      return read(reference);
    },
    consumeVerifiedSignedPdfConsent(reference) {
      events.push(["consent", reference]);
      return consume(reference);
    },
    handoffVerifiedSignedPdfDownload(reference) {
      events.push(["handoff", reference]);
      return submit(reference);
    }
  };
  return { events, coordinator,
    guard: createSignedTemporaryPdfUrlHandoff(coordinator) };
}
function safe(outcome) {
  assert.equal(Object.isFrozen(outcome), true);
  assert.equal(outcome.scanVerified, false);
  assert.equal(outcome.authorizesScan, false);
  assert.equal(outcome.authorizesOpen, false);
  assert.equal(outcome.automaticallyRetry, false);
  assert.doesNotMatch(JSON.stringify(outcome), /X-Amz|Signature|Ab%2F|report.pdf|cdn.example/);
}

test("signed temporary URL handoff is inert until a valid explicit request", async () => {
  assert.equal(SIGNED_PDF_URL_MIN_REMAINING_MS, 30_000);
  const { guard, events } = fixture();
  assert.ok(Object.isFrozen(guard));
  assert.deepEqual(events, []);
  for (const invalid of [
    null, {}, undefined, request({ userInitiated: false }),
    request({ userInitiated: "true" }),
    request({ selectionId: "https://example.test/report.pdf" }),
    request({ requestId: "../private" }),
    request({ url: signedUrl })
  ]) {
    const outcome = await guard.handoff(invalid);
    assert.equal(outcome.status, "not-requested");
    safe(outcome);
  }
  assert.deepEqual(events, []);
});

test("preserves signature parameters byte-for-byte only for the trusted download callback", async () => {
  const { guard, events } = fixture();
  const pending = guard.handoff(request());
  assert.deepEqual(events.map(x => x[0]), ["read", "consent"]);
  const outcome = await pending;
  assert.equal(outcome.status, "handed-off");
  assert.equal(outcome.handoffRequested, true);
  safe(outcome);
  assert.deepEqual(events.map(x => x[0]), ["read", "consent", "read", "handoff"]);
  assert.equal(events[3][1].url, signedUrl);
  assert.ok(Object.isFrozen(events[3][1]));
  assert.deepEqual(Object.keys(events[3][1]).sort(), [
    "frameId", "requestId", "resourceId", "selectionId",
    "siteOrigin", "source", "tabId", "url"
  ]);
  assert.doesNotMatch(JSON.stringify(events[1][1]), /Signature|report\.pdf|Ab%2F/);
});

test("does not rewrite repeated query keys, percent-encoding or signed path components", async () => {
  const samples = [
    "https://files.example.test/protected%2Freport.pdf?sig=a%2Bb%3D%3D&sig=second",
    "https://download.example.test/Azure/blob.pdf?sv=2024-10-01&sig=AB%2Bcd%2F%3D",
    "https://cdn.example.test/signed-token-ABC/statement.pdf?nonce=one&nonce=two",
    "https://cdn.example.test/opaque-token/report.pdf"
  ];
  for (const url of samples) {
    const origin = new URL(url).origin;
    const f = fixture({ read: () => selected({ url, siteOrigin: origin }) });
    assert.equal((await f.guard.handoff(request())).status, "handed-off", url);
    assert.equal(f.events.at(-1)[1].url, url);
  }
});

test("does not infer signed status or expiration from URL query parameters", async () => {
  for (const url of [
    "https://cdn.example.test/doc.pdf?Expires=9999999999&Signature=fake",
    "https://cdn.example.test/doc.pdf?X-Amz-Expires=86400&X-Amz-Signature=x"
  ]) {
    const noProof = fixture({ read: () => selected({
      url, signatureVerified: false
    }) });
    assert.equal((await noProof.guard.handoff(request())).status, "unavailable");
    assert.deepEqual(noProof.events.map(x => x[0]), ["read"]);
    const stale = fixture({ read: () => selected({
      url, expiresAtMs: Date.now() - 1
    }) });
    assert.equal((await stale.guard.handoff(request())).status, "expired");
    assert.deepEqual(stale.events.map(x => x[0]), ["read"]);
  }
});

test("rejects expired or near-expiry links without consent or download handoff", async () => {
  for (const expiresAtMs of [
    Date.now() - 5, Date.now(), Date.now() + 10_000,
    Date.now() + 29_000, Date.now() + 30_000
  ]) {
    const f = fixture({ read: () => selected({ expiresAtMs }) });
    const outcome = await f.guard.handoff(request());
    assert.equal(outcome.status, "expired");
    assert.equal(outcome.requiresFreshSelection, true);
    assert.equal(outcome.requiresNewConsent, true);
    assert.deepEqual(f.events.map(x => x[0]), ["read"]);
    safe(outcome);
  }
  const f = fixture({ read: () => selected({ expiresAtMs: null }) });
  assert.equal((await f.guard.handoff(request())).status, "unavailable");
});

test("missing or denied consent never exposes the signed URL to the handoff callback", async () => {
  for (const consume of [
    async () => false, async () => null, async () => "true",
    () => true, () => undefined,
    async () => { throw Error("private Signature=" + signedUrl); }
  ]) {
    const f = fixture({ consume });
    const outcome = await f.guard.handoff(request());
    assert.equal(outcome.status, "unavailable");
    safe(outcome);
    assert.deepEqual(f.events.map(x => x[0]), ["read", "consent"]);
    assert.equal((await f.guard.handoff(request())).status, "duplicate");
  }
  const f = fixture({ ready: false });
  assert.equal((await f.guard.handoff(request())).status, "unavailable");
  assert.deepEqual(f.events, []);
});

test("rechecks exact URL, resource ID, origin and site grant after asynchronous consent", async () => {
  const changes = [
    { url: signedUrl + "&token=changed" },
    { resourceId: "other_resource" },
    { siteOrigin: "https://other.example.test" },
    { tabId: 11 }, { frameId: 3 }, { selectionId: "changed" },
    { permissionGranted: false }, { verified: false },
    { signatureVerified: false }, { expiresAtMs: Date.now() + 400_000 }
  ];
  for (const change of changes) {
    let count = 0;
    const f = fixture({ read: () => selected(++count === 1 ? {} : change) });
    const outcome = await f.guard.handoff(request());
    assert.equal(outcome.status, "unavailable");
    assert.deepEqual(f.events.map(x => x[0]), ["read", "consent", "read"]);
    safe(outcome);
  }
});

test("refuses expiry during consent before dispatch, even with approval", async () => {
  let readCount = 0;
  const f = fixture({
    read: () => selected({
      expiresAtMs: Date.now() + (++readCount === 1 ? 240_000 : 1_000)
    })
  });
  const outcome = await f.guard.handoff(request());
  assert.equal(outcome.status, "unavailable" /* changed deadline invalidates selection */);
  assert.deepEqual(f.events.map(x => x[0]), ["read", "consent", "read"]);
  safe(outcome);
});

test("rejects unsafe URL schemes, credentials, fragments and normalization surprises", async () => {
  const bad = [
    "http://cdn.example.test/report.pdf?sig=123",
    "file:///private/report.pdf?sig=123",
    "blob:https://cdn.example.test/uuid",
    "data:application/pdf;base64,JVBER",
    "javascript:alert(1)",
    "https://user:secret@cdn.example.test/report.pdf?sig=123",
    "https://cdn.example.test/report.pdf?sig=123#page=2",
    "https://cdn.example.test/report.pdf?sig=100%",
    "https://cdn.example.test/report.pdf?sig=%0a",
    "https://cdn.example.test\\@other.test/report.pdf?sig=123",
    "https://cdn.example.test/a/../report.pdf?sig=123",
    "https://localhost/report.pdf?sig=123",
    "https://127.0.0.1/report.pdf?sig=123",
    "https://cdn.example.test/report.pdf?sig=one two",
    ""
  ];
  for (const url of bad) {
    const f = fixture({ read: () => selected({ url }) });
    assert.equal((await f.guard.handoff(request())).status, "unavailable", url);
    assert.deepEqual(f.events.map(x => x[0]), ["read"]);
  }
});

test("rejects malformed source records and untrusted claims without reading getters", async () => {
  let reads = 0;
  const withGetter = selected();
  Object.defineProperty(withGetter, "url", { get() {
    reads++;
    throw Error("private");
  } });
  const inherited = Object.create(selected());
  const withSymbol = selected();
  withSymbol[Symbol("secret")] = signedUrl;
  const proxy = new Proxy(selected(), { ownKeys() {
    throw Error("secret");
  } });
  const malformed = [
    null, undefined, [], withGetter, inherited, withSymbol, proxy,
    selected({ documentUrl: signedUrl }),
    selected({ cookie: "private" }), selected({ expiresAtMs: "90000" }),
    selected({ expiresAtMs: Infinity }), selected({ expiresAtMs: 1.2 }),
    selected({ siteOrigin: "https://other.example.test" }),
    selected({ permissionGranted: "true" }), selected({ verified: "true" }),
    selected({ signatureVerified: 1 }), selected({ requestId: "other" }),
    selected({ resourceId: "/private/report.pdf" })
  ];
  for (const value of malformed) {
    const f = fixture({ read: () => value });
    assert.equal((await f.guard.handoff(request())).status, "unavailable");
    assert.deepEqual(f.events.map(x => x[0]), ["read"]);
  }
  assert.equal(reads, 0);
});

test("replays and concurrent requests never reuse signed URLs or consent", async () => {
  let resolveConsent;
  const delayed = new Promise(resolve => { resolveConsent = resolve; });
  const f = fixture({ consume: () => delayed });
  const first = f.guard.handoff(request());
  assert.equal((await f.guard.handoff(request())).status, "duplicate");
  resolveConsent(true);
  assert.equal((await first).status, "handed-off");
  assert.equal((await f.guard.handoff(request())).status, "duplicate");
  assert.equal(f.events.filter(x => x[0] === "handoff").length, 1);
});

test("separate signed URL attempts consume separate consent and fresh resource proof", async () => {
  const f = fixture({ read: ref => selected({ requestId: ref.requestId }) });
  assert.equal((await f.guard.handoff(request())).status, "handed-off");
  assert.equal((await f.guard.handoff(request({ requestId: "attempt_2" }))).status,
    "handed-off");
  assert.equal(f.events.filter(x => x[0] === "consent").length, 2);
  assert.equal(f.events.filter(x => x[0] === "handoff").length, 2);
});

test("disposal cancels a pending approval and permanently closes the guard", async () => {
  let resolveConsent;
  const delayed = new Promise(resolve => { resolveConsent = resolve; });
  const f = fixture({ consume: () => delayed });
  const first = f.guard.handoff(request());
  assert.equal(f.guard.dispose().status, "ended");
  resolveConsent(true);
  assert.equal((await first).status, "unavailable");
  assert.equal(f.events.filter(x => x[0] === "handoff").length, 0);
  assert.equal((await f.guard.handoff(request({ requestId: "attempt_2" }))).status,
    "ended");
});

test("browser callback errors, unsafe receipts and missing adapters cannot leak credentials", async () => {
  const cases = [
    () => ({ accepted: true }),
    async () => ({ accepted: false }),
    async () => ({ accepted: "true" }),
    async () => { throw Error("Authorization: " + signedUrl); }
  ];
  for (const submit of cases) {
    const f = fixture({ submit });
    const outcome = await f.guard.handoff(request());
    assert.equal(outcome.status, "unavailable");
    safe(outcome);
  }
  assert.equal((await createSignedTemporaryPdfUrlHandoff()
    .handoff(request())).status, "unavailable");
});

test("no new browser permissions, network calls, logging, persistence or scanner bypass", async () => {
  const load = path => readFile(new URL(path, import.meta.url), "utf8");
  const [sourceText, manifestText, background, packageText, ci] = await Promise.all([
    load("../src/signed-temporary-pdf-url.js"),
    load("../manifest.json"), load("../src/background.js"),
    load("../package.json"), load("../../../.github/workflows/ci.yml")
  ]);
  assert.deepEqual(JSON.parse(manifestText).permissions, []);
  assert.deepEqual(JSON.parse(manifestText).host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.match(JSON.parse(packageText).scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(ci, /npm test/);
  for (const forbidden of [
    "chrome.", "browser.", "fetch(", "XMLHttpRequest", "WebSocket",
    "downloads.download(", "permissions.request(", "window.open(",
    "connectNative(", "sendNativeMessage(", "console.", "localStorage",
    "sessionStorage", "node:fs", "scan-and-open", "clamscan(",
    ".searchParams", "decodeURIComponent("
  ]) assert.equal(sourceText.includes(forbidden), false, forbidden);
});
