import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const researchPath = new URL(
  "../../../docs/browser-interception-apis.md", import.meta.url);
const supportPath = new URL(
  "../../../docs/download-opening-browser-support.md", import.meta.url);
const sharedManifestPath = new URL("../manifest.json", import.meta.url);
const safariManifestPath = new URL("../../safari/manifest.json", import.meta.url);
const backgroundPath = new URL("../src/background.js", import.meta.url);
const read = async () => {
  const [research, support, sharedSource, safariSource, background] =
    await Promise.all([researchPath, supportPath, sharedManifestPath,
      safariManifestPath, backgroundPath].map(path => readFile(path, "utf8")));
  return {
    research, support,
    shared: JSON.parse(sharedSource), safari: JSON.parse(safariSource),
    background
  };
};

test("each candidate interception mechanism is evaluated exactly once", async () => {
  const { research } = await read();
  const rows = research.split("\n").filter(row => row.startsWith("| ") &&
    row.includes(" | ") && !row.startsWith("| ---") &&
    !row.startsWith("| Mechanism"));
  const candidates = [
    "`downloads.onCreated`",
    "`downloads.onDeterminingFilename`",
    "`downloads.pause`",
    "`declarativeNetRequest`",
    "`webRequest` observation",
    "Blocking `webRequest.onBeforeRequest`",
    "`webRequest.filterResponseData`",
    "Browser enterprise policy",
    "Native macOS verified handoff"
  ];
  assert.equal(rows.length, candidates.length);
  for (const candidate of candidates) {
    assert.equal(rows.filter(row => row.startsWith("| " + candidate)).length, 1,
      candidate);
  }
  for (const row of rows) assert.equal(row.split(" | ").length, 4, row);
});

test("network interception does not claim to gate every downloaded-file open", async () => {
  const { research } = await read();
  for (const term of [
    "not an interlock", "not a universal file-open hook",
    "not a cross-browser API", "not an antivirus scan callback",
    "a universal completion/open veto",
    "browser downloads UI", "inline PDF viewing", "Finder",
    "other applications", "all local file opening",
    "not a synchronous open veto"
  ]) assert.ok(research.toLowerCase().includes(term.toLowerCase()), term);
  assert.match(research, /No\s+WebExtension interception API here supplies the last guarantee/);
  assert.match(research, /not “all PDFs are\s*scanned before they can be opened/);
});

test("Chrome MV3, Firefox and Safari have distinct documented interception conditions", async () => {
  const { research } = await read();
  for (const [term, status] of [
    ["webRequestBlocking", "policy-installed extensions"],
    ["Firefox", "filterResponseData"],
    ["Firefox", "Promise-based"],
    ["Safari", "declarativeNetRequest"],
    ["Brave, Edge, Vivaldi, Opera and Arc", "conditional"]
  ]) {
    assert.ok(research.includes(term), term);
    assert.ok(research.includes(status), status);
  }
  assert.match(research, /Chrome MV3[\s\S]*?policy-installed extensions/);
  assert.match(research, /Firefox:[\s\S]*?webRequestBlocking/);
  assert.match(research, /Safari:[\s\S]*?Safari-specific permitted action types/);
});

test("safety and user choices are prerequisites to any future prototype", async () => {
  const { research } = await read();
  for (const term of [
    "explicit user consent", "native scanner", "ClamAV signature",
    "quarantine", "canonical identity", "selected application",
    "fail-closed", "missing permissions", "incomplete scans",
    "worker suspension", "native disconnection", "timeouts",
    "private profiles", "user's PDF preferences",
    "dangerous-download checks", "without a separate permissions/privacy design"
  ]) assert.ok(research.includes(term), term);
});

test("interception guide links from existing opening guide without changing its support matrix", async () => {
  const { research, support } = await read();
  assert.match(support, /\[interception API feasibility assessment\]\(browser-interception-apis\.md\)/);
  assert.match(research, /\[browser-opening support matrix\]\(download-opening-browser-support\.md\)/);
  assert.match(support, /no browser has an active PDF Magic Opener/);
  for (const name of [
    "Brave (default)", "Google Chrome", "Chromium", "Microsoft Edge",
    "Vivaldi", "Opera", "Arc", "Mozilla Firefox", "Apple Safari"
  ]) assert.match(support, new RegExp(name.replace(/[()]/g, "\\$&")));
});

test("original extension manifests remain inactive without interception or opening privileges", async () => {
  const { research, shared, safari, background } = await read();
  assert.equal(shared.manifest_version, 3);
  assert.deepEqual(shared.permissions, []);
  assert.deepEqual(shared.host_permissions, []);
  assert.deepEqual(shared.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.deepEqual(safari.optional_permissions, ["downloads"]);
  assert.match(background, /Inactive shared WebExtensions background entry point/);
  assert.match(background, /void 0;/);
  assert.match(research, /Do not enable interception in this checklist task/);
});

test("guide cites primary vendor material for each capability family", async () => {
  const { research } = await read();
  for (const url of [
    "https://developer.chrome.com/docs/extensions/reference/api/webRequest",
    "https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest",
    "https://developer.chrome.com/docs/extensions/reference/api/downloads",
    "https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Intercept_HTTP_requests",
    "https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/onBeforeRequest",
    "https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/filterResponseData",
    "https://developer.apple.com/documentation/safariservices/blocking-content-with-your-safari-web-extension"
  ]) assert.ok(research.includes(url), url);
});

test("acceptance requires live browser experiments and never equates documentation with enforcement", async () => {
  const { research } = await read();
  for (const term of [
    "disposable profile", "redirects", "blob:", "data:", "file:",
    "cached", "other extensions", "rule conditions", "resource exhaustion",
    "competing extensions", "native authentication",
    "end-to-end browser security claim"
  ]) {
    assert.ok(research.includes(term), term);
  }
  assert.match(research, /an OS\/Finder open/);
  assert.match(research, /OS-managed access restrictions\s+separately/);
});
