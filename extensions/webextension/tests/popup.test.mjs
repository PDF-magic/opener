import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { validatePopupAsset } from "../scripts/popup-assets.mjs";

const root = fileURLToPath(new URL("../", import.meta.url));

test("toolbar popup is local, accessible and explicitly inactive in both builds", async () => {
  const manifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  assert.equal(manifest.action.default_title, "PDF Magic Opener (not active)");
  assert.equal(manifest.action.default_popup, "popup.html");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  const html = await readFile(join(root, "src", "popup.html"), "utf8");
  const css = await readFile(join(root, "src", "popup.css"), "utf8");
  assert.doesNotThrow(() => validatePopupAsset("popup.html", html));
  assert.doesNotThrow(() => validatePopupAsset("popup.css", css));
  assert.match(html, /<main\b[^>]*aria-labelledby=/);
  assert.match(html, /<h1\b[^>]*>PDF Magic Opener<\/h1>/);
  assert.match(html, /role="status"/);
  assert.match(html, /Not active/);
  assert.match(html, /cannot scan, sanitize, or open PDF files yet/);
  assert.match(html, /<meta name="viewport"/);
  assert.match(html, /id="openPDFMagicPreferences" href="pdfmagicopener:\/\/preferences"/);
  assert.match(css, /prefers-color-scheme: dark/);
  for (const target of ["dist", "dist/firefox"]) {
    const built = JSON.parse(await readFile(join(root, target, "manifest.json"), "utf8"));
    assert.equal(built.action.default_popup, "popup.html");
    for (const name of ["popup.html", "popup.css"]) {
      assert.equal(await readFile(join(root, target, name), "utf8"),
        await readFile(join(root, "src", name), "utf8"));
    }
  }
});

test("popup validator rejects active controls, remote resources and injection", () => {
  const baseline = '<!doctype html>\n<html lang="en">\n<link rel="stylesheet" href="popup.css"><p role="status">Not active</p><p>cannot scan, sanitize, or open PDF files yet.</p><a id="openPDFMagicPreferences" href="pdfmagicopener://preferences">Open PDF Magic Preferences</a></html>';
  assert.doesNotThrow(() => validatePopupAsset("popup.html", baseline));
  for (const injected of [
    '<script>alert(1)</script>', '<button>Scan</button>', '<form></form>',
    '<a href="options.html">Options</a>', '<iframe></iframe>',
    'onclick = "scan()"', 'https://example.com', 'javascript:scan()',
    'data:text/html', '<input type="file">'
  ]) assert.throws(() => validatePopupAsset("popup.html", baseline + injected));
  for (const badCss of ["@import 'remote.css'", "background: url(foo.png)",
                        "color: expression(alert(1))"]) {
    assert.throws(() => validatePopupAsset("popup.css", badCss + "/* prefers-color-scheme */"));
  }
  assert.throws(() => validatePopupAsset("../popup.html", baseline));
  assert.throws(() => validatePopupAsset("popup.html", "<div>Active</div>"));
});
