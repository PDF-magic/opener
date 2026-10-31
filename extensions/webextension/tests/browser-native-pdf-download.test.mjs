import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  createNativePdfDownloadFixture, NATIVE_PDF_DOWNLOAD_CASES
} from "../scripts/native-pdf-download-fixture.mjs";

const load = path => readFile(new URL(path, import.meta.url), "utf8");

test("real-download fixture is a valid PDF with safe deterministic names", () => {
  const fixture = createNativePdfDownloadFixture();
  assert.equal(fixture.pdf.subarray(0, 9).toString("ascii"), "%PDF-1.4\n");
  assert.match(fixture.pdf.subarray(-64).toString("ascii"),
    /startxref\n\d+\n%%EOF\n$/);
  assert.match(fixture.pdf.toString("ascii"), /PDF Magic Native Download Smoke/);
  assert.equal(fixture.cases.length, 2);
  assert.ok(Object.isFrozen(fixture.cases));
  assert.deepEqual(fixture.cases.map(item => item.mime), [
    "application/pdf", "application/octet-stream"
  ]);
  assert.deepEqual(fixture.cases.map(item => item.name), [
    "pdfmagic-attachment.pdf", "pdfmagic-octet.pdf"
  ]);
  for (const item of NATIVE_PDF_DOWNLOAD_CASES) {
    assert.match(item.name, /^[a-z0-9-]+\.pdf$/);
    assert.ok(item.path.startsWith("/native-download/"));
  }
  assert.deepEqual(createNativePdfDownloadFixture().pdf, fixture.pdf);
});

