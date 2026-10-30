import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createScanPdfAction, SCAN_PDF_LABEL, SCAN_PDF_UNAVAILABLE_MESSAGE
} from "../src/scan-pdf-action.js";

test("Scan PDF is exposed as a truthful manual action with safe unavailable state", () => {
  const action = createScanPdfAction();
  assert.equal(SCAN_PDF_LABEL, "Scan PDF");
  assert.match(SCAN_PDF_UNAVAILABLE_MESSAGE, /native scanner/);
  assert.deepEqual(action.state(), {
    label: "Scan PDF",
    enabled: false,
    unavailableMessage: SCAN_PDF_UNAVAILABLE_MESSAGE,
    scanVerified: false,
    authorizesOpen: false
  });
  assert.ok(Object.isFrozen(action));
  assert.ok(Object.isFrozen(action.state()));
});

test("a missing trusted native coordinator cannot scan, open or claim success", async () => {
  const action = createScanPdfAction();
  assert.deepEqual(await action.activate({ userInitiated: true }), {
    status: "unavailable", scanVerified: false, authorizesOpen: false
  });
  assert.deepEqual(await action.activate(), {
    status: "not-requested", scanVerified: false, authorizesOpen: false
  });
});

test("manual scan requires an explicit user action, not a configuration default", async () => {
  let called = 0;
  const coordinator = {
    manualScanReady: true,
    requestUserSelectedPdfScan() { called++; return { accepted: true }; }
  };
  const action = createScanPdfAction(coordinator);
  assert.equal(action.state().enabled, true);
  for (const input of [undefined, {}, { userInitiated: false },
                       { userInitiated: 1 }, { userInitiated: "true" }]) {
    assert.equal((await action.activate(input)).status, "not-requested");
  }
  assert.equal(called, 0);
  assert.equal((await action.activate({ userInitiated: true })).status, "request-submitted");
  assert.equal(called, 1);
});

test("submission cannot claim a clean scan or authorize PDF opening", async () => {
  let argumentsPassed;
  const coordinator = {
    manualScanReady: true,
    requestUserSelectedPdfScan(...args) {
      argumentsPassed = args;
      return { accepted: true, status: "clean", authorizesOpen: true,
        path: "/private/secret.pdf", token: "sensitive" };
    }
  };
  const result = await createScanPdfAction(coordinator).activate({ userInitiated: true });
  assert.deepEqual(argumentsPassed, []);
  assert.deepEqual(result, {
    status: "request-submitted", scanVerified: false, authorizesOpen: false
  });
  assert.ok(Object.isFrozen(result));
  assert.equal(JSON.stringify(result).includes("private"), false);
});

test("native readiness and accepted acknowledgment are independently required", async () => {
  let count = 0;
  const coordinator = {
    manualScanReady: false,
    requestUserSelectedPdfScan() { count++; return { accepted: true }; }
  };
  const action = createScanPdfAction(coordinator);
  assert.equal(action.state().enabled, false);
  assert.equal((await action.activate({ userInitiated: true })).status, "unavailable");
  assert.equal(count, 0);
  coordinator.manualScanReady = true;
  assert.equal(action.state().enabled, true);
  coordinator.requestUserSelectedPdfScan = () => ({ accepted: false });
  assert.equal((await action.activate({ userInitiated: true })).status, "unavailable");
  assert.equal(count, 0);
});

test("native failures and unexpected acknowledgments fail closed without leaking data", async () => {
  const coordinator = {
    manualScanReady: true,
    requestUserSelectedPdfScan() { throw Error("Sensitive document: /secret/scan.pdf"); }
  };
  const action = createScanPdfAction(coordinator);
  let result = await action.activate({ userInitiated: true });
  assert.equal(result.status, "unavailable");
  assert.equal(JSON.stringify(result).includes("secret"), false);
  coordinator.requestUserSelectedPdfScan = async () => ({ accepted: "true" });
  result = await action.activate({ userInitiated: true });
  assert.equal(result.status, "unavailable");
  coordinator.requestUserSelectedPdfScan = async () => { throw Error("failed"); };
  assert.equal((await action.activate({ userInitiated: true })).status, "unavailable");
});

test("untrusted getters and inherited readiness fail closed", async () => {
  const inherited = Object.create({ manualScanReady: true,
    requestUserSelectedPdfScan() { throw Error("must not invoke"); } });
  assert.equal(createScanPdfAction(inherited).state().enabled, false);
  const withGetter = {};
  Object.defineProperty(withGetter, "manualScanReady", {
    get() { throw Error("getter must not execute"); }
  });
  assert.equal(createScanPdfAction(withGetter).state().enabled, false);
  const denied = new Proxy({}, {
    getOwnPropertyDescriptor() { throw Error("proxy must be isolated"); }
  });
  assert.equal(createScanPdfAction(denied).state().enabled, false);
  assert.equal((await createScanPdfAction(denied).activate({ userInitiated: true })).status,
    "unavailable");
});

test("the scan action does not activate browser APIs, native messaging or file access", async () => {
  const code = await readFile(new URL("../src/scan-pdf-action.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.", "browser.", "fetch(", "XMLHttpRequest", "WebSocket",
    "connectNative(", "sendNativeMessage(", "window.open(", "addListener(",
    "localStorage", "node:fs", "scan-and-open", "clamscan"
  ]) {
    assert.equal(code.includes(forbidden), false, forbidden);
  }
});
