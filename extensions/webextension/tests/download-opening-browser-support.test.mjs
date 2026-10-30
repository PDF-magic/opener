import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const docs = new URL("../../../docs/download-opening-browser-support.md", import.meta.url);
const registry = new URL("../../../browser_registry.py", import.meta.url);
const viewer = new URL("../../../docs/browser-pdf-viewers.md", import.meta.url);
const manifest = new URL("../manifest.json", import.meta.url);
const safariManifest = new URL("../../safari/manifest.json", import.meta.url);
const background = new URL("../src/background.js", import.meta.url);

async function load() {
  const [documentation, browserRegistry, viewerDocs, manifestText,
    safariText, backgroundText] = await Promise.all([
    readFile(docs, "utf8"),
    readFile(registry, "utf8"),
    readFile(viewer, "utf8"),
    readFile(manifest, "utf8"),
    readFile(safariManifest, "utf8"),
    readFile(background, "utf8")
  ]);
  return {
    documentation, browserRegistry, viewerDocs,
    manifest: JSON.parse(manifestText),
    safariManifest: JSON.parse(safariText), backgroundText
  };
}

function browserRows(documentation) {
  return documentation.split("\n").filter((line) =>
    /^\| (?:Brave \(default\)|Google Chrome|Chromium|Microsoft Edge|Vivaldi|Opera|Arc|Mozilla Firefox|Apple Safari) \|/.test(line));
}

test("support matrix covers all nine canonical browser bundle identifiers once", async () => {
  const { documentation, browserRegistry } = await load();
  const expected = [
    ["Brave (default)", "com.brave.Browser"],
    ["Google Chrome", "com.google.Chrome"],
    ["Chromium", "org.chromium.Chromium"],
    ["Microsoft Edge", "com.microsoft.edgemac"],
    ["Vivaldi", "com.vivaldi.Vivaldi"],
    ["Opera", "com.operasoftware.Opera"],
    ["Arc", "company.thebrowser.Browser"],
    ["Mozilla Firefox", "org.mozilla.firefox"],
    ["Apple Safari", "com.apple.Safari"]
  ];
  const rows = browserRows(documentation);
  assert.equal(rows.length, expected.length);
  for (const [name, bundle] of expected) {
    const matches = rows.filter((row) =>
      row.startsWith("| " + name + " | ") && row.includes("`" + bundle + "`"));
    assert.equal(matches.length, 1, name);
    assert.match(browserRegistry, new RegExp(bundle.replaceAll(".", "\\.")));
    assert.match(matches[0], /\| Inactive \|\s*$/);
    assert.match(matches[0], /Conditional on installed, verified PDF target/);
  }
});

test("vendor-documented browser open methods are distinguished from conditional and unverified browsers", async () => {
  const { documentation } = await load();
  const rows = new Map(browserRows(documentation).map(row =>
    [row.split("|")[1].trim(), row]));
  for (const name of ["Google Chrome", "Mozilla Firefox"]) {
    assert.match(rows.get(name), /\*\*Documented\*\*/);
    assert.match(rows.get(name), /downloads.open/);
    assert.match(rows.get(name), /user (?:gesture|action)/);
  }
  for (const name of ["Brave (default)", "Chromium", "Microsoft Edge",
    "Vivaldi", "Opera", "Arc"]) {
    assert.match(rows.get(name), /Conditional/);
    assert.doesNotMatch(rows.get(name), /\*\*Documented\*\*/);
  }
  assert.match(rows.get("Apple Safari"), /\*\*Unverified\*\*/);
});

test("documentation separates browser-owned opens, gesture-gated opens and native handoffs", async () => {
  const { documentation } = await load();
  for (const required of [
    "**Browser-owned opening:**",
    "**Extension-invoked opening:**",
    "**Native verified application handoff",
    "`downloads.open`",
    "`downloads.onChanged`",
    "`downloads.open` permissions",
    "user gesture",
    "does not intercept or veto",
    "enabled opening command",
    "native coordinator",
    "browser's own opening",
    "user consent"
  ]) {
    assert.ok(documentation.includes(required), required);
  }
  assert.match(documentation, /asynchronous "scan finished" callback/);
  assert.match(documentation, /quarantine retention/);
  assert.match(documentation, /file identity/);
  assert.match(documentation, /selected.*application/);
  assert.match(documentation, /not.*intercept/i);
  assert.match(documentation, /browser-specific user-gesture route/);
});

test("support claims link directly to browser vendor API references", async () => {
  const { documentation } = await load();
  for (const url of [
    "https://developer.chrome.com/docs/extensions/reference/api/downloads",
    "https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads/open",
    "https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/User_actions",
    "https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/api-support",
    "https://developer.apple.com/documentation/SafariServices/safari-web-extensions"
  ]) assert.ok(documentation.includes(url), url);
});

test("support matrix is discoverable beside existing PDF browser viewer comparison", async () => {
  const { documentation, viewerDocs } = await load();
  assert.match(viewerDocs, /download-opening-browser-support\.md/);
  assert.match(documentation, /\[viewer differences\]\(browser-pdf-viewers\.md\)/);
});

