import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import { dynamicPdfGeneratorPage } from "../scripts/dynamic-pdf-webpage-fixture.mjs";

const read = path => readFile(new URL(path, import.meta.url), "utf8");

test("the webpage itself creates valid and bounded PDF bytes from JavaScript", () => {
  const html = dynamicPdfGeneratorPage;
  assert.match(html, /^<!doctype html>/);
  assert.ok(Buffer.byteLength(html) < 5000);
  assert.ok(!/fetch\(|XMLHttpRequest|https:\/\/|file:\/\/|sendNativeMessage|connectNative|<iframe|<embed/i.test(html));
  const script = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(script, "the generated webpage must contain its own PDF generator");
  const callbacks = new Map();
  const controls = {
    generate: { addEventListener: (_, fn) => callbacks.set("generate", fn) },
    open: { disabled: true, addEventListener: (_, fn) => callbacks.set("open", fn) }
  };
  let opened = null;
  let createdBlob = null;
  const window = { generatedPdf: null, location: { assign(url) { opened = url; } } };
  vm.runInNewContext(script[1], {
    window, Blob, TextEncoder,
    document: { getElementById(id) { return controls[id]; } },
    URL: { createObjectURL(blob) {
      createdBlob = blob;
      return "blob:http://127.0.0.1:8443/test-id";
    } }
  }, { timeout: 1000 });
  assert.equal(window.generatedPdf, null);
  assert.equal(controls.open.disabled, true);
  assert.ok(callbacks.has("generate") && callbacks.has("open"));
  callbacks.get("generate")();
  assert.equal(window.generatedPdf.blob, createdBlob);
  assert.equal(createdBlob.type, "application/pdf");
  assert.equal(controls.open.disabled, false);
  const pdf = Buffer.from(window.generatedPdf.bytes).toString("ascii");
  assert.ok(pdf.startsWith("%PDF-1.4\n"));
  assert.ok(pdf.endsWith("%%EOF\n"));
  assert.match(pdf, /Webpage generated PDF/);
  assert.doesNotMatch(pdf, /\/(JavaScript|JS|OpenAction|AA|EmbeddedFile|Launch)\b/);
  assert.ok(pdf.length > 200 && pdf.length < 4096);
  const offset = Number(pdf.match(/startxref\n(\d+)\n%%EOF/)[1]);
  assert.equal(pdf.slice(offset, offset + 9), "xref\n0 6\n");
  callbacks.get("open")();
  assert.equal(opened, "blob:http://127.0.0.1:8443/test-id");
});

test("real Brave browser CI checks both inline and webpage-generated PDF viewers", async () => {
  const [smoke, workflow, background, manifest, doc] = await Promise.all([
    read("../scripts/smoke-brave-pdf-viewer.mjs"),
    read("../../../.github/workflows/brave-webextension.yml"),
    read("../src/background.js"),
    read("../manifest.json").then(JSON.parse),
    read("../webpage-generated-pdf.md")
  ]);
  for (const token of [
    "dynamicPdfGeneratorPage", '"/generated"', "dynamicPage.goto(",
    "generated.url.startsWith", "dynamicPage.frames()", "dynamicViewerFrame",
    "application/pdf", "dynamicDownloads", "dynamicPage.close()",
    "context?.close()", "rm(profile"
  ]) assert.ok(smoke.includes(token), token);
  assert.match(workflow, /xvfb-run -a node scripts\/smoke-brave-pdf-viewer\.mjs/);
  assert.match(background, /void 0;/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  for (const phrase of ["opener-0807", "webpage", "Blob",
    "JavaScript", "scanner", "user preferences", "Brave", "not"]) {
    assert.ok(doc.toLowerCase().includes(phrase.toLowerCase()), phrase);
  }
});
