import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createBraveViewerTestPdf } from "../scripts/brave-pdf-viewer-fixture.mjs";

const read = path => readFile(new URL(path, import.meta.url), "utf8");

test("the isolated Brave PDF fixture has valid cross-reference offsets and text-only content", () => {
  const first = createBraveViewerTestPdf();
  const second = createBraveViewerTestPdf();
  assert.ok(Buffer.isBuffer(first));
  assert.deepEqual(first, second, "the fixture must be deterministic");
  assert.ok(first.length < 4096, "keep generated PDF small and bounded");
  const document = first.toString("ascii");
  assert.ok(document.startsWith("%PDF-1.4\n"));
  assert.ok(document.endsWith("%%EOF\n"));
  assert.match(document, /\/Type \/Page\b/);
  assert.match(document, /Brave built-in PDF viewer smoke test/);
  assert.doesNotMatch(document, /\/(JavaScript|JS|OpenAction|AA|EmbeddedFile|URI|Launch)\b/);
  const match = document.match(/\nstartxref\n([0-9]+)\n%%EOF\n$/);
  assert.ok(match);
  const xref = Number(match[1]);
  assert.equal(document.slice(xref, xref + 9), "xref\n0 6\n");
  const lines = document.slice(xref).split("\n");
  assert.equal(lines[1], "0 6");
  assert.equal(lines[2], "0000000000 65535 f ");
  for (let i = 1; i <= 5; i++) {
    const offset = Number(lines[i + 2].slice(0, 10));
    assert.ok(Number.isSafeInteger(offset) && offset > 0);
    assert.equal(document.slice(offset, offset + 7), String(i) + " 0 obj");
  }
});

test("Brave's real built-in PDF viewer is exercised in a separate headed CI step", async () => {
  const [workflow, smoke, manifest, background, pkg] = await Promise.all([
    read("../../../.github/workflows/brave-webextension.yml"),
    read("../scripts/smoke-brave-pdf-viewer.mjs"),
    read("../manifest.json").then(JSON.parse),
    read("../src/background.js"),
    read("../package.json").then(JSON.parse)
  ]);
  for (const requirement of [
    "brave-browser", "playwright-core", "launchPersistentContext",
    "headless: false", "127.0.0.1", "createBraveViewerTestPdf",
    "Content-Type", "application/pdf", "Content-Disposition",
    "inline", "page.goto(", 'embed[type="application/pdf"]',
    'state: "attached"', "downloads", "context?.close()",
    "rm(profile", "server.close", "chrome.permissions.contains"
  ]) assert.ok(smoke.includes(requirement), requirement);
  for (const requirement of [
    "Install official Brave stable browser",
    "xvfb-run -a node scripts/smoke-brave-pdf-viewer.mjs",
    "node --test tests/brave-compatibility.test.mjs tests/brave-pdf-viewer.test.mjs",
    "BRAVE_BROWSER_PATH: /usr/bin/brave-browser"
  ]) assert.ok(workflow.includes(requirement), requirement);
  assert.doesNotMatch(smoke, /chromium\.launch\(/);
  for (const dangerous of [
    "sendNativeMessage(", "connectNative(", "downloads.open(",
    "permissions.request(", "window.open(", "fetch(", "node:child_process",
    "localStorage", "sessionStorage"
  ]) assert.ok(!smoke.includes(dangerous), dangerous);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
});

test("Brave viewer documentation distinguishes verified CI behavior from scanner enforcement", async () => {
  const doc = await read("brave/README.md");
  for (const phrase of [
    "opener-0801", "built-in PDF viewer", "Xvfb",
    "localhost", "synthetic", "inline", "not",
    "scanner", "user", "CI"
  ]) assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
});
