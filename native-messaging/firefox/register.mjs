#!/usr/bin/env node
// Explicitly install a Firefox-only development host registration for the current user.
// No extension permission, host execution, scanning, or system-wide writes happen here.
import { constants } from "node:fs";
import { access, lstat, link, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { homedir, platform as currentPlatform } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory = fileURLToPath(new URL("./", import.meta.url));
const root = resolve(directory, "..");
const slot = "__PDF_MAGIC_NATIVE_HOST_ABSOLUTE_PATH__";
const developmentId = "pdf-magic-opener@example.invalid";

async function json(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

export function firefoxRegistrationPath({ home = homedir(), platform = currentPlatform() } = {}) {
  if (!isAbsolute(home)) throw new Error("Home directory must be absolute");
  if (platform === "darwin") {
    return join(home, "Library", "Application Support", "Mozilla", "NativeMessagingHosts");
  }
  if (platform === "linux") return join(home, ".mozilla", "native-messaging-hosts");
  throw new Error("Firefox user-level host registration is not supported on this platform");
}

export async function firefoxHostManifest(hostPath) {
  if (typeof hostPath !== "string" || !isAbsolute(hostPath)) {
    throw new Error("Native host executable path must be absolute");
  }
  const host = await lstat(hostPath);
  if (!host.isFile() || host.isSymbolicLink() || !(host.mode & 0o111)) {
    throw new Error("Native host must be an executable regular file, not a symlink");
  }
  await access(hostPath, constants.X_OK);

  const [identity, gecko, template] = await Promise.all([
    json(join(root, "host-identity.json")),
    json(join(root, "..", "extensions", "webextension", "firefox", "gecko.json")),
    json(join(directory, "host-manifest.template.json"))
  ]);
  if (identity.name !== "org.pdfmagic.opener" ||
      gecko.gecko?.id !== developmentId ||
      JSON.stringify(Object.keys(template).sort()) !==
        JSON.stringify(["allowed_extensions", "description", "name", "path", "type"]) ||
      template.name !== identity.name ||
      template.type !== "stdio" || template.path !== slot ||
      !Array.isArray(template.allowed_extensions) ||
      JSON.stringify(template.allowed_extensions) !== JSON.stringify([gecko.gecko.id])) {
    throw new Error("Firefox host identity or allowed extension ID does not match the reviewed development manifest");
  }
  return { ...template, path: hostPath };
}

export async function registerFirefoxHost({ hostPath, development = false, home, platform } = {}) {
  // Only the current development Gecko ID is reviewed. Production add-on identity,
  // Mozilla signing, and authentication are separate tasks, not implicit grants.
  if (development !== true) {
    throw new Error("Current Firefox add-on ID is development-only; pass --development explicitly");
  }
  const manifest = await firefoxHostManifest(hostPath);
  const folder = firefoxRegistrationPath({ home, platform });
  const destination = join(folder, manifest.name + ".json");
  await mkdir(folder, { recursive: true, mode: 0o700 });
  const folderInfo = await lstat(folder);
  if (!folderInfo.isDirectory() || folderInfo.isSymbolicLink()) {
    throw new Error("Refusing Firefox registration directory that is not a real directory");
  }
  const serialized = JSON.stringify(manifest, null, 2) + "\n";
  try {
    const existing = await lstat(destination);
    if (!existing.isFile() || existing.isSymbolicLink() ||
        await readFile(destination, "utf8") !== serialized) {
      throw new Error("Refusing to overwrite an existing Firefox host registration");
    }
    return destination;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  // Atomic, no-clobber publication: a concurrent install cannot overwrite a
  // pre-existing user-managed manifest. The temporary file stays owner-only.
  const scratch = await mkdtemp(join(folder, ".pdfmagic-firefox-"));
  try {
    const staged = join(scratch, "manifest.json");
    await writeFile(staged, serialized, { flag: "wx", mode: 0o600 });
    await link(staged, destination);
  } finally {
    await rm(scratch, { recursive: true, force: true });
  }
  return destination;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length !== 3 || args[0] !== "--host" || args[2] !== "--development") {
    console.error("Usage: node native-messaging/firefox/register.mjs --host /absolute/path/to/native-host --development");
    process.exitCode = 2;
  } else {
    registerFirefoxHost({ hostPath: args[1], development: true })
      .then((path) => console.log("Registered Firefox development host at " + path))
      .catch((error) => { console.error(error.message); process.exitCode = 1; });
  }
}
