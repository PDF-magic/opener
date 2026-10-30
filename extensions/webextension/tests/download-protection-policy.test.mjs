import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createConfiguredDownloadProtectionCoordinator as createCoordinator,
  installedDownloadProtectionPolicy as policy
} from "../src/download-protection-policy.js";

const request = Object.freeze({ id: 7, localPath: "/private/reports/document.pdf" });
const ack = () => Promise.resolve({ accepted: true, effectivePolicyId: "built-in" });
function fixture(configuration = { selectedProtectionProfile: "built-in" }) {
  const submissions = [];
  const coordinator = {
    nativeScannerReady: true,
    submitCompletedPdfDownload(candidate, effectivePolicy) {
      submissions.push({ candidate, effectivePolicy });
      return ack();
    }
  };
  const config = () => Promise.resolve(configuration);
  return { coordinator, config, submissions };
}

test("applies installed Built-in controls to a trusted coordinator on every request", async () => {
  const f = fixture();
  const wrapped = createCoordinator(f.coordinator, f.config);
  assert.equal(wrapped.nativeScannerReady, true);
  assert.deepEqual(await wrapped.submitCompletedPdfDownload(request),
    { accepted: true, effectivePolicyId: "built-in" });
  assert.equal(f.submissions.length, 1);
  assert.deepEqual(f.submissions[0].candidate, request);
  assert.equal(Object.isFrozen(f.submissions[0].candidate), true);
  assert.strictEqual(f.submissions[0].effectivePolicy, policy);
  assert.deepEqual(policy, {
    profileId: "built-in",
    requiredChecks: ["clamav_scan_gate", "signature_freshness",
      "file_integrity", "fail_closed_handoff"],
    failureDisposition: "deny"
  });
  assert.equal(Object.isFrozen(policy.requiredChecks), true);
  assert.equal(Object.isFrozen(policy), true);
});

test("missing active selection uses the documented Built-in default", async () => {
  const f = fixture({ showScanProgress: false });
  const wrapped = createCoordinator(f.coordinator, f.config);
  assert.equal((await wrapped.submitCompletedPdfDownload(request)).accepted, true);
  assert.equal(f.submissions.length, 1);
});

test("planned preview choices are preserved and never applied as active tiers", async () => {
  for (const preview of ["standard", "enhanced", "maximum", "unassigned"]) {
    const config = { selectedProtectionProfile: "built-in",
      preferredProtectionLevel: preview, showScanProgress: false };
    const f = fixture(config);
    const wrapped = createCoordinator(f.coordinator, f.config);
    assert.equal((await wrapped.submitCompletedPdfDownload(request)).accepted, true);
    assert.deepEqual(config, { selectedProtectionProfile: "built-in",
      preferredProtectionLevel: preview, showScanProgress: false });
    assert.equal(f.submissions[0].effectivePolicy.profileId, "built-in");
  }
});

test("unsupported, invalid or future active selections fail closed without downgrading", async () => {
  for (const selection of ["standard", "enhanced", "maximum",
    "future-tier", "", null, 7, false, undefined]) {
    const f = fixture({ selectedProtectionProfile: selection });
    const wrapped = createCoordinator(f.coordinator, f.config);
    assert.deepEqual(await wrapped.submitCompletedPdfDownload(request), { accepted: false });
    assert.deepEqual(f.submissions, []);
  }
});

test("malformed settings and accessor-backed active selection fail closed", async () => {
  let reads = 0;
  const accessor = {};
  Object.defineProperty(accessor, "selectedProtectionProfile", {
    get() { reads++; throw Error("private settings"); }
  });
  for (const value of [null, [], "built-in", 1, accessor,
    Object.create({ selectedProtectionProfile: "built-in" })]) {
    const f = fixture(value);
    const wrapped = createCoordinator(f.coordinator, f.config);
    assert.deepEqual(await wrapped.submitCompletedPdfDownload(request), { accepted: false });
    assert.deepEqual(f.submissions, []);
  }
  assert.equal(reads, 0);
});

