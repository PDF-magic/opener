import assert from "node:assert/strict";
import { lstat, readFile } from "node:fs/promises";
import test from "node:test";
import {
  AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX,
  AUTOMATIC_INTERCEPTION_PDF_PATHS,
  assessAutomaticInterceptionReliability,
  assessAutomaticPdfInterception
} from "../src/automatic-interception-capability-matrix.js";
import { getPdfInterceptionPointAssessment } from "../src/pdf-interception-point-assessment.js";

const root = new URL("../../../", import.meta.url);
const read = path => readFile(new URL(path, root), "utf8");
const catalog = async () => JSON.parse(await read("docs/browser-unsupported-routes.json"));
const documentation = () => read("docs/browser-unsupported-routes.md");
const ADDITIONAL = [
  "extensionless-mime-or-filename",
  "cross-origin-frame-and-context-menu",
  "privileged-internal-or-custom-viewer",
  "authenticated-cookie-or-signed-url",
  "dynamic-or-page-generated-pdf",
  "native-download-and-open-controls",
  "malformed-or-oversized-remote-pdf",
  "worker-extension-or-browser-restart",
  "denied-revoked-or-missing-permission",
  "enterprise-policy-or-competing-extension",
  "scanner-unavailable-or-identity-mismatch",
  "unsupported-browser-or-unknown-entry"
];

test("catalog exactly covers existing runtime path and bypass inventories", async () => {
  const [data, source] = await Promise.all([
    catalog(), read("extensions/webextension/src/pdf-interception-point-assessment.js")
  ]);
  assert.equal(data.schemaVersion, 1);
  assert.equal(data.task, "opener-0813");
  assert.equal(data.effectiveInterceptionEnabled, false);
  assert.equal(data.allPathsBlocked, false);
  assert.match(data.scope, /not browser ability to view/i);
  assert.ok(data.statusDefinitions.uncontrolled.includes("may still open"));
  assert.ok(data.statusDefinitions.unverified.includes("not active"));

  // Detect additions to the runtime's otherwise private bypass-path array.
  const match = source.match(/const UNCONTROLLED_PATHS = Object.freeze\(\[([\s\S]*?)\]\);/u);
  assert.ok(match, "Cannot locate source-of-truth bypass paths");
  const bypass = [...match[1].matchAll(/"([^"]+)"/gu)].map(value => value[1]);
  const byKind = kind => data.routes.filter(row => row.kind === kind).map(row => row.id);
  assert.deepEqual(byKind("canonical"), [...AUTOMATIC_INTERCEPTION_PDF_PATHS]);
  assert.deepEqual(byKind("bypass"), bypass);
  assert.deepEqual(byKind("additional"), ADDITIONAL);
  assert.equal(new Set(data.routes.map(row => row.id)).size, data.routes.length);
  assert.equal(data.routes.length, 27);
});

test("all registered browsers and all catalog routes remain unverified for native interception", async () => {
  const [data, research, registry] = await Promise.all([
    catalog(), read("docs/browser-automatic-interception-capabilities.json").then(JSON.parse),
    read("browser_registry.py")
  ]);
  const ids = AUTOMATIC_INTERCEPTION_CAPABILITY_MATRIX.map(row => row.id);
  const supported = [...registry.matchAll(/^\s*"([a-z]+)": "([A-Za-z0-9.-]+)",?\s*$/gmu)]
    .map(match => [match[1], match[2]]);
  assert.deepEqual(research.browsers.map(row => [row.id, row.bundleId]), supported);
  assert.deepEqual(ids, supported.map(row => row[0]));
  assert.equal(ids.length, 9);
  assert.equal(research.interceptionEnabled, false);
  assert.equal(research.allPathPreOpenVetoProven, false);
  for (const id of ids) {
    const point = getPdfInterceptionPointAssessment(id);
    assert.equal(point.automaticInterceptionEnabled, false, id);
    assert.equal(point.allPdfOpeningPathsBlocked, false, id);
    assert.equal(point.fullResponseHeldForTrustedNativeScan, false, id);
    assert.equal(assessAutomaticPdfInterception(id).automaticInterceptionEnabled, false);
    for (const path of AUTOMATIC_INTERCEPTION_PDF_PATHS) {
      const verdict = assessAutomaticInterceptionReliability(id, path);
      assert.equal(verdict.automaticInterceptionDisabled, true, id + ":" + path);
      assert.equal(verdict.authorizesScan, false);
      assert.equal(verdict.authorizesOpen, false);
    }
  }
  assert.equal(assessAutomaticInterceptionReliability("unknown-browser").authorizesOpen, false);
  assert.equal(assessAutomaticInterceptionReliability("firefox", "unknown-route").authorizesScan, false);
  assert.ok(data.routes.every(row => ["uncontrolled", "unverified"].includes(row.status)));
});

