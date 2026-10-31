import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  LARGE_REMOTE_PDF_MIN_BYTES, LARGE_REMOTE_PDF_PATH,
  createLargeRemotePdf, createLargeRemotePdfRoute
} from "../scripts/large-remote-pdf-fixture.mjs";

const load = path => readFile(new URL(path, import.meta.url), "utf8");

test("large remote PDF fixture is a deterministic, valid 16 MiB+ PDF stream", () => {
  const pdf = createLargeRemotePdf();
  assert.equal(LARGE_REMOTE_PDF_MIN_BYTES, 16 * 1024 * 1024);
  assert.ok(pdf.length > LARGE_REMOTE_PDF_MIN_BYTES);
  assert.ok(pdf.length < LARGE_REMOTE_PDF_MIN_BYTES + 4096);
  assert.equal(pdf.subarray(0, 9).toString("ascii"), "%PDF-1.4\n");
  assert.match(pdf.subarray(-64).toString("ascii"), /startxref\n\d+\n%%EOF\n$/);
  assert.deepEqual(createLargeRemotePdf(), pdf);
  assert.equal(LARGE_REMOTE_PDF_PATH, "/large/remote.pdf");
  assert.ok(pdf.includes(Buffer.from("Large Remote PDF Viewer Test", "ascii")));
  assert.ok(pdf.includes(Buffer.from("/Count 1", "ascii")));
});

test("HTTP fixture serves full and byte-range PDF responses with exact lengths", async () => {
  const pdf = createLargeRemotePdf();
  const fixture = createLargeRemotePdfRoute(pdf);
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
  const base = "http://127.0.0.1:" + server.address().port;
  const url = base + fixture.path;
  try {
    assert.equal(fixture.size, pdf.length);
    const head = await fetch(url, { method: "HEAD" });
    assert.equal(head.status, 200);
    assert.equal(head.headers.get("content-length"), String(pdf.length));
    assert.equal(head.headers.get("accept-ranges"), "bytes");
    assert.equal(head.headers.get("content-type"), "application/pdf");
    assert.equal((await head.arrayBuffer()).byteLength, 0);

    const first = await fetch(url, { headers: { Range: "bytes=0-1023" } });
    assert.equal(first.status, 206);
    assert.equal(first.headers.get("content-range"), "bytes 0-1023/" + pdf.length);
    assert.equal(first.headers.get("content-length"), "1024");
    assert.equal(first.headers.get("content-disposition"), "inline");
    assert.equal(first.headers.get("cache-control"), "no-store");
    assert.deepEqual(Buffer.from(await first.arrayBuffer()), pdf.subarray(0, 1024));

    const suffix = await fetch(url, { headers: { Range: "bytes=-2048" } });
    assert.equal(suffix.status, 206);
    assert.equal(suffix.headers.get("content-range"),
      "bytes " + (pdf.length - 2048) + "-" + (pdf.length - 1) + "/" + pdf.length);
    assert.deepEqual(Buffer.from(await suffix.arrayBuffer()), pdf.subarray(-2048));

    const last = await fetch(url, {
      headers: { Range: "bytes=" + (pdf.length - 128) + "-" }
    });
    assert.equal(last.status, 206);
    assert.deepEqual(Buffer.from(await last.arrayBuffer()), pdf.subarray(-128));

    const full = await fetch(url);
    assert.equal(full.status, 200);
    assert.equal(full.headers.get("content-length"), String(pdf.length));
    assert.equal(full.headers.get("content-type"), "application/pdf");
    assert.equal(full.headers.get("x-content-type-options"), "nosniff");
    assert.deepEqual(Buffer.from(await full.arrayBuffer()), pdf);

    for (const range of [
      "bytes=" + pdf.length + "-", "bytes=3-2", "bytes=0-1,4-5",
      "bytes=-0", "bytes=a-b", "bytes="
    ]) {
      const denied = await fetch(url, { headers: { Range: range } });
      assert.equal(denied.status, 416, range);
      assert.equal(denied.headers.get("content-range"), "bytes */" + pdf.length);
      assert.equal((await denied.arrayBuffer()).byteLength, 0);
    }
    assert.equal((await fetch(url, { method: "POST" })).status, 405);
    assert.equal((await fetch(base + "/other.pdf")).status, 404);
    assert.deepEqual(fixture.snapshot(),
      { requests: 5, fullRequests: 2, rangeRequests: 3, invalidRanges: 6 });
    assert.ok(Object.isFrozen(fixture.snapshot()));
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test("Chrome and Firefox CI must render the large remote PDF without changing scanner policy", async () => {
  const [chrome, firefox, ci, packageJson, background, manifest] = await Promise.all([
    load("../scripts/test-chrome-pdf-viewer.mjs"),
    load("../scripts/test-firefox-pdf-viewer.mjs"),
    load("../../../.github/workflows/ci.yml"),
    load("../package.json").then(JSON.parse),
    load("../src/background.js"),
    load("../manifest.json").then(JSON.parse)
  ]);
  for (const harness of [chrome, firefox]) {
    for (const required of [
      "createLargeRemotePdf", "createLargeRemotePdfRoute",
      "large.handle(request, response)", "large.path",
      "LARGE_REMOTE_PDF_MIN_BYTES", "large.snapshot().requests",
      "large remote PDF"
    ]) assert.ok(harness.includes(required), required);
    for (const forbidden of [
      "--load-extension=", "permissions.request(", "connectNative(",
      "sendNativeMessage(", "clamscan(", "https://"
    ]) assert.equal(harness.includes(forbidden), false, forbidden);
  }
  assert.match(chrome, /hasViewerEmbed/);
  assert.match(firefox, /viewerProbe/);
  assert.match(firefox, /firstPageRendered/);
  assert.match(ci, /name: Chrome package smoke test/);
  assert.match(ci, /name: Firefox built-in PDF viewer smoke test/);
  assert.match(ci, /node scripts\/test-chrome-pdf-viewer\.mjs/);
  assert.match(ci, /node scripts\/test-firefox-pdf-viewer\.mjs/);
  assert.match(packageJson.scripts.test, /tests\/\*\.test\.mjs/);
  assert.ok(background.trimEnd().endsWith("void 0;"));
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
});
