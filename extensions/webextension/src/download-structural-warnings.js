// Passive, opt-in warning display for a trusted, correlated native scan report.
// Browser download metadata cannot establish structural findings or malware.
const REQUEST_ID = /^[A-Za-z0-9_-]{1,80}$/u;
const MAX_ROWS = 64;
const STAGES = Object.freeze({
  pdfStructure: "PDF structure", objectRelationships: "Object relationships",
  embeddedFiles: "Embedded files", automaticActions: "Automatic actions",
  javascriptActions: "JavaScript actions", formActions: "Form actions",
  annotations: "Annotations", incrementalRevisions: "Incremental revisions",
  embeddedUrls: "Embedded URLs", malformedStructures: "Malformed structures",
  ambiguousStructures: "Ambiguous structures", executableContent: "Executable content"
});
const CODES = Object.freeze({
  malformedStructure: "Malformed structure",
  conflictingStructure: "Conflicting structure",
  unresolvedReference: "Unresolved reference",
  knownMaliciousContent: "Known malicious content",
  activeContent: "Active content", suspiciousUrl: "Suspicious URL",
  unexpectedEmbeddedFile: "Unexpected embedded file",
  incrementalRevision: "Incremental revision",
  unsupportedFeature: "Unsupported feature", resourceLimit: "Resource limit",
  inspectionFailure: "Inspection failure"
});
const SEVERITIES = Object.freeze({
  informational: "Information", reviewRequired: "Review required",
  suspicious: "Suspicious", critical: "Critical", blocking: "Blocking"
});
const ACTIONS = Object.freeze({
  recorded: "continueRequiredChecks",
  reviewRequired: "requestReviewBeforeOpening",
  blocking: "stopOpening",
  inspectionIncomplete: "rerunOrRepairInspection"
});
const STATUSES = Object.freeze([
  "clean", "malwareDetected", "suspiciousStructure", "encrypted",
  "incompleteScan", "scanFailed", "scanTimedOut", "fileChanged",
  "fileTooLarge", "cancelled"
]);
const unavailable = Object.freeze({
  status: "unavailable", warningsDisplayed: 0, authorizesOpen: false
});
const empty = Object.freeze({
  status: "no-warnings", warningsDisplayed: 0, authorizesOpen: false
});

