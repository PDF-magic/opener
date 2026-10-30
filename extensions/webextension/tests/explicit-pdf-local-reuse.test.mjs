import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { planExplicitPdfLocalReuse } from "../src/explicit-pdf-local-reuse.js";

const selected = "pdf_choice_4";
const snapshot = () => ({
  selectionId: selected, documentRevision: 3, pdfIdentified: true,
  currentDocumentVerified: true, selectionVerified: true,
  permissionGranted: true, userInitiated: true
});
const available = () => ({
  selectionId: selected, documentRevision: 3, status: "verified-local",
  identityVerified: true, transferComplete: true, fileStable: true
});
const absent = () => ({
  selectionId: selected, documentRevision: 3, status: "not-present"
});
const coordinator = () => ({
  localPdfReuseReady: true,
  readCurrentPdfSelection: snapshot,
  inspectExistingLocalPdf: async () => available()
});

test("the default is fail-closed with no download, scanning or opening authority", async () => {
  const result = await planExplicitPdfLocalReuse();
  assert.deepEqual(result, {
    status: "unavailable", canReuseLocal: false, requiresAcquisition: false,
    downloadStarted: false, authorizesDownload: false,
    scanVerified: false, authorizesScan: false, authorizesOpen: false
  });
  assert.ok(Object.isFrozen(result));
});

test("a verified matching and complete local PDF is reused without fetching", async () => {
  let calls = 0;
  const trusted = coordinator();
  trusted.inspectExistingLocalPdf = async (identity) => {
    calls += 1;
    assert.deepEqual(identity, { selectionId: selected, documentRevision: 3 });
    assert.ok(Object.isFrozen(identity));
    return available();
  };
  const result = await planExplicitPdfLocalReuse({ coordinator: trusted, selectionId: selected });
  assert.equal(calls, 1);
  assert.deepEqual(result, {
    status: "reuse-existing-local", canReuseLocal: true, requiresAcquisition: false,
    downloadStarted: false, authorizesDownload: false,
    scanVerified: false, authorizesScan: false, authorizesOpen: false
  });
  assert.ok(Object.isFrozen(result));
  assert.equal(JSON.stringify(result).includes(selected), false);
});

test("only an affirmative absence proposes acquisition, but never starts it", async () => {
  const trusted = coordinator();
  let acquisitionCalls = 0;
  trusted.downloadPdfAgain = () => acquisitionCalls++;
  trusted.inspectExistingLocalPdf = async () => absent();
  const result = await planExplicitPdfLocalReuse({ coordinator: trusted, selectionId: selected });
  assert.equal(result.status, "source-acquisition-needed");
  assert.equal(result.requiresAcquisition, true);
  assert.equal(result.authorizesDownload, false);
  assert.equal(result.downloadStarted, false);
  assert.equal(acquisitionCalls, 0);
});

test("partial, mismatched, unstable and unverified files never trigger redownload", async () => {
  const trusted = coordinator();
  for (const response of [
    { ...available(), transferComplete: false },
    { ...available(), fileStable: false },
    { ...available(), identityVerified: "true" },
    { ...available(), selectionId: "different" },
    { ...available(), documentRevision: 4 },
    { ...available(), localPath: "/private/data.pdf" },
    { ...absent(), unexpected: true },
    { ...absent(), status: "incomplete" },
    { ...absent(), status: "permission-revoked" },
    null, {}, [], "verified-local"
  ]) {
    trusted.inspectExistingLocalPdf = async () => response;
    const result = await planExplicitPdfLocalReuse({ coordinator: trusted, selectionId: selected });
    assert.equal(result.status, "unavailable");
    assert.equal(result.requiresAcquisition, false);
  }
});

