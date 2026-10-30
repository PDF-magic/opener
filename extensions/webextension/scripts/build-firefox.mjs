import { copyFile, lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

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
  ["content_scripts", "externally_connectable",
   "optional_permissions", "optional_host_permissions", "action"].some(
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
    "// Inactive shared WebExtensions background entry point.\\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\\n" +
    "void 0;\\n") {
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
