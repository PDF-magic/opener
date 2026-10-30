import assert from "node:assert/strict";
import { readFile, lstat } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { CHROME_PACKAGE_FILES, encodeChromeZip } from "../scripts/chrome-zip.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const dist = join(root, "dist");

function verifyZipArchive(zip) {
  // Independently parse ZIP central directory and local headers without a
  // third-party ZIP library or executing any bundled code.
  const end = zip.length - 22;
  assert.equal(zip.readUInt32LE(end), 0x06054b50);
  assert.equal(zip.readUInt16LE(end + 4), 0);
  assert.equal(zip.readUInt16LE(end + 6), 0);
  assert.equal(zip.readUInt16LE(end + 8), CHROME_PACKAGE_FILES.length);
  assert.equal(zip.readUInt16LE(end + 10), CHROME_PACKAGE_FILES.length);
  assert.equal(zip.readUInt16LE(end + 20), 0);
  const centralSize = zip.readUInt32LE(end + 12);
  const centralOffset = zip.readUInt32LE(end + 16);
  assert.equal(centralOffset + centralSize, end);
  let cursor = centralOffset;
  const records = [];
  for (const name of CHROME_PACKAGE_FILES) {
    assert.equal(zip.readUInt32LE(cursor), 0x02014b50);
    assert.equal(zip.readUInt16LE(cursor + 8), 0);
    assert.equal(zip.readUInt16LE(cursor + 10), 0);
    assert.equal(zip.readUInt16LE(cursor + 14), 0x21);
    const crc = zip.readUInt32LE(cursor + 16);
    const size = zip.readUInt32LE(cursor + 20);
    assert.equal(zip.readUInt32LE(cursor + 24), size);
    const nameLen = zip.readUInt16LE(cursor + 28);
    assert.equal(zip.readUInt16LE(cursor + 30), 0);
    assert.equal(zip.readUInt16LE(cursor + 32), 0);
    const archiveName = zip.subarray(cursor + 46, cursor + 46 + nameLen).toString("utf8");
    assert.equal(archiveName, name);
    const local = zip.readUInt32LE(cursor + 42);
    assert.ok(local < centralOffset);
    assert.equal(zip.readUInt32LE(local), 0x04034b50);
    assert.equal(zip.readUInt16LE(local + 6), 0);
    assert.equal(zip.readUInt16LE(local + 8), 0);
    assert.equal(zip.readUInt16LE(local + 12), 0x21);
    assert.equal(zip.readUInt32LE(local + 14), crc);
    assert.equal(zip.readUInt32LE(local + 18), size);
    assert.equal(zip.readUInt32LE(local + 22), size);
    assert.equal(zip.readUInt16LE(local + 26), nameLen);
    assert.equal(zip.readUInt16LE(local + 28), 0);
    assert.equal(
      zip.subarray(local + 30, local + 30 + nameLen).toString("utf8"), name
    );
    records.push({
      name,
      bytes: zip.subarray(local + 30 + nameLen, local + 30 + nameLen + size)
    });
    cursor += 46 + nameLen;
  }
  assert.equal(cursor, end);
  return records;
}

test("Chrome package is a real ZIP containing only eight validated assets", async () => {
  const manifest = JSON.parse(await readFile(join(dist, "manifest.json"), "utf8"));
  const filename = "pdf-magic-opener-chrome-" + manifest.version + ".zip";
  const archive = join(dist, "chrome", filename);
  const stats = await lstat(archive);
  assert.ok(stats.isFile());
  assert.equal(stats.isSymbolicLink(), false);
  const zip = await readFile(archive);
  const records = verifyZipArchive(zip);
  assert.deepEqual(records.map((r) => r.name), CHROME_PACKAGE_FILES);
  for (const record of records) {
    assert.deepEqual(record.bytes, await readFile(join(dist, record.name)));
  }
  assert.deepEqual(JSON.parse(records[0].bytes.toString("utf8")), manifest);
  assert.deepEqual(manifest.background, { service_worker: "background.js", type: "module" });
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(manifest.action.default_title, "PDF Magic Opener (not active)");
  assert.ok(records.every((r) => !r.name.startsWith("firefox/") &&
    !r.name.includes("src/") && !r.name.includes("secret")));
});

test("ZIP output is deterministic for identical approved inputs", async () => {
  const manifest = JSON.parse(await readFile(join(dist, "manifest.json"), "utf8"));
  const zip = await readFile(join(dist, "chrome",
    "pdf-magic-opener-chrome-" + manifest.version + ".zip"));
  const entries = await Promise.all(CHROME_PACKAGE_FILES.map(async (name) => ({
    name, bytes: await readFile(join(dist, name))
  })));
  assert.deepEqual(encodeChromeZip(entries), zip);
  assert.deepEqual(encodeChromeZip(entries), encodeChromeZip(entries));
});

test("ZIP builder refuses missing, extra, swapped or oversized assets", () => {
  const good = CHROME_PACKAGE_FILES.map((name) => ({
    name, bytes: Buffer.from("validated fixture")
  }));
  assert.doesNotThrow(() => encodeChromeZip(good));
  for (const broken of [
    good.slice(1),
    [...good, { name: "private-key.pem", bytes: Buffer.from("x") }],
    good.map((e, i) => i === 0 ? { ...e, name: "../manifest.json" } : e),
    good.map((e, i) => i === 1 ? { ...e, name: "manifest.json" } : e),
    good.map((e, i) => i === 2 ? { ...e, bytes: Buffer.alloc(0) } : e),
    good.map((e, i) => i === 3 ? { ...e, bytes: Buffer.alloc(2 * 1024 * 1024 + 1) } : e),
    good.map((e, i) => i === 4 ? { ...e, bytes: "not binary" } : e)
  ]) {
    assert.throws(() => encodeChromeZip(broken));
  }
});

test("Chrome packaging is opt-in and does not activate the scanner", async () => {
  const packageJson = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
  assert.equal(packageJson.scripts["package:chrome"], "node scripts/package-chrome.mjs");
  assert.equal(packageJson.dependencies, undefined);
  assert.equal(packageJson.devDependencies, undefined);
  const script = await readFile(join(root, "scripts", "package-chrome.mjs"), "utf8");
  for (const unsafe of [
    "sendNativeMessage(", "connectNative(", "chrome.tabs", "browser.tabs",
    "window.open(", "downloads.open(", "clamscan(", "scan-and-open"
  ]) assert.equal(script.includes(unsafe), false, unsafe);
  const doc = await readFile(join(root, "chrome", "README.md"), "utf8");
  assert.match(doc, /Chrome Web Store/);
  assert.match(doc, /not a signed CRX/i);
});