test("every route is described once with an existing nonsensitive evidence link", async () => {
  const [data, markdown] = await Promise.all([catalog(), documentation()]);
  assert.match(markdown, /^# Known unsupported and unverified PDF entry routes \(opener-0813\)/);
  const section = markdown.split("## Entry-route register\n")[1]?.split("## What existing browser tests actually verify")[0];
  assert.ok(section, "Missing route table");
  for (const row of data.routes) {
    assert.match(row.id, /^[a-z][a-z0-9-]+$/);
    assert.ok(["canonical", "bypass", "additional"].includes(row.kind));
    assert.ok(["uncontrolled", "unverified"].includes(row.status));
    assert.ok(row.limitation.length >= 35 && row.limitation.length <= 400);
    assert.ok(Array.isArray(row.evidence) && row.evidence.length >= 1 && row.evidence.length <= 2);
    const prefix = "| `" + row.id + "` | " + row.kind + " | **" + row.status + "** |";
    assert.equal(section.split(prefix).length - 1, 1, row.id + " missing or repeated");
    assert.ok(section.includes(row.limitation), row.id + " lost explanation");
    assert.equal(new Set(row.evidence).size, row.evidence.length, row.id);
    for (const evidence of row.evidence) {
      // Check only referenced repository documentation and source, not any
      // secrets, local profiles, or fixture PDFs.
      assert.match(evidence, /^(?:docs\/|extensions\/webextension\/|browser_registry\.py$)[a-zA-Z0-9/_.-]*$/);
      assert.doesNotMatch(evidence, /\.\.|secret|credential|token|password|\.env|\.pem|\.key/i);
      const path = new URL(evidence, root);
      const metadata = await lstat(path);
      assert.ok(metadata.isFile(), evidence);
      assert.ok(section.includes("](../" + evidence + ")"), row.id + ": " + evidence);
    }
  }
  const actualRows = [...section.matchAll(/^\| `([a-z][a-z0-9-]*)` \| (canonical|bypass|additional) \|/gmu)];
  assert.equal(actualRows.length, data.routes.length);
});

test("browser guidance distinguishes documented APIs, unsupported routes and real viewer tests", async () => {
  const [doc, research] = await Promise.all([
    documentation(), read("docs/browser-automatic-interception-capabilities.json").then(JSON.parse)
  ]);
  const browserSection = doc.split("## Browser-by-browser deployment limits\n")[1]
    ?.split("## Entry-route register")[0];
  assert.ok(browserSection);
  for (const browser of research.browsers) {
    assert.equal(browserSection.split("| `" + browser.id + "` |").length - 1, 1);
    assert.ok(browserSection.includes(browser.name), browser.id);
    assert.equal(browser.allPathPreOpenVetoProven, false);
  }
  for (const phrase of [
    "DNR", "Firefox", "Safari", "Chrome", "Edge", "Finder",
    "native ClamAV", "scan-before-render", "disposable",
    "does not control all browser/OS paths", "user's verified chosen application",
    "unsupported or unverified", "not a successful scan"
  ]) assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
  assert.match(doc, /no such interception route is active/i);
  assert.match(doc, /unverified and fail closed/i);
});

test("documentation is CI-guarded and does not activate extension permissions or scanner", async () => {
  const [ci, pkg, manifest, safari, background, index] = await Promise.all([
    read(".github/workflows/ci.yml"), read("extensions/webextension/package.json").then(JSON.parse),
    read("extensions/webextension/manifest.json").then(JSON.parse),
    read("extensions/safari/manifest.json").then(JSON.parse),
    read("extensions/webextension/src/background.js"),
    read("docs/README.md")
  ]);
  assert.match(ci, /node --test tests\/browser-unsupported-routes\.test\.mjs/);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.match(index, /\[Known unsupported PDF routes\]\(browser-unsupported-routes\.md\)/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.doesNotMatch(background, /addListener\(|connectNative\(|fetch\(/);
});
