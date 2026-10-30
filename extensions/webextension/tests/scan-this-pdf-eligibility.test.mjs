import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createScanThisPdfEligibilityGate, SCAN_THIS_PDF_LABEL } from "../src/scan-this-pdf-eligibility.js";

const evidence = () => ({
  pdfIdentified: true, currentDocumentVerified: true, selectionVerified: true,
  sourceAccessible: true, permissionGranted: true
});
const coordinator = () => ({
  currentPdfScanReady: true,
  readCurrentPdfEligibility: () => evidence(),
  requestCurrentPdfScan: () => { throw new Error("must not invoke"); }
});
const button = () => ({
  id: "scanThisPDF", tagName: "BUTTON", disabled: true,
  attributes: new Map([["aria-disabled", "true"]]),
  setAttribute(key, value) { this.attributes.set(key, value); }
});

test("Scan This PDF stays unavailable without authenticated current-PDF coordination", () => {
  assert.equal(SCAN_THIS_PDF_LABEL, "Scan This PDF");
  const gate = createScanThisPdfEligibilityGate();
  assert.equal(gate.state().enabled, false);
  assert.equal(gate.state().scanVerified, false);
  assert.equal(gate.state().authorizesOpen, false);
  assert.ok(Object.isFrozen(gate));
  assert.ok(Object.isFrozen(gate.state()));
  const ui = button();
  assert.equal(gate.updateControl(ui), false);
  assert.equal(ui.disabled, true);
  assert.equal(ui.attributes.get("aria-disabled"), "true");
});

test("only an eligible, current, verified and accessible PDF enables the control", () => {
  const coordinatorState = coordinator();
  const gate = createScanThisPdfEligibilityGate(coordinatorState);
  assert.equal(gate.state().enabled, true);
  const ui = button();
  assert.equal(gate.updateControl(ui), true);
  assert.equal(ui.disabled, false);
  assert.equal(ui.attributes.get("aria-disabled"), "false");
  assert.equal(gate.state().scanVerified, false);
  assert.equal(gate.state().authorizesOpen, false);
  for (const key of Object.keys(evidence())) {
    coordinatorState.readCurrentPdfEligibility = () => ({ ...evidence(), [key]: false });
    assert.equal(gate.updateControl(ui), false, key);
    assert.equal(ui.disabled, true);
    assert.equal(ui.attributes.get("aria-disabled"), "true");
  }
});

test("revoking scanner readiness, permissions or selection immediately disables action", () => {
  const current = coordinator();
  const gate = createScanThisPdfEligibilityGate(current);
  const ui = button();
  assert.equal(gate.updateControl(ui), true);
  current.currentPdfScanReady = false;
  assert.equal(gate.updateControl(ui), false);
  current.currentPdfScanReady = true;
  assert.equal(gate.updateControl(ui), true);
  current.requestCurrentPdfScan = undefined;
  assert.equal(gate.updateControl(ui), false);
  current.requestCurrentPdfScan = () => {};
  current.readCurrentPdfEligibility = () => ({ ...evidence(), permissionGranted: false });
  assert.equal(gate.updateControl(ui), false);
});

test("PDF URL, MIME hints and forged or malformed eligibility never suffice", () => {
  const current = coordinator();
  const gate = createScanThisPdfEligibilityGate(current);
  for (const value of [
    { isPdfCandidate: true, evidence: "mime-type", authorizesOpen: false },
    { url: "https://example.invalid/report.pdf", mimeType: "application/pdf" },
    { ...evidence(), extra: "private" },
    { ...evidence(), sourceAccessible: "true" },
    { ...evidence(), pdfIdentified: undefined },
    { ...evidence(), authorizesOpen: true },
    null, undefined, true, [], new URL("https://example.invalid/a.pdf")
  ]) {
    current.readCurrentPdfEligibility = () => value;
    assert.equal(gate.state().enabled, false);
  }
});

test("accessors, inherited flags, asynchronous or throwing claims fail closed", () => {
  const current = coordinator();
  const gate = createScanThisPdfEligibilityGate(current);
  const getter = evidence();
  Object.defineProperty(getter, "pdfIdentified", { get() { throw Error("do not read"); } });
  for (const response of [getter, Object.create(evidence()), Promise.resolve(evidence()),
    new Proxy({}, { getPrototypeOf() { throw Error("trap"); } })]) {
    current.readCurrentPdfEligibility = () => response;
    assert.equal(gate.state().enabled, false);
  }
  current.readCurrentPdfEligibility = () => { throw Error("sensitive path"); };
  assert.equal(gate.state().enabled, false);
  const bad = {};
  Object.defineProperty(bad, "currentPdfScanReady", { get() { throw Error("trap"); } });
  assert.equal(createScanThisPdfEligibilityGate(bad).state().enabled, false);
  assert.equal(createScanThisPdfEligibilityGate(Object.create(coordinator())).state().enabled, false);
});

test("updates only the explicitly named Scan This PDF button and never triggers scans", () => {
  let calls = 0;
  const current = coordinator();
  current.requestCurrentPdfScan = () => calls++;
  const gate = createScanThisPdfEligibilityGate(current);
  for (const ui of [{ ...button(), id: "scanPDF" }, { ...button(), tagName: "A" }, null, {}]) {
    assert.equal(gate.updateControl(ui), false);
  }
  assert.equal(gate.updateControl(button()), true);
  assert.equal(calls, 0);
});

test("gate has no page inspection, browser privileges, native calls or opening side effects", async () => {
  const source = await readFile(new URL("../src/scan-this-pdf-eligibility.js", import.meta.url), "utf8");
  for (const forbidden of ["document.", "querySelector(", "chrome.", "browser.", "fetch(",
    "XMLHttpRequest", "sendNativeMessage(", "connectNative(", "window.open(",
    "addEventListener(", "node:fs", "localStorage", "scan-and-open"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
