import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";

const load = path => readFile(new URL(path, import.meta.url), "utf8");

test("scanner gate on disposable Firefox download fixtures blocks unsafe opens", () => {
  const output = execFileSync("python3", [
    "../../tests/browser/firefox-downloaded-open.py", "--self-test"
  ], { cwd: new URL("../", import.meta.url), encoding: "utf8", timeout: 30_000 });
  assert.equal((output.match(/PASS Firefox-downloaded PDF scan-and-open isolation/g) || []).length, 2);
});

test("macOS job runs actual Firefox downloads through the safe-open gate", async () => {
  const [workflow, browser, helper, manifest, background] = await Promise.all([
    load("../../../.github/workflows/firefox-download-macos-open.yml"),
    load("../scripts/test-firefox-native-pdf-download.mjs"),
    load("../../../tests/browser/firefox-downloaded-open.py"),
    load("../manifest.json").then(JSON.parse),
    load("../src/background.js")
  ]);
  for (const part of [
    "macos-latest", "browser-actions/setup-firefox@v1",
    "browser-actions/setup-geckodriver@latest",
    "test-firefox-native-pdf-download.mjs",
    "--macos-handoff"
  ]) assert.ok(workflow.includes(part), part);
  assert.match(browser, /process\.platform, "darwin"/);
  assert.match(browser, /readFile\(join\(downloadDir, item\.name\)\)/);
  assert.match(browser, /firefox-downloaded-open\.py/);
  assert.match(helper, /opener\.scan_and_open/);
  assert.match(helper, /"\/usr\/bin\/xattr", "-px"/);
  assert.match(helper, /"\/usr\/bin\/xattr", "-w"/);
  assert.match(helper, /"org\.mozilla\.firefox"/);
  assert.match(helper, /"malware-blocked"/);
  assert.match(helper, /"missing-target-blocked"/);
  assert.match(helper, /"scan-timeout-blocked"/);
  assert.match(helper, /patch\.object\(opener, "launch_clean_file"/);
  assert.match(helper, /"com\.apple\.quarantine"/);
  assert.equal(background.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  for (const forbidden of [
    "--load-extension=", "permissions.request(", "downloads.open(",
    "sendNativeMessage(", "connectNative(", "clamscan(", "https://"
  ]) assert.equal(browser.includes(forbidden), false, forbidden);
});

test("macOS handoff is an isolated, mocked launcher test, not uncontrolled opening", async () => {
  const helper = await load("../../../tests/browser/firefox-downloaded-open.py");
  assert.match(helper, /checked_download\(path\)/);
  assert.match(helper, /not stat\.S_ISREG/);
  assert.match(helper, /path\.read_bytes\(\) != data/);
  assert.match(helper, /read_quarantine\(path\) != original/);
  assert.match(helper, /"firefox-set"/);
  assert.match(helper, /"seeded-in-test"/);
  assert.match(helper, /"scan", "verify", "launch", "verify", "launch"/);
  assert.match(helper, /"CACHE_DB"/);
  assert.match(helper, /"SCAN_REQUEST_DB"/);
  assert.match(helper, /"verify_launch_target"/);
  assert.doesNotMatch(helper, /subprocess\.Popen|os\.system|webbrowser\.open/);
});
