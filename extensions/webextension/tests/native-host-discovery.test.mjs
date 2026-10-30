import assert from "node:assert/strict";
import { chmod, lstat, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { HOST_NAME, lookupDirectory, verifyHostDiscovery } from "../../../native-messaging/verify-host-discovery.mjs";

const ID = "abcdefghijklmnopabcdefghijklmnop";
const origin = "chrome-extension://" + ID + "/";

async function fixture(t) {
  const home = await mkdtemp(join(tmpdir(), "pdfmagic-native-discovery-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const executable = join(home, "host");
  await writeFile(executable, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(executable, 0o700);
  return { home, executable };
}

async function installFixture(browser, { home, executable }, options = {}) {
  const directory = lookupDirectory(browser, { home, platform: options.platform ?? "darwin",
    browserMajor: options.browserMajor });
  await mkdir(directory, { recursive: true });
  const path = join(directory, HOST_NAME + ".json");
  const manifest = { name: HOST_NAME, description: "Transport-only test host", path: executable,
    type: "stdio", [browser === "firefox" ? "allowed_extensions" : "allowed_origins"]:
      [browser === "firefox" ? "pdf-magic-opener@example.invalid" : origin] };
  await writeFile(path, JSON.stringify(manifest), { mode: 0o600 });
  return { path, manifest };
}

test("browser-specific macOS discovery uses separate paths and documented Opera fallback", () => {
  const home = "/Users/test";
  const paths = Object.fromEntries(["chrome", "chromium", "edge", "brave", "vivaldi", "arc", "opera", "firefox"]
    .map(browser => [browser, lookupDirectory(browser, { home })]));
  assert.equal(new Set(Object.values(paths)).size, 7);
  assert.equal(paths.opera, paths.chrome);
  assert.equal(paths.firefox, "/Users/test/Library/Application Support/Mozilla/NativeMessagingHosts");
  assert.equal(paths.arc, "/Users/test/Library/Application Support/Arc/User Data/NativeMessagingHosts");
  assert.equal(lookupDirectory("chrome-for-testing", { home, browserMajor: 145 }), paths.chrome);
  assert.notEqual(lookupDirectory("chrome-for-testing", { home, browserMajor: 146 }), paths.chrome);
  assert.throws(() => lookupDirectory("chrome-for-testing", { home }), /version/);
  assert.throws(() => lookupDirectory("chrome", { home: "relative" }), /absolute/);
  assert.throws(() => lookupDirectory("safari", { home }), /Unsupported/);
  assert.throws(() => lookupDirectory("edge", { home, platform: "win32" }), /Unsupported/);
  assert.equal(lookupDirectory("firefox", { home: "/home/test", platform: "linux" }),
    "/home/test/.mozilla/native-messaging-hosts");
});

test("a browser does not see a host registered only for another browser", async t => {
  const env = await fixture(t);
  const chrome = await installFixture("chrome", env);
  assert.equal((await verifyHostDiscovery({ browser: "chrome", home: env.home, platform: "darwin", expectedExtensionId: ID })).status,
    "registration-valid");
  assert.equal((await verifyHostDiscovery({ browser: "edge", home: env.home, platform: "darwin" })).status,
    "unregistered");
  assert.equal((await verifyHostDiscovery({ browser: "firefox", home: env.home, platform: "darwin" })).status,
    "unregistered");
  assert.equal((await verifyHostDiscovery({ browser: "opera", home: env.home, platform: "darwin" })).status,
    "registration-valid");
  assert.equal(JSON.parse(await readFile(chrome.path, "utf8")).name, HOST_NAME);
});

test("each supported Chromium browser checks its own lookup directory", async t => {
  const env = await fixture(t);
  for (const browser of ["chromium", "edge", "brave", "vivaldi", "arc"]) {
    const { path } = await installFixture(browser, env);
    const result = await verifyHostDiscovery({ browser, home: env.home, platform: "darwin", expectedExtensionId: ID });
    assert.equal(result.manifestPath, path);
    assert.equal(result.browserHandshakeVerified, false);
    assert.equal(result.status, ["brave", "vivaldi", "arc"].includes(browser)
      ? "candidate-registration-valid" : "registration-valid");
  }
});

test("Firefox requires Gecko allowed_extensions, not Chromium origins", async t => {
  const env = await fixture(t);
  await installFixture("firefox", env);
  assert.equal((await verifyHostDiscovery({ browser: "firefox", home: env.home, platform: "darwin",
    expectedExtensionId: "pdf-magic-opener@example.invalid" })).status, "registration-valid");
  assert.equal((await verifyHostDiscovery({ browser: "firefox", home: env.home, platform: "darwin",
    expectedExtensionId: "not-approved@example.com" })).status, "invalid");
  const linux = await fixture(t);
  await installFixture("firefox", linux, { platform: "linux" });
  assert.equal((await verifyHostDiscovery({ browser: "firefox", home: linux.home, platform: "linux" })).status,
    "registration-valid");
});

test("malformed host, origin, executable and extra keys never verify", async t => {
  const env = await fixture(t);
  const { path, manifest } = await installFixture("chrome", env);
  for (const changed of [
    { ...manifest, allowed_origins: ["*"] },
    { ...manifest, allowed_origins: ["chrome-extension://evil/"] },
    { ...manifest, allowed_origins: [] },
    { ...manifest, allowed_origins: [origin, origin] },
    { ...manifest, allowed_origins: [origin], allowed_extensions: ["someone@example.com"] },
    { ...manifest, path: "relative-host" },
    { ...manifest, type: "http" },
    { ...manifest, name: "other.host" },
  ]) {
    await writeFile(path, JSON.stringify(changed));
    assert.equal((await verifyHostDiscovery({ browser: "chrome", home: env.home, platform: "darwin" })).status,
      "invalid");
  }
  await writeFile(path, JSON.stringify(manifest));
  await chmod(env.executable, 0o600);
  assert.equal((await verifyHostDiscovery({ browser: "chrome", home: env.home, platform: "darwin" })).status,
    "invalid");
  await chmod(env.executable, 0o700);
  await writeFile(path, "{bad-json");
  assert.equal((await verifyHostDiscovery({ browser: "chrome", home: env.home, platform: "darwin" })).status,
    "invalid");
});

test("symlinked manifest or directory is unsafe and leaves targets untouched", async t => {
  const env = await fixture(t);
  const { path } = await installFixture("chrome", env);
  const original = await readFile(path);
  const linked = join(env.home, "backup");
  await writeFile(linked, original);
  await rm(path);
  await symlink(linked, path);
  assert.equal((await verifyHostDiscovery({ browser: "chrome", home: env.home, platform: "darwin" })).status,
    "unsafe");
  assert.deepEqual(await readFile(linked), original);
  await rm(path);
  const directory = dirname(path);
  await rm(directory, { recursive: true });
  await symlink(env.home, directory, "dir");
  assert.equal((await verifyHostDiscovery({ browser: "chrome", home: env.home, platform: "darwin" })).status,
    "unsafe");
  assert.equal((await lstat(join(env.home, "host"))).isFile(), true);
});

test("verification never enables nativeMessaging or claims runtime handshake", async t => {
  const env = await fixture(t);
  const { path } = await installFixture("chrome", env);
  const before = await readFile(path);
  const result = await verifyHostDiscovery({ browser: "chrome", home: env.home, platform: "darwin" });
  assert.equal(result.browserHandshakeVerified, false);
  assert.deepEqual(await readFile(path), before);
  const ext = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.deepEqual(ext.permissions, []);
  assert.deepEqual(ext.host_permissions, []);
  assert.deepEqual(ext.optional_permissions, ["downloads"]);
});
