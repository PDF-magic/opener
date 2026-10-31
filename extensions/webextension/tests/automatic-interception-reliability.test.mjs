import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX,
  AUTOMATIC_INTERCEPTION_RELIABILITY_POLICY_VERSION,
  AUTOMATIC_INTERCEPTION_PDF_PATHS,
  assessAutomaticInterceptionReliability,
  assessAutomaticPdfInterception
} from "../src/automatic-interception-capability-matrix.js";

const ids = AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.map(row => row.id);
function deny(result, reason) {
  assert.equal(Object.isFrozen(result), true);
  assert.equal(result.status, "disabled-unreliable");
  assert.equal(result.reason, reason);
  assert.equal(result.automaticInterceptionDisabled, true);
  assert.equal(result.automaticInterceptionEnabled, false);
  assert.equal(result.blockingPointVerified, false);
  assert.equal(result.nativeScanInterlockVerified, false);
  assert.equal(result.allPdfOpeningPathsBlocked, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.doesNotMatch(JSON.stringify(result), /https?:|token|private|filename/i);
}

test("all shipped browsers remain disabled even for main-frame PDF candidates", () => {
  assert.equal(AUTOMATIC_INTERCEPTION_RELIABILITY_POLICY_VERSION, 1);
  assert.equal(ids.length, 9);
  for (const id of ids) {
    const row = AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.find(x => x.id === id);
    const reason = row.family === "chromium"
      ? "no-verified-blocking-native-hold"
      : row.family === "webkit" ? "browser-interception-unverified"
        : "native-scan-interlock-unverified";
    deny(assessAutomaticInterceptionReliability(id), reason);
    const assessment = assessAutomaticPdfInterception(id);
    assert.equal(assessment.status, "inactive");
    assert.equal(assessment.automaticInterceptionDisabled, true);
    assert.equal(assessment.disabledReason, reason);
    assert.equal(assessment.automaticInterceptionEnabled, false);
  }
});

test("unsupported PDF routes stay disabled even when browser APIs exist", () => {
  assert.ok(Object.isFrozen(AUTOMATIC_INTERCEPTION_PDF_PATHS));
  assert.equal(new Set(AUTOMATIC_INTERCEPTION_PDF_PATHS).size,
    AUTOMATIC_INTERCEPTION_PDF_PATHS.length);
  assert.ok(AUTOMATIC_INTERCEPTION_PDF_PATHS.includes("network-main-frame"));
  for (const id of ids) {
    for (const pdfPath of AUTOMATIC_INTERCEPTION_PDF_PATHS) {
      if (pdfPath === "network-main-frame") continue;
      deny(assessAutomaticInterceptionReliability(id, pdfPath),
        "uncontrolled-pdf-path");
    }
  }
});

test("missing, malformed and unrecognized browser or PDF context fail closed", () => {
  for (const browserId of [
    undefined, null, {}, [], 42, new String("firefox"),
    "Firefox", "opera-gx", "safari ", "gecko", ""
  ]) {
    deny(assessAutomaticInterceptionReliability(browserId),
      "unsupported-browser");
    const state = assessAutomaticPdfInterception(browserId);
    assert.equal(state.automaticInterceptionDisabled, true);
    assert.equal(state.automaticInterceptionEnabled, false);
  }
  for (const path of [
    undefined, null, {}, [], 33, new String("network-main-frame"),
    "unknown", "", "https://private.test/report.pdf", "file:///tmp/private.pdf"
  ]) {
    if (path === undefined) continue; // Omitted argument uses the safe default.
    deny(assessAutomaticInterceptionReliability("firefox", path),
      "unverified-pdf-path");
  }
});

test("forged API readiness and stored opt-in cannot enable interception", async () => {
  let calls = 0;
  const event = { addListener() { calls++; }, removeListener() { calls++; } };
  const fakeApi = {
    runtime: { getManifest() { calls++; }, getURL() { calls++; } },
    webRequest: {
      onBeforeRequest: event, filterResponseData() { calls++; }
    },
    declarativeNetRequest: {
      getDynamicRules() { calls++; },
      updateDynamicRules() { calls++; }
    },
    downloads: {
      onCreated: event, onChanged: event, onErased: event
    }
  };
  for (const id of ids) {
    const result = assessAutomaticPdfInterception(id, fakeApi);
    assert.equal(result.automaticInterceptionDisabled, true);
    assert.equal(result.automaticInterceptionEnabled, false);
    assert.equal(result.permissionVerified, false);
    assert.equal(result.nativeScanInterlockVerified, false);
    deny(assessAutomaticInterceptionReliability(id, "network-main-frame"),
      result.disabledReason);
  }
  assert.equal(calls, 0);

  const swift = await readFile(
    new URL("../../../PDFMagicOpenerApp/ScanProgressPreference.swift",
      import.meta.url), "utf8");
  assert.match(swift, /automaticPDFInterceptionOptIns/);
  assert.match(swift, /saveOptIn\(/);
  // A preference for future support remains independently editable and
  // preserved. This policy does not rewrite stored user choices.
});

test("no unreliable path gains live permissions, native calls or PDF opening", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [manifest, background, source, pkg] = await Promise.all([
    read("../manifest.json").then(JSON.parse), read("../src/background.js"),
    read("../src/automatic-interception-capability-matrix.js"),
    read("../package.json").then(JSON.parse)
  ]);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(background.trim().endsWith("void 0;"));
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  for (const forbidden of [
    "permissions.request(", "downloads.open(", "connectNative(",
    "sendNativeMessage(", "location.href =", "fetch(", "addListener("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
