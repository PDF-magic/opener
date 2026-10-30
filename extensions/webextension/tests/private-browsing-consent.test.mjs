import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createPrivateBrowsingConsentGate, PRIVATE_BROWSING_CONSENT_NOTICE
} from "../src/private-browsing-consent.js";

const browser = (allowed = async () => true) => ({ isAllowedIncognitoAccess: allowed });
const active = async () => true;
const consent = { userInitiated: true };

function blocked(state) {
  assert.equal(state.scannerVerified, false);
  assert.equal(state.authorizesOpen, false);
  assert.ok(Object.isFrozen(state));
}

test("private-browsing access starts disabled and makes no browser call on construction", async () => {
  let calls = 0;
  const gate = createPrivateBrowsingConsentGate(
    browser(() => { calls++; return Promise.resolve(true); }), active
  );
  assert.deepEqual(gate.state(), {
    status: "consent-required", consentRecorded: false,
    scannerVerified: false, authorizesOpen: false
  });
  blocked(gate.state());
  assert.equal(await gate.canProcessPrivateData(), false);
  assert.equal(calls, 0);
  assert.ok(Object.isFrozen(gate));
  assert.match(PRIVATE_BROWSING_CONSENT_NOTICE, /optional/);
});

test("only explicit opt-in with browser and private-session checks records consent", async () => {
  let browserCalls = 0;
  let sessionCalls = 0;
  const gate = createPrivateBrowsingConsentGate(
    browser(async () => { browserCalls++; return true; }),
    async () => { sessionCalls++; return true; }
  );
  for (const input of [undefined, {}, { userInitiated: false },
    { userInitiated: 1 }, { userInitiated: "true" }]) {
    assert.equal((await gate.recordConsent(input)).status, "consent-required");
  }
  assert.equal(browserCalls, 0);
  assert.equal(sessionCalls, 0);
  const result = await gate.recordConsent(consent);
  assert.equal(result.status, "consented");
  assert.equal(result.consentRecorded, true);
  blocked(result);
  assert.equal(browserCalls, 1);
  assert.equal(sessionCalls, 1);
  assert.equal(await gate.canProcessPrivateData(), true);
  assert.equal(browserCalls, 2);
  assert.equal(sessionCalls, 2);
});

test("browser private access alone cannot override missing per-session user consent", async () => {
  const gate = createPrivateBrowsingConsentGate(browser(), active);
  assert.equal(await gate.canProcessPrivateData(), false);
  assert.equal(gate.state().status, "consent-required");
  assert.equal((await gate.recordConsent({ userInitiated: false })).consentRecorded, false);
});

test("opt-in cannot bypass browser-level refusal or non-private context", async () => {
  for (const [api, session] of [
    [browser(async () => false), active],
    [browser(), async () => false],
    [browser(async () => "true"), active],
    [browser(), async () => "true"]
  ]) {
    const gate = createPrivateBrowsingConsentGate(api, session);
    assert.equal((await gate.recordConsent(consent)).status, "unavailable");
    assert.equal(await gate.canProcessPrivateData(), false);
    blocked(gate.state());
  }
});

test("unsupported, callback-only and failing browsers remain disabled", async () => {
  for (const api of [null, {}, { isAllowedIncognitoAccess: true },
    browser(() => undefined), browser(() => false),
    browser(() => { throw Error("/private/secret.pdf"); }),
    browser(() => Promise.reject(Error("/private/secret.pdf")))]) {
    const gate = createPrivateBrowsingConsentGate(api, active);
    assert.equal((await gate.recordConsent(consent)).status, "unavailable");
    assert.equal(JSON.stringify(gate.state()).includes("secret"), false);
    assert.equal(await gate.canProcessPrivateData(), false);
  }
  const noSession = createPrivateBrowsingConsentGate(browser(), null);
  assert.equal((await noSession.recordConsent(consent)).status, "unavailable");
});