test("documentation does not claim current extension can scan or control openings", async () => {
  const { documentation, manifest, safariManifest, backgroundText } = await load();
  assert.match(documentation, /no browser has an active PDF Magic Opener/);
  assert.match(documentation, /PDF Magic Opener flow is currently inactive/);
  assert.match(documentation, /not guaranteed by any listed browser integration/i);
  assert.equal(backgroundText.trim(), "// Inactive shared WebExtensions background entry point.\n// Do not listen for messages, inspect PDFs or request native access here.\nvoid 0;");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(safariManifest.permissions.includes("nativeMessaging"), true);
  assert.equal(safariManifest.permissions.includes("downloads.open"), false);
  assert.equal(manifest.permissions.includes("downloads.open"), false);
  assert.equal(manifest.optional_permissions.includes("downloads.open"), false);
});

test("safety guidance does not treat browser downloads.open as a scanner verdict", async () => {
  const { documentation } = await load();
  for (const snippet of [
    "does **not** choose the app",
    "opening authorization",
    "ClamAV",
    "quarantine",
    "user's selected",
    "permission review",
    "real browser acceptance tests",
    "no browser has an active",
    "clean verdict"
  ]) assert.ok(documentation.includes(snippet), snippet);
});

function strictInterceptionRows(documentation) {
  const marker = "## Strict pre-open interception availability (opener-0717)";
  const start = documentation.indexOf(marker);
  assert.notEqual(start, -1, "strict interception section must be discoverable");
  const section = documentation.slice(start + marker.length)
    .split("\n## What can actually be enforced?")[0];
  return section.split("\n").filter(line =>
    /^\| (?:Brave \(default\)|Google Chrome|Chromium|Microsoft Edge|Vivaldi|Opera|Arc|Mozilla Firefox|Apple Safari) \|/.test(line));
}

test("strict interception limitations identify all nine registry browsers exactly once", async () => {
  const { documentation, browserRegistry } = await load();
  const expected = [
    "Brave (default)", "Google Chrome", "Chromium", "Microsoft Edge",
    "Vivaldi", "Opera", "Arc", "Mozilla Firefox", "Apple Safari"
  ];
  const rows = strictInterceptionRows(documentation);
  assert.equal(rows.length, expected.length);
  for (const name of expected) {
    const found = rows.filter(line => line.startsWith("| " + name + " | "));
    assert.equal(found.length, 1, name);
    assert.match(browserRegistry, /com\.brave\.Browser/);
    assert.ok(found[0].split("|")[3].trim().length > 10, "uncaptured opening path: " + name);
    assert.match(found[0], /OS opening|Finder/);
    assert.doesNotMatch(found[0], /\| (?:Supported|Available|Enforced) \|/);
  }
});

test("standard downloads API cannot guarantee strict opening interception in Chromium-family or Firefox", async () => {
  const { documentation } = await load();
  const map = new Map(strictInterceptionRows(documentation).map(line =>
    [line.split("|")[1].trim(), line.split("|")[2].trim()]));
  for (const name of [
    "Brave (default)", "Google Chrome", "Chromium", "Microsoft Edge",
    "Vivaldi", "Opera", "Arc", "Mozilla Firefox"
  ]) {
    assert.match(map.get(name), /\*\*Unavailable\*\*/, name);
    assert.doesNotMatch(map.get(name), /strict interception supported/i);
  }
  assert.match(map.get("Apple Safari"), /\*\*Unverified; treat as unavailable\*\*/);
  assert.doesNotMatch(map.get("Apple Safari"), /proven impossible|supported/i);
});

test("strict-interception definition covers browser-owned and OS bypass paths without inventing universal authority", async () => {
  const { documentation } = await load();
  const section = documentation.split("## Strict pre-open interception availability (opener-0717)")[1]
    .split("\n## What can actually be enforced?")[0];
  for (const phrase of [
    "universal, pre-open veto",
    "public WebExtensions downloads API",
    "automatic-open",
    "inline",
    "Finder",
    "downloads.onCreated",
    "downloads.onChanged",
    "downloads.onErased",
    "downloads.onDeterminingFilename",
    "filename selection",
    "downloads.open",
    "user gesture",
    "browser's own",
    "controlled native handoff",
    "not browser-wide strict interception",
    "current-file identity",
    "quarantine",
    "selected-application",
    "user consent",
    "real installed-browser tests",
    "remain inactive"
  ]) assert.ok(section.includes(phrase), phrase);
  assert.match(section, /not.*a general right to veto all/i);
  assert.match(section, /not.*proof that all possible privileged OS controls/i);
  assert.match(section, /no Safari-specific strict/);
});

test("vendor documentation for unavailable public intercept mechanisms remains linked", async () => {
  const { documentation } = await load();
  const section = documentation.split("## Strict pre-open interception availability (opener-0717)")[1]
    .split("\n## What can actually be enforced?")[0];
  for (const url of [
    "https://developer.chrome.com/docs/extensions/reference/api/downloads",
    "https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads",
    "https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads/open",
    "https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/api-support",
    "https://developer.apple.com/documentation/safariservices/assessing-your-safari-web-extension-s-browser-compatibility"
  ]) assert.ok(section.includes(url), url);
});

test("strict opening limitations are documentation only and change no installed extension privileges", async () => {
  const { documentation, manifest, safariManifest, backgroundText } = await load();
  assert.match(documentation, /current shipped\s+background and popup remain inactive/i);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(backgroundText.trimEnd().endsWith("void 0;"), true);
  assert.equal(safariManifest.permissions.includes("downloads.open"), false);
});
