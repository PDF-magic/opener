import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createDownloadStructuralWarningsDisplay as createDisplay } from
  "../src/download-structural-warnings.js";

class Node {
  constructor(tag, document = null) {
    this.nodeType = 1;
    this.tag = tag;
    this.ownerDocument = document;
    this.children = [];
    this.attributes = {};
    this.textContent = "";
    this.hidden = false;
  }
  appendChild(node) { this.children.push(node); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  removeAttribute(key) { delete this.attributes[key]; }
  get visibleText() {
    return [this.textContent, ...this.children.map(x => x.visibleText)].join(" ");
  }
}
function root() {
  const doc = { createElement(tag) { return new Node(tag, doc); } };
  return new Node("section", doc);
}

const id = "scan_req_9";
function finding(code = "malformedStructure", severity = "suspicious",
  outcome = "reviewRequired", nextAction = "requestReviewBeforeOpening") {
  return {
    code, findingId: "finding-v1:test:object=none:page=none",
    severity, objectNumber: null, pageNumber: null,
    result: { outcome, nextAction,
      explanation: "untrusted provider-controlled explanation: /private/secret.pdf",
      malwareAssessment: "notConfirmed" }
  };
}
function report(stageResults = [{
  stage: "pdfStructure", outcome: "completed", findings: [finding()]
}], requiresBlock = true, status = "clean") {
  return {
    schemaVersion: 1, authorizesOpen: false, requiresBlock,
    scan: { status }, clamav: { effectivePolicyId: "built-in", detectionNames: [] },
    structuralFindings: {
      schemaVersion: 2, authorizesOpen: false, requiresBlock,
      stageResults
    }
  };
}
function fixture(input = report()) {
  const host = {
    nativeScanResultsReady: true,
    readVerifiedDownloadScanReport: async (requested) => ({
      scanRequestId: requested, report: input
    })
  };
  return { host, target: root() };
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test("renders a real accessible structural warning from a trusted correlated report", async () => {
  const f = fixture();
  const display = createDisplay(f.target, f.host);
  const result = await display.show(id);
  assert.deepEqual(result, {
    status: "displayed", warningsDisplayed: 1, authorizesOpen: false
  });
  assert.equal(f.target.hidden, false);
  assert.equal(f.target.attributes.role, "alert");
  assert.match(f.target.visibleText, /Structural warnings/);
  assert.match(f.target.visibleText, /PDF structure · Suspicious · Malformed structure/);
  assert.match(f.target.visibleText, /Review required/);
  assert.match(f.target.visibleText, /not malware confirmation/);
  assert.doesNotMatch(f.target.visibleText, /private|secret|https?:|untrusted provider/i);
  assert.equal(f.target.children[2].tag, "ul");
  assert.equal(f.target.children[2].children[0].tag, "li");
  display.dispose();
});

test("incomplete and unrun stages are displayed instead of claiming success", async () => {
  const f = fixture(report([
    { stage: "pdfStructure", outcome: "completed", findings: [] },
    { stage: "embeddedFiles", outcome: "incomplete", findings: [] },
    { stage: "javascriptActions", outcome: "notRun", findings: [] }
  ]));
  const display = createDisplay(f.target, f.host);
  const answer = await display.show(id);
  assert.equal(answer.warningsDisplayed, 2);
  assert.match(f.target.visibleText, /Embedded files: inspection incomplete/);
  assert.match(f.target.visibleText, /JavaScript actions: inspection not run/);
  display.dispose();
});

test("known malicious and inspection failure codes cannot be downgraded by severity", async () => {
  const f = fixture(report([{
    stage: "pdfStructure", outcome: "completed",
    findings: [
      finding("knownMaliciousContent", "informational", "blocking", "stopOpening"),
      finding("resourceLimit", "informational",
        "inspectionIncomplete", "rerunOrRepairInspection")
    ]
  }]));
  const display = createDisplay(f.target, f.host);
  assert.equal((await display.show(id)).warningsDisplayed, 2);
  assert.match(f.target.visibleText, /Known malicious content — Opening stopped/);
  assert.match(f.target.visibleText, /Resource limit — Inspection incomplete/);
  display.dispose();
});

test("informational-only evidence hides warnings and never grants approval", async () => {
  const f = fixture(report([{
    stage: "pdfStructure", outcome: "completed",
    findings: [finding("unsupportedFeature", "informational",
      "recorded", "continueRequiredChecks")]
  }], false));
  const display = createDisplay(f.target, f.host);
  assert.deepEqual(await display.show(id), {
    status: "no-warnings", warningsDisplayed: 0, authorizesOpen: false
  });
  assert.equal(f.target.hidden, true);
  assert.deepEqual(f.target.children, []);
  display.dispose();
});

test("requiresBlock mismatches, malformed findings and unexpected stage IDs fail closed", async () => {
  const invalids = [
    report([], false),
    report([{ stage: "unknown", outcome: "completed", findings: [] }], false),
    report([{ stage: "pdfStructure", outcome: "notRun", findings: [finding()] }]),
    report([{ stage: "pdfStructure", outcome: "completed",
      findings: [finding("malformedStructure", "informational", "recorded",
        "continueRequiredChecks")] }], true),
    report([{ stage: "pdfStructure", outcome: "completed",
      findings: [finding("resourceLimit", "informational", "recorded",
        "continueRequiredChecks")] }]),
    report([{ stage: "pdfStructure", outcome: "completed",
      findings: [finding("malformedStructure", "critical",
        "reviewRequired", "requestReviewBeforeOpening")] }]),
    report([{ stage: "pdfStructure", outcome: "completed",
      findings: [finding()] }, { stage: "pdfStructure", outcome: "completed",
      findings: [] }]),
    report([{ stage: "pdfStructure", outcome: "completed", findings: [] }], true)
  ];
  invalids[0].structuralFindings.requiresBlock = false;
  for (const r of invalids) {
    const f = fixture(r);
    const display = createDisplay(f.target, f.host);
    assert.equal((await display.show(id)).status, "unavailable");
    assert.equal(f.target.hidden, true);
    display.dispose();
  }
});

test("rejects malformed combined reports, unsupported policy, and mismatched scan IDs", async () => {
  const invalids = [
    { ...report(), schemaVersion: 0 },
    { ...report(), authorizesOpen: true },
    { ...report(), clamav: { effectivePolicyId: "maximum", detectionNames: [] } },
    { ...report(), scan: { status: "complete" } },
    { ...report(), scan: { status: "clean" }, clamav: {
      effectivePolicyId: "built-in", detectionNames: ["Threat"]
    } },
    { ...report(), privatePath: "/private/report.pdf" },
    { ...report(), structuralFindings: {
      ...report().structuralFindings, authorizesOpen: true
    } }
  ];
  for (const r of invalids) {
    const f = fixture(r);
    const display = createDisplay(f.target, f.host);
    assert.equal((await display.show(id)).status, "unavailable");
    assert.equal(f.target.hidden, true);
    display.dispose();
  }
  const f = fixture();
  f.host.readVerifiedDownloadScanReport = async () => ({
    scanRequestId: "different_id", report: report()
  });
  const display = createDisplay(f.target, f.host);
  assert.equal((await display.show(id)).status, "unavailable");
  display.dispose();
});

test("never invokes PDF-controlled or hostile getters and never shows injected strings", async () => {
  let accesses = 0;
  const findingValue = finding();
  Object.defineProperty(findingValue, "code", {
    get() { accesses += 1; throw Error("private path"); }
  });
  const response = report([{
    stage: "pdfStructure", outcome: "completed", findings: [findingValue]
  }]);
  const f = fixture(response);
  const display = createDisplay(f.target, f.host);
  assert.equal((await display.show(id)).status, "unavailable");
  assert.equal(accesses, 0);
  const malicious = report();
  malicious.structuralFindings.stageResults[0].findings[0].result.explanation =
    "<img src=x onerror=alert(1)> https://private.example report.pdf";
  f.host.readVerifiedDownloadScanReport = async () => ({
    scanRequestId: id, report: malicious
  });
  assert.equal((await display.show(id)).status, "displayed");
  assert.doesNotMatch(f.target.visibleText, /<img|private\.example|report\.pdf/);
  display.dispose();
});

test("validates every warning even beyond the visible 64-row limit", async () => {
  const findings = Array.from({ length: 80 }, () => finding());
  const f = fixture(report([{
    stage: "pdfStructure", outcome: "completed", findings
  }]));
  const display = createDisplay(f.target, f.host);
  assert.equal((await display.show(id)).warningsDisplayed, 64);
  assert.match(f.target.visibleText, /16 additional warnings not displayed/);
  findings[79].result.nextAction = "unsafeOpen";
  assert.equal((await display.show(id)).status, "unavailable");
  assert.equal(f.target.hidden, true);
  display.dispose();
});

test("stale async results never overwrite a newer request", async () => {
  const f = fixture();
  let release;
  f.host.readVerifiedDownloadScanReport = (requested) =>
    requested === "old" ? new Promise(resolve => { release = resolve; }) :
      Promise.resolve({ scanRequestId: requested, report: report() });
  const display = createDisplay(f.target, f.host);
  const old = display.show("old");
  assert.equal((await display.show("new")).status, "displayed");
  release({ scanRequestId: "old", report: report() });
  assert.equal((await old).status, "unavailable");
  assert.equal(f.target.hidden, false);
  assert.match(f.target.visibleText, /Structural warnings/);
  display.dispose();
});

test("clear, lost readiness and dispose remove the warning and prevent late display", async () => {
  const f = fixture();
  const display = createDisplay(f.target, f.host);
  assert.equal((await display.show(id)).status, "displayed");
  display.clear();
  assert.equal(f.target.hidden, true);
  assert.equal(f.target.attributes.role, undefined);
  assert.deepEqual(f.target.children, []);
  f.host.nativeScanResultsReady = false;
  assert.equal((await display.show(id)).status, "unavailable");
  f.host.nativeScanResultsReady = true;
  let release;
  f.host.readVerifiedDownloadScanReport = () =>
    new Promise(resolve => { release = resolve; });
  const pending = display.show(id);
  await tick();
  display.dispose();
  release({ scanRequestId: id, report: report() });
  assert.equal((await pending).status, "unavailable");
  assert.equal(f.target.hidden, true);
});

test("missing trust, invalid target, failing coordinator and malformed request IDs fail closed", async () => {
  assert.throws(() => createDisplay({}, {}), TypeError);
  const f = fixture();
  f.host.readVerifiedDownloadScanReport = async () => {
    throw Error("private scanner diagnostics");
  };
  const display = createDisplay(f.target, f.host);
  assert.equal((await display.show(id)).status, "unavailable");
  for (const bad of ["", "../private", "id with spaces", "x".repeat(81), null]) {
    assert.equal((await display.show(bad)).status, "unavailable");
  }
  assert.doesNotMatch(f.target.visibleText, /private scanner diagnostics/);
  display.dispose();
});

test("module is inert and never enables browser integration or file opening", async () => {
  const source = await readFile(new URL("../src/download-structural-warnings.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  for (const forbidden of ["innerHTML", "globalThis.chrome", "globalThis.browser",
    "downloads.open(", "connectNative(", "sendNativeMessage(", "scan_and_open",
    "clamscan", "fetch(", "localStorage", "node:fs"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
