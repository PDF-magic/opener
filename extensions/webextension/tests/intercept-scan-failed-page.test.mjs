import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  FAILED_INTERCEPTION_PAGE, FAILED_INTERCEPTION_CSS,
  validateFailedInterceptionAsset
} from "../scripts/intercept-scan-failed-assets.mjs";
import { CHROME_PACKAGE_FILES } from "../scripts/chrome-zip.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));
const read = name => readFile(join(root, "src", name), "utf8");

test("a blocked, static and accessible failure-only page is always rendered", async () => {
  const html = await read(FAILED_INTERCEPTION_PAGE);
  const css = await read(FAILED_INTERCEPTION_CSS);
  assert.doesNotThrow(() => validateFailedInterceptionAsset(FAILED_INTERCEPTION_PAGE, html));
  assert.doesNotThrow(() => validateFailedInterceptionAsset(FAILED_INTERCEPTION_CSS, css));
  for (const phrase of [
    'role="alert" aria-labelledby="scan-failure-title"',
    "PDF blocked: scan did not complete",
    "not verified by the required scanner",
    "will not open or release this PDF",
    "Close this tab",
    "cannot prevent opening in other browser viewers, Finder, or other applications"
  ]) assert.ok(html.includes(phrase), phrase);
  assert.match(css, /prefers-color-scheme: dark/);
  assert.doesNotMatch(html, /<\s*(?:script|button|a|iframe|form|img)\b|https?:\/\/|file:\/\//i);
  assert.doesNotMatch(css, /@import|url\s*\(/i);
});

test("validator refuses executable or bypassing content, false success and external resources", async () => {
  const original = await read(FAILED_INTERCEPTION_PAGE);
  const css = await read(FAILED_INTERCEPTION_CSS);
  for (const changed of [
    original.replace("Close this tab.", "<button>Open anyway</button>Close this tab."),
    original.replace("</body>", "<script>alert(1)</script></body>"),
    original.replace("</body>", '<iframe src="/secret.pdf"></iframe></body>'),
    original.replace("</body>", '<a href="https://example.test/file.pdf">Open</a></body>'),
    original.replace("</body>", '<img src="data:image/png;base64,AAAA"></body>'),
    original.replace("</body>", '<div onclick="go()">Open</div></body>'),
    original.replace("PDF blocked: scan did not complete", "PDF ready to open"),
    original.replace("will not open or release this PDF.", "will open this PDF."),
    original.replace('role="alert"', 'role="status"'),
    original.replace('href="intercept-scan-failed.css"', 'href="https://example.test/style.css"'),
    original.replace("</body>", '<meta http-equiv="refresh" content="0;url=/document.pdf"></body>')
  ]) assert.throws(() => validateFailedInterceptionAsset(FAILED_INTERCEPTION_PAGE, changed));
  for (const changed of [
    css + '\n@import "https://example.test/style.css";',
    css + '\n.blocked { background: url(/private.pdf); }',
    css.replace("prefers-color-scheme: dark", "prefers-color-scheme: light")
  ]) assert.throws(() => validateFailedInterceptionAsset(FAILED_INTERCEPTION_CSS, changed));
  assert.throws(() => validateFailedInterceptionAsset("other.html", original));
  assert.throws(() => validateFailedInterceptionAsset(FAILED_INTERCEPTION_PAGE, null));
});

test("both extension builds include exactly the validated static page assets", async () => {
  for (const name of [FAILED_INTERCEPTION_PAGE, FAILED_INTERCEPTION_CSS]) {
    assert.equal(CHROME_PACKAGE_FILES.filter(entry => entry === name).length, 1);
    const source = await read(name);
    for (const variant of ["", "firefox"]) {
      const built = await readFile(join(root, "dist", variant, name), "utf8");
      assert.equal(built, source);
    }
  }
  const manifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(manifest.web_accessible_resources, undefined);
  assert.equal(manifest.content_scripts, undefined);
  assert.ok((await read("background.js")).trimEnd().endsWith("void 0;"));
});

test("existing CI invokes the failure page test and both builders validate the page", async () => {
  const ci = await readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8");
  assert.match(ci, /node --test tests\/intercept-scan-failed-page\.test\.mjs/);
  for (const script of ["build.mjs", "build-firefox.mjs"]) {
    assert.match(await readFile(join(root, "scripts", script), "utf8"),
      /copyFailedInterceptionAssets\(root, output\)/);
  }
});
