import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, lstat, mkdir, mkdtemp, readFile, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  firefoxHostManifest, registerFirefoxHost
} from "../../../native-messaging/firefox/register.mjs";

const development = true;

async function fixture(t) {
  const home = await mkdtemp(join(tmpdir(), "pdfmagic-host-app-update-"));
  t.after(() => rm(home, { recursive: true, force: true }));
  const hostPath = join(home, "pdf-magic-native-host");
  await writeFile(hostPath, "#!/bin/sh\nprintf 'original-version\\n'\n", { mode: 0o700 });
  await chmod(hostPath, 0o700);
  return { home, hostPath };
}

for (const platform of ["darwin", "linux"]) {
  test("Firefox " + platform + " registration survives an atomic same-path application update", async (t) => {
    const { home, hostPath } = await fixture(t);
    const destination = await registerFirefoxHost({ hostPath, home, platform, development });
    const before = await readFile(destination, "utf8");
    const beforeInode = (await lstat(destination)).ino;
    const neighbour = join(home, "user-preferences.json");
    await writeFile(neighbour, "{\"custom\":true}\n");

    const nextVersion = join(home, "staged-native-host");
    await writeFile(nextVersion, "#!/bin/sh\nprintf 'updated-version\\n'\n", { mode: 0o700 });
    await chmod(nextVersion, 0o700);
    await rename(nextVersion, hostPath);
    assert.equal(execFileSync(hostPath, { encoding: "utf8" }).trim(), "updated-version");

    assert.equal(await registerFirefoxHost({ hostPath, home, platform, development }), destination);
    assert.equal(await readFile(destination, "utf8"), before, "manifest must remain unchanged");
    assert.equal((await lstat(destination)).ino, beforeInode, "no registration rewrite");
    assert.equal(JSON.parse(before).path, hostPath);
    assert.equal(await readFile(neighbour, "utf8"), "{\"custom\":true}\n");
    assert.deepEqual(await firefoxHostManifest(hostPath), JSON.parse(before));
  });

  test("Firefox " + platform + " relocated update is not automatically registered", async (t) => {
    const { home, hostPath } = await fixture(t);
    const destination = await registerFirefoxHost({ hostPath, home, platform, development });
    const before = await readFile(destination, "utf8");
    const newPath = join(home, "UpdatedApplication.app", "Contents", "MacOS", "native-host");
    await mkdir(join(home, "UpdatedApplication.app", "Contents", "MacOS"), { recursive: true });
    await rename(hostPath, newPath);

    await assert.rejects(firefoxHostManifest(hostPath), { code: "ENOENT" });
    await assert.rejects(
      registerFirefoxHost({ hostPath: newPath, home, platform, development }),
      /Refusing to overwrite an existing Firefox host registration/
    );
    assert.equal((await readFile(destination, "utf8")), before);
    assert.equal(JSON.parse(before).path, hostPath, "stale registration is not claimed healthy");
    assert.equal(execFileSync(newPath, { encoding: "utf8" }).trim(), "original-version");
  });
}

test("the application-update check does not enable browser-to-native PDF actions", async () => {
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.equal(manifest.incognito, "not_allowed");
  assert.match(manifest.action.default_title, /not active/);
});