test("current PDF, explicit intent, identity and permission are mandatory", async () => {
  const trusted = coordinator();
  for (const field of [
    "pdfIdentified", "currentDocumentVerified", "selectionVerified",
    "permissionGranted", "userInitiated"
  ]) {
    trusted.readCurrentPdfSelection = () => ({ ...snapshot(), [field]: false });
    assert.equal((await planExplicitPdfLocalReuse({
      coordinator: trusted, selectionId: selected
    })).status, "unavailable", field);
  }
  for (const bad of ["/downloads/file.pdf", "https://example.test/a.pdf", "", "a".repeat(81),
    true, null, "../pdf", "pdf id"]) {
    trusted.readCurrentPdfSelection = snapshot;
    assert.equal((await planExplicitPdfLocalReuse({
      coordinator: trusted, selectionId: bad
    })).status, "unavailable");
  }
});

test("navigation or document changes during awaited inspection invalidate reuse", async () => {
  const trusted = coordinator();
  let complete;
  trusted.inspectExistingLocalPdf = () => new Promise(resolve => { complete = resolve; });
  const pending = planExplicitPdfLocalReuse({ coordinator: trusted, selectionId: selected });
  trusted.readCurrentPdfSelection = () => ({ ...snapshot(), documentRevision: 4 });
  complete(available());
  assert.equal((await pending).status, "unavailable");
  trusted.readCurrentPdfSelection = snapshot;
  trusted.inspectExistingLocalPdf = async () => available();
  trusted.localPdfReuseReady = false;
  assert.equal((await planExplicitPdfLocalReuse({
    coordinator: trusted, selectionId: selected
  })).status, "unavailable");

  // Even if a replacement callback returns the original-looking selection,
  // it may belong to another document or session. Never trust the old one.
  trusted.localPdfReuseReady = true;
  let finish;
  trusted.inspectExistingLocalPdf = () => new Promise(resolve => { finish = resolve; });
  const next = planExplicitPdfLocalReuse({ coordinator: trusted, selectionId: selected });
  trusted.inspectExistingLocalPdf = async () => available();
  finish(available());
  assert.equal((await next).status, "unavailable");
});

test("untrusted accessors, inherited evidence, proxies and native failures fail closed", async () => {
  const trusted = coordinator();
  const getter = snapshot();
  Object.defineProperty(getter, "pdfIdentified", {
    get() { throw Error("never invoke page getter"); }
  });
  const bad = [
    getter,
    Object.create(snapshot()),
    new Proxy({}, { ownKeys() { throw Error("proxy"); } }),
    Promise.resolve(snapshot()),
    { ...snapshot(), unexpected: "path" }
  ];
  for (const value of bad) {
    trusted.readCurrentPdfSelection = () => value;
    assert.equal((await planExplicitPdfLocalReuse({
      coordinator: trusted, selectionId: selected
    })).status, "unavailable");
  }
  trusted.readCurrentPdfSelection = snapshot;
  const inspected = available();
  Object.defineProperty(inspected, "fileStable", {
    get() { throw Error("/private/secret.pdf"); }
  });
  trusted.inspectExistingLocalPdf = async () => inspected;
  assert.equal((await planExplicitPdfLocalReuse({
    coordinator: trusted, selectionId: selected
  })).status, "unavailable");
  trusted.inspectExistingLocalPdf = async () => { throw Error("/private/secret.pdf"); };
  const outcome = await planExplicitPdfLocalReuse({ coordinator: trusted, selectionId: selected });
  assert.equal(outcome.status, "unavailable");
  assert.equal(JSON.stringify(outcome).includes("secret"), false);
});

test("does not modify browser privileges, fetch documents or scan cached PDFs", async () => {
  const source = await readFile(new URL("../src/explicit-pdf-local-reuse.js", import.meta.url), "utf8");
  for (const forbidden of [
    "fetch(", "XMLHttpRequest", "chrome.", "browser.", "sendNativeMessage(",
    "connectNative(", "window.open(", "addListener(", "node:fs",
    "localStorage", "node:crypto"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  const manifest = JSON.parse(await readFile(
    new URL("../manifest.json", import.meta.url), "utf8"
  ));
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.match(background, /Inactive shared WebExtensions background/);
});
