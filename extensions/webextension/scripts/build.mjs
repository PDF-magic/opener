import { copyFile, lstat, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const manifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
const allowed = [
  "background", "description", "host_permissions", "icons", "manifest_version", "name", "permissions", "version"
];

// The initial shared project must not accidentally acquire runtime privileges.
if (
  JSON.stringify(Object.keys(manifest).sort()) !== JSON.stringify(allowed) ||
  manifest.manifest_version !== 3 ||
  manifest.name !== "PDF Magic Opener" ||
  !manifest.background || typeof manifest.background !== "object" ||
  Array.isArray(manifest.background) ||
  JSON.stringify(Object.keys(manifest.background).sort()) !==
    JSON.stringify(["service_worker", "type"]) ||
  manifest.background.service_worker !== "background.js" ||
  manifest.background.type !== "module" ||
  !/^\d+\.\d+\.\d+$/.test(manifest.version) ||
  !Array.isArray(manifest.permissions) || manifest.permissions.length !== 0 ||
  !Array.isArray(manifest.host_permissions) || manifest.host_permissions.length !== 0 ||
  !manifest.icons || typeof manifest.icons !== "object" ||
  Array.isArray(manifest.icons) ||
  JSON.stringify(Object.keys(manifest.icons)) !== JSON.stringify(["16", "32", "48", "128"])
) {
  throw new Error("Shared WebExtensions scaffold must remain permission-free");
}

// Validate the actual browser assets before packaging. Paths are an exact
// hard-coded allowlist, so manifest input cannot cause arbitrary file reads.
const iconSizes = [16, 32, 48, 128];
for (const size of iconSizes) {
  const relative = `icons/icon-${size}.png`;
  if (manifest.icons[String(size)] !== relative) {
    throw new Error("Invalid WebExtensions icon path");
  }
  const path = join(root, relative);
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink() || info.size > 1024 * 1024) {
    throw new Error("Invalid WebExtensions icon asset");
  }
  const png = await readFile(path);
  if (
    png.length < 45 ||
    !png.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])) ||
    png.readUInt32BE(8) !== 13 ||
    png.toString("ascii", 12, 16) !== "IHDR" ||
    png.readUInt32BE(16) !== size ||
    png.readUInt32BE(20) !== size ||
    png[24] !== 8 || png[25] !== 6 ||
    png.readUInt32BE(png.length - 12) !== 0 ||
    png.toString("ascii", png.length - 8, png.length - 4) !== "IEND"
  ) {
    throw new Error("Invalid WebExtensions PNG icon dimensions or encoding");
  }
}

// The worker is an intentionally inert module, not a scan or open handler.
// Reject symlinks and unexpected source contents until a separately reviewed
// feature explicitly defines the browser-to-native safety boundary.
const workerPath = join(root, "src", "background.js");
const workerInfo = await lstat(workerPath);
if (!workerInfo.isFile() || workerInfo.isSymbolicLink() ||
    workerInfo.size > 4096) {
  throw new Error("Invalid shared WebExtensions background entry point");
}
const backgroundSource = await readFile(workerPath, "utf8");
if (backgroundSource !==
    "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\n" +
    "export {};\n") {
  throw new Error("Background entry point must remain inert");
}

const output = join(root, "dist");
await mkdir(output, { recursive: true });
await writeFile(join(output, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
await copyFile(workerPath, join(output, "background.js"));

// Copy only validated static art. The no-op background module has no runtime
// permissions, content scripts, event listeners or native PDF bridge.
await mkdir(join(output, "icons"), { recursive: true });
for (const size of iconSizes) {
  const name = `icon-${size}.png`;
  await copyFile(join(root, "icons", name), join(output, "icons", name));
}
