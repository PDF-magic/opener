import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { validatePopupAsset } from "../scripts/popup-assets.mjs";
import { createScanPdfAction, SCAN_PDF_UNAVAILABLE_MESSAGE } from "../src/scan-pdf-action.js";

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
  assert.ok(html.includes('<button id="scanPDF" type="button" disabled aria-disabled="true" aria-describedby="scanPDFUnavailable">Scan PDF</button>'));
  assert.ok(html.includes('<p id="scanPDFUnavailable">Scan PDF is unavailable until a verified native scanner is connected.</p>'));
  assert.ok(html.includes('<button id="scanThisPDF" type="button" disabled aria-disabled="true" aria-describedby="scanThisPDFUnavailable">Scan This PDF</button>'));
  assert.ok(html.includes('<p id="scanThisPDFUnavailable">Scan This PDF is unavailable until a verified native scanner and trusted current-PDF selection are connected.</p>'));
  assert.match(html, /<section class="unsupported-action" aria-labelledby="current-pdf-title">/);
  assert.match(html, /<h2 id="current-pdf-title">Current PDF<\/h2>/);
  assert.match(css, /button:disabled/);
  assert.equal(createScanPdfAction().state().enabled, false);
  assert.equal(SCAN_PDF_UNAVAILABLE_MESSAGE,
    "Scan PDF is unavailable until a verified native scanner is connected.");
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
  const baseline = '<!doctype html>\n<html lang="en">\n<link rel="stylesheet" href="popup.css"><p role="status">Not active</p><p>cannot scan, sanitize, or open PDF files yet.</p><a id="openPDFMagicPreferences" href="pdfmagicopener://preferences">Open PDF Magic Preferences</a><button id="scanPDF" type="button" disabled aria-disabled="true" aria-describedby="scanPDFUnavailable">Scan PDF</button><p id="scanPDFUnavailable">Scan PDF is unavailable until a verified native scanner is connected.</p><button id="scanThisPDF" type="button" disabled aria-disabled="true" aria-describedby="scanThisPDFUnavailable">Scan This PDF</button><p id="scanThisPDFUnavailable">Scan This PDF is unavailable until a verified native scanner and trusted current-PDF selection are connected.</p><section class="interception-state" aria-labelledby="interception-state-title"><h2 id="interception-state-title">Automatic PDF interception</h2><p id="automaticInterceptionEffectiveStatus" role="status">Status: Inactive</p><p>No verified browser interception or native scan-before-render connection is active. Saved opt-in preferences do not change this status.</p></section><section class="scan-result" aria-labelledby="explicit-pdf-result-title"><h2 id="explicit-pdf-result-title">Scan result</h2><p id="explicitPdfScanResult" role="status" aria-live="polite">No verified scan result is available.</p></html>';
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

test("Scan This PDF toolbar action remains disabled until trusted native PDF selection exists", async () => {
  const html = await readFile(join(root, "src", "popup.html"), "utf8");
  const control = '<button id="scanThisPDF" type="button" disabled aria-disabled="true" aria-describedby="scanThisPDFUnavailable">Scan This PDF</button>';
  const explanation = '<p id="scanThisPDFUnavailable">Scan This PDF is unavailable until a verified native scanner and trusted current-PDF selection are connected.</p>';
  assert.doesNotThrow(() => validatePopupAsset("popup.html", html));
  assert.equal(html.split(control).length, 2);
  assert.equal(html.split(explanation).length, 2);
  const mutations = [
    html.replace(control, control.replace(" disabled aria-disabled", " aria-disabled")),
    html.replace(control, control.replace('aria-disabled="true"', 'aria-disabled="false"')),
    html.replace(control, control.replace('type="button"', 'type="submit"')),
    html.replace(control, control.replace('aria-describedby="scanThisPDFUnavailable"', 'aria-describedby="missing"')),
    html.replace(control, control.replace('id="scanThisPDF"', 'id="scanPDF"')),
    html.replace(control, ""),
    html.replace(explanation, ""),
    html.replace(control, control + control),
    html.replace(explanation, explanation + explanation),
    html.replace(explanation, explanation.replace("trusted current-PDF selection", "any page URL")),
    html.replace("</section>", '<button id="scanAnyFile">Scan</button></section>'),
    html.replace("</section>", '<script>scanDocument()</script></section>')
  ];
  for (const mutation of mutations) {
    assert.notEqual(mutation, html);
    assert.throws(() => validatePopupAsset("popup.html", mutation),
      /Unsafe WebExtensions popup asset/);
  }
  const manifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  assert.equal(manifest.action.default_popup, "popup.html");
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.permissions, []);
});

test("unsupported Scan PDF cannot be enabled, rewired or stripped of its reason", async () => {
  const html = await readFile(join(root, "src", "popup.html"), "utf8");
  const button = '<button id="scanPDF" type="button" disabled aria-disabled="true" aria-describedby="scanPDFUnavailable">Scan PDF</button>';
  const reason = '<p id="scanPDFUnavailable">Scan PDF is unavailable until a verified native scanner is connected.</p>';
  assert.doesNotThrow(() => validatePopupAsset("popup.html", html));
  for (const mutation of [
    html.replace(" disabled aria-disabled", " aria-disabled"),
    html.replace('aria-disabled="true"', 'aria-disabled="false"'),
    html.replace('type="button" disabled', 'type="submit" disabled'),
    html.replace('aria-describedby="scanPDFUnavailable"', 'aria-describedby="missing"'),
    html.replace(button, ""),
    html.replace(reason, ""),
    html.replace("verified native scanner", "browser scanner"),
    html.replace(button, button + button),
    html.replace("</section>", '<button id="unsafeScan">Scan now</button></section>'),
    html.replace("</section>", '<script>openPdf()</script></section>'),
    html.replace("</section>", '<select><option>Open</option></select></section>'),
    html.replace("</section>", '<div contenteditable="true">Open</div></section>')
  ]) assert.throws(() => validatePopupAsset("popup.html", mutation), /Unsafe WebExtensions popup asset/);
});
