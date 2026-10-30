import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));

test("CI must load the actual Chrome ZIP in Chrome for Testing", async () => {
  const workflow = await readFile(join(root, "../../.github/workflows/ci.yml"), "utf8");
  assert.match(workflow, /chrome-package-smoke:/);
  assert.match(workflow, /browser-actions\/setup-chrome@v2/);
  assert.match(workflow, /chrome-version: stable/);
  assert.match(workflow, /npm run package:chrome/);
  assert.match(workflow, /unzip -q "dist\/chrome\/pdf-magic-opener-chrome-/);
  assert.match(workflow, /node scripts\/test-chrome\.mjs "\$CHROME_PATH" "\$PACKAGE_DIR"/);
  assert.match(workflow, /name: Chrome package smoke test/);
});

test("Chrome smoke harness checks browser installation and inert UI without opening PDFs", async () => {
  const script = await readFile(join(root, "scripts/test-chrome.mjs"), "utf8");
  for (const required of [
    "--load-extension=", "--headless=new", "--user-data-dir=",
    "Target.getTargets", "Target.createTarget", "Target.attachToTarget",
    "Runtime.evaluate", "chrome.runtime.getManifest",
    "chrome-extension://", "not_allowed", "scanDisabled",
    "pdfmagicopener://preferences", "Not active"
  ]) {
    assert.ok(script.includes(required), "Missing real Chrome assertion: " + required);
  }
  for (const forbidden of [
    "chrome.permissions.request", "chrome.tabs.create", "window.open(",
    "https://example", "NSWorkspace", "clamscan("
  ]) {
    assert.equal(script.includes(forbidden), false, "Unexpected activation: " + forbidden);
  }
  assert.match(script, /await rm\(profile, \{ recursive: true, force: true \}\)/);
});
