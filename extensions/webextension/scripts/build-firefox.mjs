import { copyFile, lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { copyPopupAssets } from "./popup-assets.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
const settings = JSON.parse(await readFile(join(root, "firefox", "gecko.json"), "utf8"));
const keys = Object.keys(settings.gecko ?? {}).sort();

if (
  source.manifest_version !== 3 ||
  typeof source.name !== "string" || !source.name.trim() ||
  !/^\d+\.\d+\.\d+$/.test(source.version) ||
  source.browser_specific_settings !== undefined ||
  JSON.stringify(source.background) !==
    JSON.stringify({ service_worker: "background.js", type: "module" }) ||
  !Array.isArray(source.permissions) || source.permissions.length !== 0 ||
  !Array.isArray(source.host_permissions) || source.host_permissions.length !== 0 ||
  JSON.stringify(source.optional_permissions) !== JSON.stringify(["downloads"]) ||
  !source.action || typeof source.action !== "object" ||
  Array.isArray(source.action) ||
  JSON.stringify(Object.keys(source.action).sort()) !==
    JSON.stringify(["default_icon", "default_popup", "default_title"]) ||
  source.action.default_popup !== "popup.html" ||
  source.action.default_title !== "PDF Magic Opener (not active)" ||
  JSON.stringify(source.action.default_icon) !== JSON.stringify(source.icons) ||
  ["content_scripts", "externally_connectable",
   "optional_host_permissions"].some(
    (field) => Object.hasOwn(source, field)
  ) ||
  Object.keys(settings).join() !== "gecko" ||
  JSON.stringify(keys) !== JSON.stringify([
    "data_collection_permissions", "id", "strict_min_version"
  ]) ||
  !/^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+$/.test(settings.gecko.id) ||
  settings.gecko.strict_min_version !== "128.0" ||
  JSON.stringify(settings.gecko.data_collection_permissions) !==
    JSON.stringify({ required: ["none"] })
) {
  throw new Error("Firefox scaffold manifest must remain inactive and permission-free");
}

// Firefox MV3 uses background.scripts rather than Chromium service_workers.
// The shared worker has no imports/exports or handlers, and is also valid
// as a classic script. Keep the two browser outputs distinct.
const { background: sharedWorker, ...shared } = source;
const manifest = {
  ...shared,
  background: { scripts: ["background.js"] },
  browser_specific_settings: settings
};
// Package the exact source into the Firefox output as well, never pointing
// at the Chromium sibling directory or executing it during the build.
const workerPath = join(root, "src", "background.js");
const workerStat = await lstat(workerPath);
if (!workerStat.isFile() || workerStat.isSymbolicLink() ||
    workerStat.size > 4096) {
  throw new Error("Invalid Firefox background script");
}
const workerSource = await readFile(workerPath, "utf8");
if (workerSource !==
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "void 0;\n") {
  throw new Error("Firefox background entry point must remain inert");
}

const output = join(root, "dist", "firefox");
await mkdir(output, { recursive: true });
await writeFile(
  join(output, "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8"
);
await copyFile(workerPath, join(output, "background.js"));

await copyPopupAssets(root, output);

// Package the same local, allowlisted toolbar icons for the Firefox variant.
// Do not follow symlinks or accept manifest-supplied file paths.
const sizes = [16, 32, 48, 128];
await mkdir(join(output, "icons"), { recursive: true });
for (const size of sizes) {
  const name = `icon-${size}.png`;
  const relative = `icons/${name}`;
  if (source.icons?.[String(size)] !== relative ||
      source.action.default_icon?.[String(size)] !== relative) {
    throw new Error("Invalid Firefox toolbar icon path");
  }
  const asset = join(root, "icons", name);
  const metadata = await lstat(asset);
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size > 1024 * 1024) {
    throw new Error("Invalid Firefox toolbar icon asset");
  }
  const bytes = await readFile(asset);
  if (bytes.length < 45 ||
      !bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
      bytes.readUInt32BE(16) !== size || bytes.readUInt32BE(20) !== size) {
    throw new Error("Invalid Firefox toolbar icon contents");
  }
  await copyFile(asset, join(output, "icons", name));
}
