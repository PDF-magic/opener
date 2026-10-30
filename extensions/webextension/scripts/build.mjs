import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const manifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
const allowed = [
  "description", "host_permissions", "manifest_version", "name", "permissions", "version"
];

// The initial shared project must not accidentally acquire runtime privileges.
if (
  JSON.stringify(Object.keys(manifest).sort()) !== JSON.stringify(allowed) ||
  manifest.manifest_version !== 3 ||
  manifest.name !== "PDF Magic Opener" ||
  typeof manifest.description !== "string" ||
  !manifest.description.trim() || manifest.description.length > 132 ||
  !/^\d+\.\d+\.\d+$/.test(manifest.version) ||
  !Array.isArray(manifest.permissions) || manifest.permissions.length !== 0 ||
  !Array.isArray(manifest.host_permissions) || manifest.host_permissions.length !== 0
) {
  throw new Error("Shared WebExtensions scaffold must remain permission-free");
}

const output = join(root, "dist");
await mkdir(output, { recursive: true });
await writeFile(join(output, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
