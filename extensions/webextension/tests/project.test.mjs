import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { inflateSync } from "node:zlib";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (path) => JSON.parse(await readFile(join(root, path), "utf8"));

test("the shared project is a private dependency-free Node package", async () => {
  const pkg = await load("package.json");
  assert.equal(pkg.private, true);
  assert.equal(pkg.type, "module");
  assert.equal(pkg.scripts.build, "node scripts/build.mjs");
  assert.equal(pkg.scripts.test, "node --test tests/*.test.mjs");
  assert.equal(pkg.dependencies, undefined);
  assert.equal(pkg.devDependencies, undefined);
  assert.equal(pkg.scripts.install, undefined);
  assert.equal(pkg.scripts.start, undefined);
});

test("the common Manifest V3 scaffold has no browser or host privileges", async () => {
  const manifest = await load("manifest.json");
  assert.deepEqual(Object.keys(manifest).sort(), [
    "action", "background", "description", "host_permissions", "icons", "manifest_version", "name", "permissions", "version"
  ]);
  assert.equal(manifest.manifest_version, 3);
  assert.match(manifest.version, /^\d+\.\d+\.\d+$/);
  assert.equal(manifest.name, "PDF Magic Opener");
  assert.equal(manifest.description,
    "PDF Magic Opener browser integration scaffold. Not active; cannot scan, sanitize, or open PDF files.");
  assert.ok(manifest.description.length <= 132);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  for (const forbidden of [
    "content_scripts", "externally_connectable", "nativeMessaging",
    "web_accessible_resources", "optional_permissions", "optional_host_permissions"
  ]) {
    assert.equal(manifest[forbidden], undefined);
  }
});

test("the build generates the same inert portable manifest", async () => {
  const source = await load("manifest.json");
  const output = await load("dist/manifest.json");
  assert.deepEqual(output, source);
  assert.equal(output.name, "PDF Magic Opener");
  const raw = await readFile(join(root, "dist", "manifest.json"), "utf8");
  assert.equal(raw, `${JSON.stringify(source, null, 2)}\n`);
});

test("the manifest identifies four actual portable PNG icon sizes", async () => {
  const manifest = await load("manifest.json");
  assert.deepEqual(manifest.icons, {
    "16": "icons/icon-16.png",
    "32": "icons/icon-32.png",
    "48": "icons/icon-48.png",
    "128": "icons/icon-128.png"
  });
  for (const size of [16, 32, 48, 128]) {
    const source = await readFile(join(root, manifest.icons[String(size)]));
    const built = await readFile(join(root, "dist", manifest.icons[String(size)]));
    assert.deepEqual(built, source, `icon-${size} must be packaged without modification`);
    assert.deepEqual(
      [...source.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]
    );
    assert.equal(source.readUInt32BE(8), 13);
    assert.equal(source.toString("ascii", 12, 16), "IHDR");
    assert.equal(source.readUInt32BE(16), size);
    assert.equal(source.readUInt32BE(20), size);
    assert.equal(source[24], 8, "8-bit PNG");
    assert.equal(source[25], 6, "RGBA PNG");
    assert.equal(source.toString("ascii", 37, 41), "IDAT");
    const compressedLength = source.readUInt32BE(33);
    const pixels = inflateSync(source.subarray(41, 41 + compressedLength));
    assert.equal(pixels.length, size * (size * 4 + 1));
    assert.equal(pixels[0], 0, "first scanline uses PNG filter None");
    const rgbaAt = (x, y) => {
      const offset = y * (size * 4 + 1) + 1 + 4 * x;
      return pixels.subarray(offset, offset + 4);
    };
    assert.equal(rgbaAt(0, 0)[3], 0, "transparent corner");
    assert.equal(rgbaAt(size - 1, 0)[3], 0, "transparent corner");
    assert.equal(rgbaAt(Math.floor(size / 2), Math.floor(size / 2))[3], 255,
      "visible centered artwork");
    const colors = new Set();
    for (let y = 0; y < size; y++) {
      assert.equal(pixels[y * (size * 4 + 1)], 0);
      for (let x = 0; x < size; x++) {
        const rgba = rgbaAt(x, y);
        if (rgba[3] > 240) colors.add(rgba.subarray(0, 3).join(","));
      }
    }
    assert.ok(colors.size >= 3, "icons contain distinguishable artwork colors");
  }
});

test("the shared Manifest V3 declares a packaged no-op background module", async () => {
  const manifest = await load("manifest.json");
  const builtManifest = await load("dist/manifest.json");
  assert.deepEqual(manifest.background, {
    service_worker: "background.js",
    type: "module"
  });
  assert.deepEqual(builtManifest.background, manifest.background);

  const workerSource = await readFile(join(root, "src", "background.js"), "utf8");
  const packagedWorker = await readFile(join(root, "dist", "background.js"), "utf8");
  assert.equal(packagedWorker, workerSource);
  assert.equal(workerSource,
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "void 0;\n"
  );

  // Importing the packaged module has no side effects, registrations,
  // browser API calls, network requests or access to native scan policy.
  const url = new URL("../dist/background.js", import.meta.url);
  const imported = await import(url.href);
  assert.deepEqual(Object.keys(imported), []);
});

test("toolbar action uses only existing icons and cannot activate PDF opening", async () => {
  const source = await load("manifest.json");
  const built = await load("dist/manifest.json");
  assert.deepEqual(Object.keys(source.action).sort(), ["default_icon", "default_title"]);
  assert.equal(source.action.default_title, "PDF Magic Opener (not active)");
  assert.deepEqual(source.action.default_icon, source.icons);
  assert.deepEqual(built.action, source.action);
  assert.equal(source.action.default_popup, undefined, "popup is a separate task");
  assert.deepEqual(source.permissions, []);
  assert.deepEqual(source.host_permissions, []);
  assert.deepEqual(source.background, { service_worker: "background.js", type: "module" });
  for (const size of [16, 32, 48, 128]) {
    const path = source.action.default_icon[String(size)];
    assert.equal(path, `icons/icon-${size}.png`);
    assert.deepEqual(await readFile(join(root, "dist", path)), await readFile(join(root, path)));
  }
});
