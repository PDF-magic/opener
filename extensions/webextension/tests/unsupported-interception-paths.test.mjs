import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { getBrowserCapabilityFlags } from "../src/browser-capabilities.js";
import {
  assessDownloadOpeningBeforeMonitoringCompletes as assess
} from "../src/download-early-open-assessment.js";

const supportGuide = new URL("../../../docs/download-opening-browser-support.md", import.meta.url);
const sharedManifest = new URL("../manifest.json", import.meta.url);
const safariManifest = new URL("../../safari/manifest.json", import.meta.url);

const unsupportedPaths = new Map([
  ["Brave (default)", ["Download shelf", "embedded PDF viewer", "OS opening"]],
  ["Google Chrome", ["Download bubble", "automatic open", "embedded viewer", "OS opening"]],
  ["Chromium", ["Download manager", "embedded viewer", "OS opening"]],
  ["Microsoft Edge", ["Download manager", "embedded viewer", "OS opening"]],
  ["Vivaldi", ["Download manager", "embedded viewer", "OS opening"]],
  ["Opera", ["Download manager", "embedded viewer", "OS opening"]],
  ["Arc", ["Download UI", "embedded viewer", "OS opening"]],
  ["Mozilla Firefox", ["Downloads panel", "PDF.js", "OS opening"]],
  ["Apple Safari", ["Safari inline PDF viewer", "Downloads UI", "Finder"]]
]);

function strictRows(guide) {
  const section = guide.split("## Strict pre-open interception availability (opener-0717)")[1]
    ?.split("\n## What can actually be enforced?")[0];
  assert.ok(section, "documented strict interception report is required");
  return section.split("\n").filter(line => line.startsWith("| ") &&
    !line.startsWith("| ---") && !line.startsWith("| Browser |"));
}

function eventSource() {
  const listeners = new Set();
  return {
    addListener(callback) { listeners.add(callback); },
    removeListener(callback) { listeners.delete(callback); },
    get count() { return listeners.size; }
  };
}

function browserFixture(rows) {
  const searches = [];
  const downloads = {
    onCreated: eventSource(), onChanged: eventSource(), onErased: eventSource(),
    search(query) {
      searches.push(query);
      return Promise.resolve(rows);
    },
    open() { throw new Error("unapproved browser opening"); },
    pause() { throw new Error("unapproved browser pause"); },
    cancel() { throw new Error("unapproved browser cancellation"); }
  };
  const permissions = {
    onRemoved: eventSource(),
    contains() { return Promise.resolve(true); },
    request() { throw new Error("unexpected permission request"); }
  };
  return { downloads, permissions, searches };
}

const pending = Object.freeze({ kind: "monitoring-pending", id: 7 });
const completed = Object.freeze({
  id: 7, state: "complete", exists: true, paused: false, canResume: false,
  danger: "safe", filename: "/private/untrusted.pdf"
});

function assertNotEnforced(report, fixture) {
  assert.equal(report.openingBlocked, false);
  assert.equal(report.scanVerified, false);
  assert.equal(report.authorizesOpen, false);
  assert.equal(JSON.stringify(report).includes("/private/"), false);
  assert.deepEqual(fixture.searches, [{ id: 7 }]);
  for (const name of ["onCreated", "onChanged", "onErased"]) {
    assert.equal(fixture.downloads[name].count, 0, name);
  }
  assert.equal(fixture.permissions.onRemoved.count, 0);
}

test("unsupported interception report identifies each independent browser/OS bypass", async () => {
  const guide = await readFile(supportGuide, "utf8");
  const rows = strictRows(guide);
  assert.equal(rows.length, unsupportedPaths.size);
  const seen = new Set();
  for (const line of rows) {
    const cells = line.split("|").slice(1, -1).map(cell => cell.trim());
    assert.equal(cells.length, 3, line);
    const [browser, status, paths] = cells;
    assert.equal(seen.has(browser), false, browser);
    seen.add(browser);
    assert.ok(unsupportedPaths.has(browser), `unexpected browser: ${browser}`);
    for (const path of unsupportedPaths.get(browser)) {
      assert.ok(paths.includes(path), `${browser}: missing ${path}`);
    }
    if (browser === "Apple Safari") {
      assert.match(status, /^\*\*Unverified; treat as unavailable\*\*/);
      assert.doesNotMatch(status, /proven impossible|confirmed unsupported/i);
    } else {
      assert.match(status, /^\*\*Unavailable\*\*/);
    }
    assert.doesNotMatch(status, /supported|enabled|enforced|guaranteed/i);
  }
  assert.deepEqual(seen, new Set(unsupportedPaths.keys()));
  for (const bypass of ["other extensions", "automatic-open", "inline", "Finder"]) {
    assert.ok(guide.includes(bypass), `undocumented bypass: ${bypass}`);
  }
  assert.match(guide, /not browser-wide strict interception/);
});

test("download-event API presence cannot be reported as a strict open veto", async () => {
  const event = () => ({ addListener() {}, removeListener() {} });
  const capabilities = getBrowserCapabilityFlags({
    downloads: { onCreated: event(), onChanged: event(), onErased: event() }
  });
  assert.equal(capabilities.downloadEventsApi, true);
  assert.equal(capabilities.pdfOpeningEnabled, false);
  assert.equal(capabilities.scannerVerificationEnabled, false);
  assert.equal(capabilities.nativeMessagingEnabled, false);
  const [shared, safari] = await Promise.all([sharedManifest, safariManifest]
    .map(url => readFile(url, "utf8").then(JSON.parse)));
  for (const manifest of [shared, safari]) {
    assert.equal(manifest.permissions.includes("downloads.open"), false);
    assert.equal((manifest.optional_permissions || []).includes("downloads.open"), false);
  }
});

test("browser-owned completion reports possible opening, never enforced opening safety", async () => {
  for (const path of ["download bubble", "download history", "automatic download opening"]) {
    const f = browserFixture([completed]);
    const report = await assess(f.downloads, f.permissions, pending);
    assert.equal(report.status, "opening-possible", path);
    assert.equal(report.browserMayOpenBeforeMonitoringCompletes, true, path);
    assertNotEnforced(report, f);
  }
});

test("inline viewers and Finder cannot be claimed blocked without a download record", async () => {
  for (const path of ["inline PDF viewer", "Finder", "other applications"]) {
    const f = browserFixture([]);
    const report = await assess(f.downloads, f.permissions, pending);
    assert.equal(report.status, "unknown", path);
    assert.equal(report.browserMayOpenBeforeMonitoringCompletes, null, path);
    assertNotEnforced(report, f);
  }
});

test("partial, interrupted and untrusted browser states never report protection", async () => {
  for (const [rows, expected] of [
    [[{ ...completed, state: "in_progress" }], "transfer-in-progress"],
    [[{ ...completed, state: "interrupted" }], "transfer-interrupted"],
    [[{ ...completed, exists: false }], "unknown"],
    [[{ ...completed, id: 8 }], "unknown"],
    [[{ ...completed, error: "NETWORK_FAILED" }], "unknown"]
  ]) {
    const f = browserFixture(rows);
    const report = await assess(f.downloads, f.permissions, pending);
    assert.equal(report.status, expected);
    assertNotEnforced(report, f);
  }
});
