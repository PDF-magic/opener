import assert from "node:assert/strict";
import { lstat, readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { CHROME_PACKAGE_FILES, encodeChromeZip } from "../scripts/chrome-zip.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const firefox = join(root, "dist", "firefox");
const files = CHROME_PACKAGE_FILES;

function decodeZip(zip) {
  // Independent parser for the deterministic, uncompressed ZIP layout.
  const end = zip.length - 22;
  assert.ok(end > 0);
  assert.equal(zip.readUInt32LE(end), 0x06054b50);
  assert.equal(zip.readUInt16LE(end + 4), 0);
  assert.equal(zip.readUInt16LE(end + 6), 0);
  assert.equal(zip.readUInt16LE(end + 8), files.length);
  assert.equal(zip.readUInt16LE(end + 10), files.length);
  assert.equal(zip.readUInt16LE(end + 20), 0);
  const length = zip.readUInt32LE(end + 12);
  const start = zip.readUInt32LE(end + 16);
  assert.equal(start + length, end);
  const records = [];
  let cursor = start;
  for (const expected of files) {
    assert.equal(zip.readUInt32LE(cursor), 0x02014b50);
    assert.equal(zip.readUInt16LE(cursor + 8), 0);
    assert.equal(zip.readUInt16LE(cursor + 10), 0);
    const size = zip.readUInt32LE(cursor + 20);
    assert.equal(zip.readUInt32LE(cursor + 24), size);
    const nameLength = zip.readUInt16LE(cursor + 28);
    assert.equal(zip.readUInt16LE(cursor + 30), 0);
    assert.equal(zip.readUInt16LE(cursor + 32), 0);
    const name = zip.subarray(cursor + 46, cursor + 46 + nameLength).toString("utf8");
    assert.equal(name, expected);
    const local = zip.readUInt32LE(cursor + 42);
    assert.ok(local < start);
    assert.equal(zip.readUInt32LE(local), 0x04034b50);
    assert.equal(zip.readUInt16LE(local + 6), 0);
    assert.equal(zip.readUInt16LE(local + 8), 0);
    assert.equal(zip.readUInt32LE(local + 14), zip.readUInt32LE(cursor + 16));
    assert.equal(zip.readUInt32LE(local + 18), size);
    assert.equal(zip.readUInt32LE(local + 22), size);
    assert.equal(zip.readUInt16LE(local + 26), nameLength);
    assert.equal(zip.readUInt16LE(local + 28), 0);
    assert.equal(
      zip.subarray(local + 30, local + 30 + nameLength).toString("utf8"), expected
    );
    const from = local + 30 + nameLength;
    assert.ok(from + size <= start);
    records.push({ name, bytes: zip.subarray(from, from + size) });
    cursor += 46 + nameLength;
  }
  assert.equal(cursor, end);
  return records;
}

async function packagePath() {
  const manifest = JSON.parse(await readFile(join(firefox, "manifest.json"), "utf8"));
  return join(root, "dist", "firefox-packages",
    "pdf-magic-opener-firefox-" + manifest.version + "-unsigned.zip");
}

test("Firefox package is an actual unsigned ZIP of exactly ten approved files", async () => {
  const path = await packagePath();
  const stat = await lstat(path);
  assert.ok(stat.isFile() && !stat.isSymbolicLink());
  const archive = await readFile(path);
  const entries = decodeZip(archive);
  assert.deepEqual(entries.map((entry) => entry.name), files);
  for (const entry of entries) {
    assert.deepEqual(entry.bytes, await readFile(join(firefox, entry.name)));
  }
  assert.equal(entries[0].name, "manifest.json", "Manifest belongs at ZIP root");
  assert.ok(entries.every(({ name }) =>
    !name.includes("src/") && !name.includes("gecko.json") &&
    !name.startsWith("/") && !name.includes("..") &&
    !name.includes("chrome/") && !name.includes("secret") &&
    !name.includes("node_modules/")));
});

test("Firefox ZIP has Gecko MV3 settings, inactive worker, and no extra grants", async () => {
  const manifest = JSON.parse(await readFile(join(firefox, "manifest.json"), "utf8"));
  const archive = decodeZip(await readFile(await packagePath()));
  const shipped = JSON.parse(archive[0].bytes.toString("utf8"));
  assert.deepEqual(shipped, manifest);
  assert.equal(shipped.manifest_version, 3);
  assert.equal(shipped.incognito, "not_allowed");
  assert.deepEqual(shipped.background, { scripts: ["background.js"] });
  assert.equal(shipped.background.service_worker, undefined);
  assert.deepEqual(shipped.permissions, []);
  assert.deepEqual(shipped.host_permissions, []);
  assert.deepEqual(shipped.optional_permissions, ["downloads"]);
  assert.equal(shipped.optional_host_permissions, undefined);
  assert.equal(shipped.content_scripts, undefined);
  assert.deepEqual(shipped.browser_specific_settings, JSON.parse(
    await readFile(join(root, "firefox", "gecko.json"), "utf8")
  ));
  assert.equal(shipped.browser_specific_settings.gecko.strict_min_version, "128.0");
  assert.deepEqual(shipped.browser_specific_settings.gecko.data_collection_permissions, {
    required: ["none"]
  });
  assert.deepEqual(archive[1].bytes,
    await readFile(join(root, "src", "background.js")));
  assert.ok(archive[1].bytes.toString("utf8").trimEnd().endsWith("void 0;"));
});

test("Firefox archive is byte-for-byte reproducible from the Firefox build", async () => {
  const entries = await Promise.all(files.map(async (name) => ({
    name, bytes: await readFile(join(firefox, name))
  })));
  const packaged = await readFile(await packagePath());
  assert.deepEqual(encodeChromeZip(entries), packaged);
  assert.deepEqual(encodeChromeZip(entries), encodeChromeZip(entries));
});

test("shared deterministic ZIP encoder still rejects unexpected Firefox inputs", () => {
  const entries = files.map((name) => ({ name, bytes: Buffer.from("fixture") }));
  assert.doesNotThrow(() => encodeChromeZip(entries));
  for (const invalid of [
    entries.slice(1),
    [...entries, { name: "private-key.pem", bytes: Buffer.from("x") }],
    entries.map((e, i) => i === 0 ? { ...e, name: "../manifest.json" } : e),
    entries.map((e, i) => i === 1 ? { ...e, bytes: Buffer.alloc(0) } : e),
    entries.map((e, i) => i === 2 ? { ...e, bytes: Buffer.alloc(2097153) } : e)
  ]) assert.throws(() => encodeChromeZip(invalid));
});

test("Firefox packaging is opt-in, unsigned, and never starts a PDF scan", async () => {
  const pkg = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
  assert.equal(pkg.scripts["package:firefox"], "node scripts/package-firefox.mjs");
  assert.equal(pkg.dependencies, undefined);
  assert.equal(pkg.devDependencies, undefined);
  const script = await readFile(join(root, "scripts", "package-firefox.mjs"), "utf8");
  for (const unsafe of ["sendNativeMessage(", "connectNative(", "downloads.open(",
    "browser.tabs", "chrome.tabs", "window.open(", "clamscan(", "scan-and-open"]) {
    assert.equal(script.includes(unsafe), false, unsafe);
  }
  const docs = await readFile(join(root, "firefox", "README.md"), "utf8");
  assert.match(docs, /unsigned/i);
  assert.match(docs, /Mozilla signing/i);
  assert.match(docs, /production.*ID/i);
});