test("untrusted browser API getters never execute", async () => {
  let ran = 0;
  const api = {};
  Object.defineProperty(api, "isAllowedIncognitoAccess", {
    get() { ran++; throw Error("must not run"); }
  });
  const gate = createPrivateBrowsingConsentGate(api, active);
  assert.equal((await gate.recordConsent(consent)).status, "unavailable");
  assert.equal(ran, 0);
  const proxy = new Proxy({}, { getOwnPropertyDescriptor() { throw Error("private"); } });
  assert.equal((await createPrivateBrowsingConsentGate(proxy, active).recordConsent(consent)).status,
    "unavailable");
});

test("browser access is rechecked and revocation latches private consent closed", async () => {
  let permitted = true;
  let calls = 0;
  const gate = createPrivateBrowsingConsentGate(browser(async () => {
    calls++;
    return permitted;
  }), active);
  assert.equal((await gate.recordConsent(consent)).status, "consented");
  assert.equal(await gate.canProcessPrivateData(), true);
  permitted = false;
  assert.equal(await gate.canProcessPrivateData(), false);
  assert.equal(gate.state().status, "unavailable");
  permitted = true;
  assert.equal(await gate.canProcessPrivateData(), false);
  assert.equal((await gate.recordConsent(consent)).status, "unavailable",
    "an invalidated consent must not produce a stale consented status");
  assert.equal(await gate.canProcessPrivateData(), false);
  assert.equal(calls, 3);
});

test("private-context mismatch invalidates consent even with a browser grant", async () => {
  let stillPrivate = true;
  const gate = createPrivateBrowsingConsentGate(browser(), async () => stillPrivate);
  assert.equal((await gate.recordConsent(consent)).status, "consented");
  stillPrivate = false;
  assert.equal(await gate.canProcessPrivateData(), false);
  assert.equal(gate.state().status, "unavailable");
});

test("ending a session invalidates consent and cannot be undone in that gate", async () => {
  const gate = createPrivateBrowsingConsentGate(browser(), active);
  assert.equal((await gate.recordConsent(consent)).status, "consented");
  assert.equal(gate.endSession().status, "ended");
  assert.equal(await gate.canProcessPrivateData(), false);
  assert.equal((await gate.recordConsent(consent)).status, "ended");
  assert.equal(gate.endSession().status, "ended");
});

test("late permission response after session shutdown cannot restore consent", async () => {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  const gate = createPrivateBrowsingConsentGate(browser(() => pending), active);
  const request = gate.recordConsent(consent);
  assert.equal(gate.endSession().status, "ended");
  release(true);
  assert.equal((await request).status, "ended");
  assert.equal(await gate.canProcessPrivateData(), false);
});

test("concurrent opt-ins share a permission check and do not reprompt", async () => {
  let release;
  let calls = 0;
  const pending = new Promise(resolve => { release = resolve; });
  const gate = createPrivateBrowsingConsentGate(browser(() => {
    calls++;
    return pending;
  }), active);
  const first = gate.recordConsent(consent);
  const second = gate.recordConsent(consent);
  assert.strictEqual(first, second);
  assert.equal(calls, 1);
  release(true);
  assert.equal((await first).status, "consented");
  assert.strictEqual(gate.recordConsent(consent), first);
});

test("independent private sessions never share a consent decision", async () => {
  const one = createPrivateBrowsingConsentGate(browser(), active);
  const two = createPrivateBrowsingConsentGate(browser(), active);
  await one.recordConsent(consent);
  assert.equal(await one.canProcessPrivateData(), true);
  assert.equal(await two.canProcessPrivateData(), false);
  one.endSession();
  assert.equal(await one.canProcessPrivateData(), false);
  assert.equal(two.state().status, "consent-required");
});

test("consent module has no import-time browser, storage or scanner effects", async () => {
  const src = await readFile(new URL("../src/private-browsing-consent.js", import.meta.url), "utf8");
  const executable = src.replace(/\/\/[^\n]*/g, "");
  for (const forbidden of [
    "globalThis.", "browser.", "chrome.", "addListener(", "permissions.request(",
    "connectNative(", "sendNativeMessage(", "fetch(", "window.open(",
    "localStorage", "sessionStorage", "node:fs", "scan-and-open"
  ]) {
    assert.equal(executable.includes(forbidden), false, forbidden);
  }
});
