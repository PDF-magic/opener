import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const base = new URL("../../../", import.meta.url);
const read = async path => readFile(new URL(path, base), "utf8");
const data = async () => JSON.parse(await read("docs/browser-automatic-interception-capabilities.json"));
const doc = async () => read("docs/browser-automatic-interception-research.md");
const manifest = async path => JSON.parse(await read(path));
const KEYS = [
  "brave", "chrome", "chromium", "edge", "vivaldi",
  "opera", "arc", "firefox", "safari"
];
const FAMILIES = {
  brave: "chromium", chrome: "chromium", chromium: "chromium",
  edge: "chromium", vivaldi: "chromium", opera: "chromium",
  arc: "chromium", firefox: "gecko", safari: "webkit"
};
const SOURCES = {
  brave: "brave.com", chrome: "developer.chrome.com",
  chromium: "developer.chrome.com", edge: "learn.microsoft.com",
  vivaldi: "help.vivaldi.com", opera: "help.opera.com",
  arc: "arc.net", firefox: "developer.mozilla.org",
  safari: "developer.apple.com"
};

test("all nine browser registry identifiers are represented exactly once", async () => {
  const matrix = await data();
  const registry = await read("browser_registry.py");
  const supported = {};
  for (const match of registry.matchAll(/^\s*"([a-z]+)": "([A-Za-z0-9.-]+)",?\s*$/gm)) {
    supported[match[1]] = match[2];
  }
  assert.equal(matrix.schemaVersion, 1);
  assert.match(matrix.reviewDate, /^2026-\d{2}-\d{2}$/);
  assert.equal(matrix.interceptionEnabled, false);
  assert.equal(matrix.allPathPreOpenVetoProven, false);
  assert.deepEqual(Object.keys(supported), KEYS);
  assert.deepEqual(matrix.browsers.map(row => row.id), KEYS);
  assert.deepEqual(Object.fromEntries(matrix.browsers.map(row =>
    [row.id, row.bundleId])), supported);
});

test("API research never claims universal scan-before-open capabilities", async () => {
  const matrix = await data();
  for (const row of matrix.browsers) {
    assert.equal(row.family, FAMILIES[row.id]);
    assert.equal(row.allPathPreOpenVetoProven, false);
    assert.equal(row.liveBrowserSecurityValidationRequired, true);
    assert.ok(["documented", "conditional"].includes(row.declarativeRules));
    assert.ok(["documented", "conditional", "not-established"].includes(row.downloadEvents));
    assert.ok(["documented", "policy-installed-only",
      "conditional-policy-installed-only", "not-established"].includes(row.blockingWebRequest));
    assert.ok(["documented-firefox-only", "not-established"].includes(row.responseBodyFilter));
    if (row.id !== "firefox") {
      assert.equal(row.responseBodyFilter, "not-established");
      assert.notEqual(row.blockingWebRequest, "documented");
    } else {
      assert.equal(row.responseBodyFilter, "documented-firefox-only");
      assert.equal(row.blockingWebRequest, "documented");
    }
    if (row.id === "safari") {
      assert.equal(row.blockingWebRequest, "not-established");
      assert.equal(row.downloadEvents, "not-established");
    }
  }
});

test("report contains every browser and links to two vendor/upstream sources", async () => {
  const matrix = await data(), markdown = await doc();
  assert.match(markdown, /opener-0777/);
  assert.match(markdown, /NOT an implementation/);
  assert.match(markdown, /No OS\/Finder\/all-open guarantee/);
  for (const row of matrix.browsers) {
    assert.ok(markdown.includes(row.name), row.id);
    assert.ok(markdown.includes(row.bundleId), row.id);
    assert.equal(row.primarySources.length, 2);
    assert.equal(new Set(row.primarySources).size, 2);
    assert.ok(row.primarySources.some(url =>
      new URL(url).hostname === SOURCES[row.id]), row.id);
    for (const url of row.primarySources) {
      assert.equal(new URL(url).protocol, "https:");
      assert.ok(markdown.includes(url), row.id + " missing " + url);
      assert.equal(url.includes("?"), false);
    }
  }
});

test("existing manifests and inert worker remain non-intercepting", async () => {
  const shared = await manifest("extensions/webextension/manifest.json");
  const safari = await manifest("extensions/safari/manifest.json");
  for (const m of [shared, safari]) {
    assert.equal(m.manifest_version, 3);
    assert.deepEqual(m.host_permissions, []);
    assert.equal(m.incognito, "not_allowed");
    assert.ok(!m.permissions.some(value =>
      /webRequest|declarativeNetRequest|downloads.open|debugger/.test(value)));
  }
  assert.deepEqual(shared.permissions, []);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.equal(shared.optional_host_permissions, undefined);
  const worker = await read("extensions/webextension/src/background.js");
  assert.match(worker, /void 0;/);
  assert.ok(!worker.includes("addListener("));
});
