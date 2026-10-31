import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  MALFORMED_REMOTE_PDF_CASES, createMalformedRemotePdfRoutes
} from "../scripts/malformed-remote-pdf-routes.mjs";

const load = path => readFile(new URL(path, import.meta.url), "utf8");

test("malformed fixtures cannot accidentally represent renderable PDFs", () => {
  assert.equal(MALFORMED_REMOTE_PDF_CASES.length, 2);
  const [truncated, nonPdf] = MALFORMED_REMOTE_PDF_CASES;
  assert.equal(truncated.path, "/malformed/truncated.pdf");
  assert.equal(nonPdf.path, "/malformed/not-a-pdf.pdf");
  assert.match(truncated.body.toString("ascii"), /^%PDF-1\.4\n/);
  assert.ok(!truncated.body.includes(Buffer.from("startxref")));
  assert.ok(!truncated.body.includes(Buffer.from("%%EOF")));
  assert.ok(!truncated.body.includes(Buffer.from("/Type /Page ")));
  assert.ok(!nonPdf.body.subarray(0, 5).equals(Buffer.from("%PDF-")));
  assert.ok(nonPdf.body.length > 0);
});

test("malformed PDFs are served only from explicit local routes with correct MIME", async () => {
  const fixture = createMalformedRemotePdfRoutes();
  const server = createServer((request, response) => {
    if (!fixture.handle(request, response)) {
      response.writeHead(404, { "Cache-Control": "no-store" });
      response.end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const origin = "http://127.0.0.1:" + server.address().port;
  try {
    for (const item of MALFORMED_REMOTE_PDF_CASES) {
      const response = await fetch(origin + item.path);
      assert.equal(response.status, 200);
      assert.equal(response.headers.get("content-type"), "application/pdf");
      assert.equal(response.headers.get("content-disposition"), "inline");
      assert.equal(response.headers.get("content-length"), String(item.body.length));
      assert.equal(response.headers.get("x-content-type-options"), "nosniff");
      assert.equal(response.headers.get("cache-control"), "no-store");
      assert.deepEqual(Buffer.from(await response.arrayBuffer()), item.body);
    }
    assert.deepEqual(fixture.snapshot(), {
      "/malformed/truncated.pdf": 1,
      "/malformed/not-a-pdf.pdf": 1
    });
    assert.equal(Object.isFrozen(fixture.snapshot()), true);
    assert.equal((await fetch(origin + "/malformed/unknown.pdf")).status, 404);
    assert.equal((await fetch(origin + "/malformed/truncated.pdf",
      { method: "POST" })).status, 405);
    assert.equal((await fetch(origin + "/private.pdf")).status, 404);
    assert.deepEqual(fixture.snapshot(), {
      "/malformed/truncated.pdf": 1,
      "/malformed/not-a-pdf.pdf": 1
    });
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test("CI exercises real Firefox PDF.js failure, no pages, and recovery without scanner access", async () => {
  const [firefox, ci, manifest, background, pkg, fixtureSource] = await Promise.all([
    load("../scripts/test-firefox-pdf-viewer.mjs"),
    load("../../../.github/workflows/ci.yml"),
    load("../manifest.json").then(JSON.parse),
    load("../src/background.js"),
    load("../package.json").then(JSON.parse),
    load("../scripts/malformed-remote-pdf-routes.mjs")
  ]);
  for (const required of [
    "createMalformedRemotePdfRoutes", "malformed.handle(request, response)",
    "malformed.cases", "malformed.snapshot()[item.path]",
    "Firefox PDF.js reader for malformed remote PDF",
    "assert.equal(invalid.pages, null",
    "assert.equal(invalid.pageNodes, 0",
    "normal PDF recovers after malformed remote PDF", "viewerProbe"
  ]) assert.ok(firefox.includes(required), required);
  assert.match(ci, /name: Firefox built-in PDF viewer smoke test/);
  assert.match(ci, /node scripts\/test-firefox-pdf-viewer\.mjs/);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  for (const source of [firefox, fixtureSource]) {
    for (const forbidden of [
      "--load-extension=", "permissions.request(", "connectNative(",
      "sendNativeMessage(", "clamscan(", "https://"
    ]) assert.equal(source.includes(forbidden), false, forbidden);
  }
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
});
