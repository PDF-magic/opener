// Build a Chrome Web Store upload ZIP; do not sign, install, or activate it.
import { randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, rename, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { CHROME_PACKAGE_FILES, encodeChromeZip } from "./chrome-zip.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const dist = join(root, "dist");

async function requireDirectory(path) {
  const stat = await lstat(path);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("Unsafe Chrome build directory");
  }
}

// Check any existing dist directory before the build writes to it.
try {
  await requireDirectory(dist);
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}

// Reuse the established Chromium source, icon, popup and worker validators.
await import("./build.mjs");
await requireDirectory(dist);
await requireDirectory(join(dist, "icons"));

const sourceManifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
const manifest = JSON.parse(await readFile(join(dist, "manifest.json"), "utf8"));
if (JSON.stringify(manifest) !== JSON.stringify(sourceManifest) ||
    manifest.manifest_version !== 3 ||
    manifest.name !== "PDF Magic Opener" ||
    !/^\d+\.\d+\.\d+$/.test(manifest.version) ||
    !Array.isArray(manifest.permissions) || manifest.permissions.length !== 0 ||
    !Array.isArray(manifest.host_permissions) || manifest.host_permissions.length !== 0 ||
    JSON.stringify(manifest.background) !==
      JSON.stringify({ service_worker: "background.js", type: "module" }) ||
    manifest.action?.default_title !== "PDF Magic Opener (not active)") {
  throw new Error("Unsafe Chrome package manifest");
}
const entries = [];
for (const name of CHROME_PACKAGE_FILES) {
  const builtPath = join(dist, name);
  const sourcePath = join(root, name === "manifest.json" ? name :
    name === "background.js" || name.startsWith("popup.") ? join("src", name) : name);
  const stat = await lstat(builtPath);
  if (!stat.isFile() || stat.isSymbolicLink() ||
      stat.size === 0 || stat.size > 2 * 1024 * 1024) {
    throw new Error("Unsafe Chrome package input file");
  }
  const bytes = await readFile(builtPath);
  if (name !== "manifest.json" && !bytes.equals(await readFile(sourcePath))) {
    throw new Error("Chrome package contents differ from validated source");
  }
  entries.push({ name, bytes });
}
const archive = encodeChromeZip(entries);
const output = join(dist, "chrome");
await mkdir(output, { recursive: true });
await requireDirectory(output);
const destination = join(output, "pdf-magic-opener-chrome-" + manifest.version + ".zip");
const temporary = join(output, ".tmp-" + randomUUID());
try {
  const handle = await open(temporary, "wx", 0o600);
  try {
    await handle.writeFile(archive);
  } finally {
    await handle.close();
  }
  await rename(temporary, destination);
} finally {
  await rm(temporary, { force: true });
}
console.log("Chrome extension package: " + destination);
