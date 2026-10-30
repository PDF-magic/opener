import assert from "node:assert/strict";
import { constants } from "node:fs";
import { access, chmod, lstat, mkdtemp, mkdir, readFile, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  firefoxHostManifest, firefoxRegistrationPath, registerFirefoxHost
} from "../../../native-messaging/firefox/register.mjs";

const sourceRoot = new URL("../../../native-messaging/", import.meta.url);
const readJson = async (url) => JSON.parse(await readFile(url, "utf8"));

async function fixture(t) {
  const { rm } = await import("node:fs/promises");
  const home = await mkdtemp(join(tmpdir(), "pdfmagic-firefox-host-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const hostPath = join(home, "native-host");
  await writeFile(hostPath, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  await chmod(hostPath, 0o700);
  return { home, hostPath };
}

test("Firefox template approves exactly the currently declared development Gecko ID", async (t) => {
  const { hostPath } = await fixture(t);
  const template = await readJson(new URL("../../../native-messaging/firefox/host-manifest.template.json", import.meta.url));
  const identity = await readJson(new URL("host-identity.json", sourceRoot));
  const gecko = await readJson(new URL("../firefox/gecko.json", import.meta.url));
  assert.equal(identity.name, "org.pdfmagic.opener");
  assert.deepEqual(template.allowed_extensions, [gecko.gecko.id]);
  assert.equal(gecko.gecko.id, "pdf-magic-opener@example.invalid");
  assert.equal(template.type, "stdio");
  assert.equal(template.name, identity.name);
  assert.equal(template.path, "__PDF_MAGIC_NATIVE_HOST_ABSOLUTE_PATH__");
  assert.deepEqual(await firefoxHostManifest(hostPath), { ...template, path: hostPath });
});

test("Firefox uses only the correct per-user macOS and Linux registration locations", () => {
  assert.equal(firefoxRegistrationPath({ home: "/Users/demo", platform: "darwin" }),
    "/Users/demo/Library/Application Support/Mozilla/NativeMessagingHosts");
  assert.equal(firefoxRegistrationPath({ home: "/home/demo", platform: "linux" }),
    "/home/demo/.mozilla/native-messaging-hosts");
  assert.throws(() => firefoxRegistrationPath({ home: "/Users/demo", platform: "win32" }));
  assert.throws(() => firefoxRegistrationPath({ home: "relative", platform: "darwin" }));
});

for (const platform of ["darwin", "linux"]) {
  test("opt-in " + platform + " registration writes an exact native messaging manifest, atomically and idempotently", async (t) => {
    const { home, hostPath } = await fixture(t);
    const directory = firefoxRegistrationPath({ home, platform });
    await assert.rejects(registerFirefoxHost({ hostPath, home, platform }), /development-only/);
    await assert.rejects(access(directory, constants.F_OK), { code: "ENOENT" });
    const path = await registerFirefoxHost({ hostPath, home, platform, development: true });
    assert.equal(path, join(directory, "org.pdfmagic.opener.json"));
    assert.deepEqual(await readJson(new URL("file://" + path)), await firefoxHostManifest(hostPath));
    assert.equal((await lstat(path)).mode & 0o777, 0o600);
    assert.equal(await registerFirefoxHost({ hostPath, home, platform, development: true }), path);
    const modified = { ...(await firefoxHostManifest(hostPath)), allowed_extensions: ["other@example.com"] };
    await writeFile(path, JSON.stringify(modified), "utf8");
    await assert.rejects(registerFirefoxHost({ hostPath, home, platform, development: true }), /Refusing to overwrite/);
    assert.deepEqual(JSON.parse(await readFile(path, "utf8")), modified, "preserve user modifications");
  });
}

test("refuses nonexistent, nonexecutable, directory, relative and symlink host paths", async (t) => {
  const { home, hostPath } = await fixture(t);
  await assert.rejects(firefoxHostManifest("relative-host"), /absolute/);
  await assert.rejects(firefoxHostManifest(join(home, "missing")), { code: "ENOENT" });
  await chmod(hostPath, 0o600);
  await assert.rejects(firefoxHostManifest(hostPath), /executable/);
  await chmod(hostPath, 0o700);
  await mkdir(join(home, "directory"));
  await assert.rejects(firefoxHostManifest(join(home, "directory")), /executable/);
  const symlinkPath = join(home, "host-link");
  await symlink(hostPath, symlinkPath);
  await assert.rejects(firefoxHostManifest(symlinkPath), /symlink/);
});

test("refuses a symlinked registration directory without changing its target", async (t) => {
  const { home, hostPath } = await fixture(t);
  const folder = firefoxRegistrationPath({ home, platform: "linux" });
  await mkdir(join(home, ".mozilla"));
  const redirect = join(home, "redirect");
  await mkdir(redirect);
  await symlink(redirect, folder);
  await assert.rejects(registerFirefoxHost({ hostPath, home, platform: "linux", development: true }), /real directory/);
  assert.deepEqual(await (await import("node:fs/promises")).readdir(redirect), []);
});

test("registration changes neither extension privileges nor the scanner integration", async () => {
  const manifest = await readJson(new URL("../manifest.json", import.meta.url));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.equal(manifest.background.service_worker, "background.js");
});