function own(record, key) {
  if (record === null || typeof record !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function exact(record, keys) {
  if (record === null || typeof record !== "object" || Array.isArray(record) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(record))) return false;
  const actual = Reflect.ownKeys(record);
  return actual.length === keys.length && keys.every(key => actual.includes(key) &&
    Object.hasOwn(Object.getOwnPropertyDescriptor(record, key), "value"));
}

function values(array, maximum, allowEmpty = true) {
  if (!Array.isArray(array) || array.length > maximum ||
      (!allowEmpty && array.length === 0) ||
      Reflect.ownKeys(array).length !== array.length + 1) return null;
  const items = [];
  for (let i = 0; i < array.length; i += 1) {
    const descriptor = Object.getOwnPropertyDescriptor(array, String(i));
    if (!descriptor || !Object.hasOwn(descriptor, "value")) return null;
    items.push(descriptor.value);
  }
  return items;
}

function expectedResult(code, severity) {
  if (code === "knownMaliciousContent") return "blocking";
  if (code === "resourceLimit" || code === "inspectionFailure") {
    return "inspectionIncomplete";
  }
  if (severity === "critical" || severity === "blocking") return "blocking";
  if (severity === "reviewRequired" || severity === "suspicious") return "reviewRequired";
  return "recorded";
}

function warningRows(response, requestId) {
  if (!exact(response, ["scanRequestId", "report"]) ||
      own(response, "scanRequestId") !== requestId) return null;
  const report = own(response, "report");
  if (!exact(report, ["schemaVersion", "authorizesOpen", "requiresBlock",
    "scan", "clamav", "structuralFindings"]) ||
    own(report, "schemaVersion") !== 1 || own(report, "authorizesOpen") !== false ||
    typeof own(report, "requiresBlock") !== "boolean") return null;
  const scan = own(report, "scan"), clamav = own(report, "clamav");
  if (!exact(scan, ["status"]) || !STATUSES.includes(own(scan, "status")) ||
      !exact(clamav, ["effectivePolicyId", "detectionNames"]) ||
      own(clamav, "effectivePolicyId") !== "built-in") return null;
  const names = values(own(clamav, "detectionNames"), 256);
  if (!names || names.some(name => typeof name !== "string" ||
      !/^[A-Za-z0-9][A-Za-z0-9._!+@-]{0,254}$/u.test(name)) ||
      new Set(names).size !== names.length ||
      (own(scan, "status") === "clean" && names.length !== 0)) return null;

  const structural = own(report, "structuralFindings");
  if (!exact(structural, ["schemaVersion", "authorizesOpen", "requiresBlock",
      "stageResults"]) ||
      own(structural, "schemaVersion") !== 2 ||
      own(structural, "authorizesOpen") !== false ||
      typeof own(structural, "requiresBlock") !== "boolean") return null;
  const stages = values(own(structural, "stageResults"), 32, false);
  if (!stages) return null;
  const seen = new Set(), rows = [];
  let count = 0, computedBlock = false;

  // Validate EVERY row before rendering, including rows past the display cap.
  for (const stage of stages) {
    if (!exact(stage, ["stage", "outcome", "findings"])) return null;
    const key = own(stage, "stage"), outcome = own(stage, "outcome");
    if (!Object.hasOwn(STAGES, key) || seen.has(key) ||
        !["completed", "incomplete", "notRun"].includes(outcome)) return null;
    seen.add(key);
    const findings = values(own(stage, "findings"), 128);
    if (!findings || (outcome === "notRun" && findings.length !== 0)) return null;
    if (outcome !== "completed") {
      computedBlock = true;
      count += 1;
      if (rows.length < MAX_ROWS) rows.push(
        STAGES[key] + ": inspection " + (outcome === "notRun" ? "not run" : "incomplete")
      );
    }
    for (const finding of findings) {
      if (!exact(finding, ["code", "findingId", "severity", "objectNumber",
        "pageNumber", "result"]) &&
        !exact(finding, ["code", "findingId", "severity", "objectNumber",
          "pageNumber", "objectReference", "result"])) return null;
      const code = own(finding, "code"), severity = own(finding, "severity");
      if (!Object.hasOwn(CODES, code) || !Object.hasOwn(SEVERITIES, severity)) return null;
      const result = own(finding, "result");
      if (!exact(result, ["outcome", "explanation", "nextAction", "malwareAssessment"]) &&
          !exact(result, ["outcome", "explanation", "nextAction"])) return null;
      const outcomeId = own(result, "outcome");
      if (outcomeId !== expectedResult(code, severity) ||
          own(result, "nextAction") !== ACTIONS[outcomeId] ||
          (own(result, "malwareAssessment") !== undefined &&
            own(result, "malwareAssessment") !== "notConfirmed")) return null;
      // Ignore all PDF-controlled or provider-supplied explanation and location
      // fields; output only fixed, locally authored labels.
      if (outcomeId !== "recorded") {
        computedBlock = true;
        count += 1;
        if (rows.length < MAX_ROWS) rows.push(
          STAGES[key] + " · " + SEVERITIES[severity] + " · " + CODES[code] +
          " — " + (outcomeId === "blocking" ? "Opening stopped" :
            outcomeId === "inspectionIncomplete" ? "Inspection incomplete" :
            "Review required")
        );
      }
    }
  }
  if (computedBlock !== own(structural, "requiresBlock") ||
      own(report, "requiresBlock") !== (
        own(scan, "status") !== "clean" || names.length !== 0 || computedBlock
      )) return null;
  return Object.freeze({ count, rows: Object.freeze(rows) });
}

function validRoot(root) {
  try {
    return root?.nodeType === 1 &&
      typeof root.ownerDocument?.createElement === "function" &&
      typeof root.replaceChildren === "function" &&
      typeof root.setAttribute === "function" &&
      typeof root.removeAttribute === "function";
  } catch {
    return false;
  }
}

/**
 * Display structural warnings ONLY from an independently trusted,
 * authenticated coordinator's correlated combined scan report. The readiness
 * flag is not authentication; the caller must establish trust separately.
 */
export function createDownloadStructuralWarningsDisplay(root, coordinator) {
  if (!validRoot(root)) throw new TypeError("An extension-owned display element is required");
  let active = true, generation = 0;

  function hide() {
    root.replaceChildren();
    root.hidden = true;
    root.removeAttribute("role");
  }

  function clear() {
    generation += 1;
    hide();
  }

  async function show(scanRequestId) {
    const ticket = ++generation;
    hide();
    try {
      if (!active || typeof scanRequestId !== "string" ||
          !REQUEST_ID.test(scanRequestId) ||
          own(coordinator, "nativeScanResultsReady") !== true) return unavailable;
      const reader = own(coordinator, "readVerifiedDownloadScanReport");
      if (typeof reader !== "function") return unavailable;
      const pending = reader.call(coordinator, scanRequestId);
      if (!pending || typeof pending.then !== "function") return unavailable;
      const response = await pending;
      if (!active || generation !== ticket ||
          own(coordinator, "nativeScanResultsReady") !== true) return unavailable;
      const warnings = warningRows(response, scanRequestId);
      if (warnings === null) return unavailable;
      if (warnings.count === 0) return empty;

      const doc = root.ownerDocument;
      const heading = doc.createElement("strong");
      heading.textContent = "Structural warnings — review required";
      const explanation = doc.createElement("p");
      explanation.textContent =
        "PDF structure inspection reported concerns or incomplete checks. " +
        "These findings are not malware confirmation and never authorize opening.";
      const list = doc.createElement("ul");
      for (const row of warnings.rows) {
        const item = doc.createElement("li");
        item.textContent = row;
        list.appendChild(item);
      }
      const nodes = [heading, explanation, list];
      if (warnings.count > warnings.rows.length) {
        const remaining = doc.createElement("p");
        remaining.textContent =
          String(warnings.count - warnings.rows.length) + " additional warnings not displayed";
        nodes.push(remaining);
      }
      if (!active || ticket !== generation ||
          own(coordinator, "nativeScanResultsReady") !== true) return unavailable;
      root.replaceChildren(...nodes);
      root.setAttribute("role", "alert");
      root.hidden = false;
      return Object.freeze({
        status: "displayed", warningsDisplayed: warnings.rows.length,
        authorizesOpen: false
      });
    } catch {
      if (active && ticket === generation) hide();
      return unavailable;
    }
  }

  function dispose() {
    if (!active) return;
    active = false;
    clear();
  }

  hide();
  return Object.freeze({ show, clear, dispose });
}