test("unknown/forged requests cannot invoke the native submission method", async () => {
  let reads = 0;
  const getter = { id: 7 };
  Object.defineProperty(getter, "localPath", {
    get() { reads++; throw Error("secret"); }
  });
  const malicious = [
    null, {}, 7, "file", [], getter,
    { id: 7 }, { id: -1, localPath: "/a.pdf" },
    { id: "7", localPath: "/a.pdf" }, { id: 7.2, localPath: "/a.pdf" },
    { id: 7, localPath: "" },
    { id: 7, localPath: "/a.pdf", scanVerified: true },
    { id: 7, localPath: "/a.pdf", authorizesOpen: true },
    Object.assign(Object.create({ id: 7 }), { localPath: "/a.pdf" })
  ];
  const f = fixture();
  const wrapped = createCoordinator(f.coordinator, f.config);
  for (const value of malicious) {
    assert.deepEqual(await wrapped.submitCompletedPdfDownload(value), { accepted: false });
  }
  assert.equal(f.submissions.length, 0);
  assert.equal(reads, 0);
});

test("native policy mismatch or rejection does not claim successful submission", async () => {
  for (const reply of [
    { accepted: true }, { accepted: true, effectivePolicyId: "maximum" },
    { accepted: true, effectivePolicyId: "standard" },
    { accepted: false, effectivePolicyId: "built-in" },
    null, { accepted: "true", effectivePolicyId: "built-in" }
  ]) {
    const f = fixture();
    f.coordinator.submitCompletedPdfDownload = () => Promise.resolve(reply);
    const wrapped = createCoordinator(f.coordinator, f.config);
    assert.deepEqual(await wrapped.submitCompletedPdfDownload(request), { accepted: false });
  }
});

test("settings change during asynchronous native submission fails closed", async () => {
  const f = fixture();
  let current = { selectedProtectionProfile: "built-in" };
  f.config = () => Promise.resolve(current);
  let respond;
  f.coordinator.submitCompletedPdfDownload = () => new Promise(resolve => { respond = resolve; });
  const wrapped = createCoordinator(f.coordinator, f.config);
  const pending = wrapped.submitCompletedPdfDownload(request);
  await new Promise(resolve => setImmediate(resolve));
  current = { selectedProtectionProfile: "enhanced" };
  respond({ accepted: true, effectivePolicyId: "built-in" });
  assert.deepEqual(await pending, { accepted: false });
});

test("native disconnect, failed configuration reads and throws never expose private paths", async () => {
  const f = fixture();
  f.coordinator.nativeScannerReady = false;
  const offline = createCoordinator(f.coordinator, f.config);
  assert.equal(offline.nativeScannerReady, false);
  assert.deepEqual(await offline.submitCompletedPdfDownload(request), { accepted: false });
  assert.deepEqual(f.submissions, []);
  const errors = fixture();
  errors.config = () => Promise.reject(Error("/private/secret-preferences"));
  const wrapped = createCoordinator(errors.coordinator, errors.config);
  assert.deepEqual(await wrapped.submitCompletedPdfDownload(request), { accepted: false });
  assert.equal(JSON.stringify(await wrapped.submitCompletedPdfDownload(request)).includes("private"), false);
  assert.deepEqual(errors.submissions, []);
});

test("native readiness is checked again after async configuration access", async () => {
  const f = fixture();
  f.config = async () => {
    f.coordinator.nativeScannerReady = false;
    return { selectedProtectionProfile: "built-in" };
  };
  const wrapped = createCoordinator(f.coordinator, f.config);
  assert.deepEqual(await wrapped.submitCompletedPdfDownload(request), { accepted: false });
  assert.deepEqual(f.submissions, []);
});

test("module remains opt-in and never reads settings, enables scanning or weakens safety", async () => {
  const source = await readFile(new URL("../src/download-protection-policy.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of [
    "globalThis.chrome", "globalThis.browser", "UserDefaults", "localStorage",
    "storage.local", "connectNative(", "sendNativeMessage(", "scan_and_open",
    "clamscan", "downloads.open(", "fetch(", "node:fs"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
