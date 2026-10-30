#!/usr/bin/env node
// Read-only inspection of native host lookup candidates. No browser or host is launched.
import { constants } from "node:fs";
import { access, lstat, readFile } from "node:fs/promises";
import { homedir, platform as currentPlatform } from "node:os";
import { isAbsolute, join, parse, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const sourceRoot = fileURLToPath(new URL("./", import.meta.url));
const identity = JSON.parse(await readFile(join(sourceRoot, "host-identity.json"), "utf8"));
export const HOST_NAME = identity.name;
const filename = HOST_NAME + ".json";
// Reuse opener-0642's reviewed browser inventory rather than declaring new paths.
const inventory = JSON.parse(await readFile(join(sourceRoot, "chromium-registration-targets.json"), "utf8"));
const browserKeys = {
  "Google Chrome": "chrome", "Chromium": "chromium",
  "Google Chrome for Testing": "chrome-for-testing", "Microsoft Edge": "edge",
  "Brave": "brave", "Vivaldi": "vivaldi", "Arc": "arc", "Opera": "opera"
};
const prefix = "~/Library/Application Support/";
const suffix = "/NativeMessagingHosts";
if (inventory.hostName !== HOST_NAME || inventory.platform !== "macOS" ||
    inventory.targets.length !== Object.keys(browserKeys).length) {
  throw new Error("Native host lookup inventory is incomplete or mismatched");
}
const macUserLocations = Object.freeze(Object.fromEntries([
  ...inventory.targets.map(target => {
    if (!browserKeys[target.browser] ||
        !target.userManifestDirectory.startsWith(prefix) ||
        !target.userManifestDirectory.endsWith(suffix)) {
      throw new Error("Unsupported browser or invalid lookup location");
    }
    return [browserKeys[target.browser],
      target.userManifestDirectory.slice(prefix.length, -suffix.length)];
  }),
  ["firefox", "Mozilla"]
]));
const unconfirmedLocations = new Set(inventory.targets
  .filter(target => target.evidence !== "publisher-documented")
  .map(target => browserKeys[target.browser]));
const chromeOrigin = /^chrome-extension:\/\/[a-p]{32}\/$/;

export function lookupDirectory(browser, { home, platform = "darwin", browserMajor } = {}) {
  if (typeof home !== "string" || !isAbsolute(home)) {
    throw new Error("A real absolute home directory is required");
  }
  if (browser === "chrome-for-testing") {
    if (platform !== "darwin" || !Number.isSafeInteger(browserMajor) || browserMajor < 1) {
      throw new Error("Chrome for Testing requires macOS and an explicitly verified browser major version");
    }
    return join(home, "Library/Application Support",
      macUserLocations[browserMajor >= 146 ? "chrome-for-testing" : "chrome"], "NativeMessagingHosts");
  }
  if (browser === "firefox" && platform === "linux") {
    return join(home, ".mozilla/native-messaging-hosts");
  }
  const relativePath = macUserLocations[browser];
  if (platform !== "darwin" || !relativePath) throw new Error("Unsupported browser/platform lookup");
  return join(home, "Library/Application Support", relativePath, "NativeMessagingHosts");
}

async function requireSafeRegular(path, { executable = false } = {}) {
  const metadata = await lstat(path);
  if (!metadata.isFile() || metadata.isSymbolicLink()) throw new Error("Not a regular file or is a symlink");
  if (executable && !(metadata.mode & 0o111)) throw new Error("Host path is not executable");
  if (executable) await access(path, constants.X_OK);
  return metadata;
}

async function requireSafePath(home, target) {
  const normalizedHome = resolve(home);
  const rel = relative(normalizedHome, target);
  if (rel === "" || rel === ".." || rel.startsWith(".." + sep) || isAbsolute(rel)) {
    throw new Error("Registration location must be beneath the selected home");
  }
  // Never traverse a symlinked home, registration directory, or manifest.
  let path = parse(normalizedHome).root;
  for (const component of normalizedHome.slice(path.length).split(sep).filter(Boolean)) {
    path = join(path, component);
    const current = await lstat(path);
    if (!current.isDirectory() || current.isSymbolicLink()) throw new Error("Unsafe home directory chain");
  }
  for (const component of rel.split(sep).slice(0, -1)) {
    path = join(path, component);
    const current = await lstat(path);
    if (!current.isDirectory() || current.isSymbolicLink()) throw new Error("Unsafe registration directory chain");
  }
  await requireSafeRegular(target);
}

async function validateManifest(path, browser, expectedExtensionId) {
  const metadata = await requireSafeRegular(path);
  if (metadata.size > 65536 || metadata.size === 0) throw new Error("Manifest size is not bounded");
  const document = JSON.parse(await readFile(path, "utf8"));
  if (!document || Array.isArray(document) || typeof document !== "object" ||
      document.name !== HOST_NAME || document.type !== "stdio" ||
      typeof document.description !== "string" || !document.description.trim() ||
      typeof document.path !== "string" || !isAbsolute(document.path)) {
    throw new Error("Invalid native host manifest identity, transport or executable path");
  }
  // Only metadata inspection: no executable invocation, no scanner or PDF access.
  await requireSafeRegular(document.path, { executable: true });
  const firefox = browser === "firefox";
  const key = firefox ? "allowed_extensions" : "allowed_origins";
  const ids = document[key];
  if (Object.keys(document).sort().join(",") !==
      ["name", "description", "path", "type", key].sort().join(",") ||
      !Array.isArray(ids) || ids.length === 0 || ids.length !== new Set(ids).size) {
    throw new Error("Unexpected manifest fields or invalid extension allowlist");
  }
  if (firefox) {
    if (ids.some(id => typeof id !== "string" || id.length > 255 || !/^[A-Za-z0-9._@{}-]+$/.test(id))) {
      throw new Error("Invalid Firefox extension ID");
    }
  } else if (ids.some(origin => typeof origin !== "string" || !chromeOrigin.test(origin))) {
    throw new Error("Invalid Chromium extension origin");
  }
  if (expectedExtensionId !== undefined) {
    if (typeof expectedExtensionId !== "string" || !expectedExtensionId ||
        !ids.includes(firefox ? expectedExtensionId : "chrome-extension://" + expectedExtensionId + "/")) {
      throw new Error("Expected extension ID is not approved by the installed host manifest");
    }
  }
  return { hostPath: document.path, allowedIds: ids.length };
}

export async function verifyHostDiscovery({ browser, home = homedir(), platform = currentPlatform(),
  browserMajor, expectedExtensionId } = {}) {
  const directory = lookupDirectory(browser, { home, platform, browserMajor });
  const manifestPath = join(directory, filename);
  const report = { browser, manifestPath, status: "unregistered", browserHandshakeVerified: false };
  try {
    await requireSafePath(home, manifestPath);
  } catch (error) {
    if (error?.code === "ENOENT") return report;
    return { ...report, status: "unsafe", reason: error.message };
  }
  try {
    const validated = await validateManifest(manifestPath, browser, expectedExtensionId);
    return { ...report, status: unconfirmedLocations.has(browser) ? "candidate-registration-valid" : "registration-valid",
      ...validated };
  } catch (error) {
    return { ...report, status: "invalid", reason: error.message };
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if ((args.length % 2) !== 0 || args.some((a, i) => i % 2 === 0 &&
      !["--browser", "--home", "--platform", "--browser-major", "--extension-id"].includes(a))) {
    console.error("Usage: node native-messaging/verify-host-discovery.mjs --browser chrome [--home /absolute/home] [--extension-id id] [--browser-major 146]");
    process.exitCode = 2;
  } else {
    const flags = Object.fromEntries(Array.from({ length: args.length / 2 }, (_, i) => [args[i * 2], args[i * 2 + 1]]));
    const browserMajor = flags["--browser-major"] === undefined ? undefined : Number(flags["--browser-major"]);
    try {
      const result = await verifyHostDiscovery({ browser: flags["--browser"],
        home: flags["--home"] ?? homedir(), platform: flags["--platform"] ?? currentPlatform(),
        browserMajor, expectedExtensionId: flags["--extension-id"] });
      console.log(JSON.stringify(result, null, 2));
      if (!["registration-valid", "candidate-registration-valid"].includes(result.status)) process.exitCode = 1;
    } catch (error) {
      console.error(error.message);
      process.exitCode = 2;
    }
  }
}