test("real-download server returns genuine attachment headers, bytes, and safe errors", async () => {
  const fixture = createNativePdfDownloadFixture();
  const server = createServer((request, response) => {
    if (!fixture.handle(request, response)) {
      response.writeHead(404); response.end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const base = "http://127.0.0.1:" + server.address().port;
  try {
    const landing = await fetch(base + "/native-download/index");
    assert.equal(landing.status, 200);
    assert.match(landing.headers.get("content-type"), /^text\/html/);
    const html = await landing.text();
    for (const item of fixture.cases) {
      assert.ok(html.includes('id="' + item.selector.slice(1) + '"'));
      const result = await fetch(base + item.path);
      assert.equal(result.status, 200);
      assert.equal(result.headers.get("content-type"), item.mime);
      assert.equal(result.headers.get("content-disposition"),
        'attachment; filename="' + item.name + '"');
      assert.equal(result.headers.get("content-length"), String(fixture.pdf.length));
      assert.equal(result.headers.get("cache-control"), "no-store");
      assert.equal(result.headers.get("x-content-type-options"), "nosniff");
      assert.deepEqual(Buffer.from(await result.arrayBuffer()), fixture.pdf);
    }
    assert.deepEqual(fixture.snapshot(), {
      requests: {
        "/native-download/attachment.pdf": 1, "/native-download/octet": 1
      },
      landingRequests: 1
    });
    assert.ok(Object.isFrozen(fixture.snapshot()));
    assert.ok(Object.isFrozen(fixture.snapshot().requests));
    assert.equal((await fetch(base + "/native-download/unknown.pdf")).status, 404);
    assert.equal((await fetch(base + fixture.cases[0].path,
      { method: "POST" })).status, 405);
    assert.equal((await fetch(base + "/outside.pdf")).status, 404);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test("dedicated Chrome and Firefox download CI jobs inspect actual saved files", async () => {
  const [chrome, firefox, ci, manifest, background, packageJson] = await Promise.all([
    load("../scripts/test-chrome-native-pdf-download.mjs"),
    load("../scripts/test-firefox-native-pdf-download.mjs"),
    load("../../../.github/workflows/browser-native-pdf-downloads.yml"),
    load("../manifest.json").then(JSON.parse),
    load("../src/background.js"),
    load("../package.json").then(JSON.parse)
  ]);
  for (const expected of [
    "Chrome browser-native PDF downloads",
    "Firefox browser-native PDF downloads",
    "browser-actions/setup-chrome@v2",
    "browser-actions/setup-firefox@v1",
    "browser-actions/setup-geckodriver@latest",
    "test-chrome-native-pdf-download.mjs",
    "test-firefox-native-pdf-download.mjs"
  ]) assert.ok(ci.includes(expected), expected);
  for (const content of [chrome, firefox]) {
    for (const expected of [
      "createNativePdfDownloadFixture", "127.0.0.1",
      "fixture.snapshot().requests[item.path]",
      "fixture.pdf", "readFile(join(downloadDir, item.name))",
      "await rm(profile, { recursive: true, force: true })"
    ]) assert.ok(content.includes(expected), expected);
    for (const forbidden of [
      "--load-extension=", "permissions.request(", "connectNative(",
      "sendNativeMessage(", "downloads.open(", "clamscan(", "https://"
    ]) assert.equal(content.includes(forbidden), false, forbidden);
  }
  assert.ok(chrome.includes("Browser.downloadWillBegin"));
  assert.ok(chrome.includes("Browser.downloadProgress"));
  assert.ok(chrome.includes('event.state === "completed"'));
  assert.ok(firefox.includes('"browser.download.dir": downloadDir'));
  assert.ok(firefox.includes('"/element/" + elementId + "/click"'));
  assert.match(packageJson.scripts.test, /tests\/\*\.test\.mjs/);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
});

test("macOS Chrome download-to-safe-open CI retains actual filesystem quarantine", async () => {
  const [chrome, safeOpen, workflow, retention] = await Promise.all([
    load("../scripts/test-chrome-native-pdf-download.mjs"),
    load("../../../tests/general/chrome-downloaded-quarantine.py"),
    load("../../../.github/workflows/browser-native-pdf-downloads.yml"),
    load("../../../tests/general/retain-os-quarantine.py")
  ]);
  for (const required of [
    "PDF_MAGIC_CHROME_HANDOFF_DIR",
    "await rename(source, destination)",
    "handoff.isDirectory() && !handoff.isSymbolicLink()",
    "Handoff must be empty",
    "Transferred Chrome download must retain its exact original bytes"
  ]) assert.ok(chrome.includes(required), required);
  assert.ok(!chrome.includes("copyFile("),
    "A copying handoff may discard the Chrome download's macOS xattrs");
  for (const required of [
    "chrome-macos-quarantine-open",
    "runs-on: macos-15",
    "PDF_MAGIC_CHROME_HANDOFF_DIR",
    "PDF_MAGIC_CHROME_DOWNLOAD_DIR",
    "tests/general/chrome-downloaded-quarantine.py -v",
    "browser-actions/setup-chrome@v2",
    "actions/upload-artifact@v4",
    "actions/download-artifact@v4",
    "needs: chrome-native-pdf-download",
    "if-no-files-found: error"
  ]) assert.ok(workflow.includes(required), required);
  for (const required of [
    'QUARANTINE = "com.apple.quarantine"',
    '["/usr/bin/xattr", "-px", QUARANTINE',
    '["/usr/bin/xattr", "-wx", QUARANTINE',
    "opener.scan_and_open(str(pdf), \"/scanner\")",
    "launch.assert_not_called()",
    '"clean"',
    '"malware"',
    '"failure"',
    '"timeout"',
    "pdfmagic-attachment.pdf",
    "pdfmagic-octet.pdf",
    "patch.object(opener, \"launch_clean_file\"",
    "patch.object(opener, \"intended_destination\""
  ]) assert.ok(safeOpen.includes(required), required);
  assert.ok(!safeOpen.includes("subprocess.run([\"open\""),
    "No real macOS PDF opener must launch during the test");
  assert.ok(!safeOpen.includes("os.removexattr("));
  assert.ok(retention.includes("test_macos_quarantine_attribute_survives_blocked_pdf"));
});
