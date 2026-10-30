// Build an unsigned Firefox submission ZIP, never a signed installable XPI.
// The exact eight-file archive allowlist uses the existing deterministic
// ZIP STORE encoder: Firefox and Chrome share filenames, not manifests.
import { randomUUID } from "node:crypto";
import { lstat, mkdir, open, readFile, rename, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { CHROME_PACKAGE_FILES, encodeChromeZip } from "./chrome-zip.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const dist = join(root, "dist");
const firefox = join(dist, "firefox");

async function safeDirectory(path) {
  const stat = await lstat(path);
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error("Unsafe Firefox package directory");
  }
}

try {
  await safeDirectory(dist);
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}

// Rebuild from reviewed Firefox source, applying the established manifest,
// icon and inert background validators before reading any packaging inputs.
await import("./build-firefox.mjs");
await safeDirectory(dist);
await safeDirectory(firefox);
await safeDirectory(join(firefox, "icons"));

const shared = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
const gecko = JSON.parse(await readFile(join(root, "firefox", "gecko.json"), "utf8"));
const builtManifest = JSON.parse(await readFile(join(firefox, "manifest.json"), "utf8"));
const { background, ...common } = shared;
const expected = {
  ...common,
  background: { scripts: ["background.js"] },
  browser_specific_settings: gecko
};
if (JSON.stringify(builtManifest) !== JSON.stringify(expected) ||
    builtManifest.manifest_version !== 3 ||
    builtManifest.incognito !== "not_allowed" ||
    builtManifest.name !== "PDF Magic Opener" ||
    !/^\d+\.\d+\.\d+$/.test(builtManifest.version) ||
    JSON.stringify(builtManifest.background) !==
      JSON.stringify({ scripts: ["background.js"] }) ||
    JSON.stringify(builtManifest.permissions) !== "[]" ||
    JSON.stringify(builtManifest.host_permissions) !== "[]" ||
    JSON.stringify(builtManifest.optional_permissions) !==
      JSON.stringify(["downloads"]) ||
    builtManifest.browser_specific_settings?.gecko?.strict_min_version !== "128.0" ||
    JSON.stringify(builtManifest.browser_specific_settings?.gecko?.data_collection_permissions) !==
      JSON.stringify({ required: ["none"] })) {
  throw new Error("Unsafe Firefox submission manifest");
}

const entries = [];
for (const name of CHROME_PACKAGE_FILES) {
  const builtPath = join(firefox, name);
  const stat = await lstat(builtPath);
  if (!stat.isFile() || stat.isSymbolicLink() ||
      stat.size === 0 || stat.size > 2 * 1024 * 1024) {
    throw new Error("Unsafe Firefox package input file");
  }
  const bytes = await readFile(builtPath);
  if (name !== "manifest.json") {
    const input = name === "background.js" || name.startsWith("popup.")
      ? join(root, "src", name) : join(root, name);
    const sourceStat = await lstat(input);
    if (!sourceStat.isFile() || sourceStat.isSymbolicLink() ||
        !bytes.equals(await readFile(input))) {
      throw new Error("Firefox package differs from validated source");
    }
  }
  entries.push({ name, bytes });
}

const archive = encodeChromeZip(entries);
const output = join(dist, "firefox-packages");
await mkdir(output, { recursive: true });
await safeDirectory(output);
const destination = join(output,
  "pdf-magic-opener-firefox-" + builtManifest.version + "-unsigned.zip");
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

console.log("Unsigned Firefox extension ZIP: " + destination);
console.log("Mozilla signing and approved production Gecko ID are required before release.");
