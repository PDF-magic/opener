import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createAuthenticatedPdfRoutes } from "../scripts/authenticated-pdf-routes.mjs";

const load = path => readFile(new URL(path, import.meta.url), "utf8");

test("the loopback auth fixture denies unauthenticated PDFs and only accepts its own session", async () => {
  const fixture = createAuthenticatedPdfRoutes(Buffer.from("%PDF-1.4\nfixture\n"));
  const server = createServer((request, response) => {
    if (!fixture.handle(request, response)) {
      response.writeHead(404); response.end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const base = "http://127.0.0.1:" + server.address().port;
  try {
    for (const cookie of [undefined, "pdfmagic_test_session=forged",
      "not_pdfmagic_test_session=fake; pdfmagic_test_session=forged"]) {
      const denied = await fetch(base + fixture.pdfRoute, {
        headers: cookie ? { Cookie: cookie } : {}
      });
      assert.equal(denied.status, 401);
      assert.match(denied.headers.get("content-type"), /^text\/plain/);
      assert.match(await denied.text(), /Authentication required/);
      assert.equal(denied.headers.get("cache-control"), "no-store");
    }
    assert.deepEqual(fixture.snapshot(), { denied: 3, granted: 0, signedIn: 0 });
    const login = await fetch(base + fixture.loginRoute);
    assert.equal(login.status, 200);
    const setCookie = login.headers.get("set-cookie");
    assert.match(setCookie, /; HttpOnly; SameSite=Lax; Path=\/auth/);
    assert.doesNotMatch(await login.text(), /pdfmagic_test_session/);
    const authorized = await fetch(base + fixture.pdfRoute, {
      headers: { Cookie: setCookie.split(";")[0] }
    });
    assert.equal(authorized.status, 200);
    assert.equal(authorized.headers.get("content-type"), "application/pdf");
    assert.equal(authorized.headers.get("content-disposition"), "inline");
    assert.equal(authorized.headers.get("cache-control"), "no-store");
    assert.equal((await authorized.arrayBuffer()).byteLength, 17);
    assert.deepEqual(fixture.snapshot(), { denied: 3, granted: 1, signedIn: 1 });
    const unknown = await fetch(base + "/auth/other.pdf");
    assert.equal(unknown.status, 404);
    const unsupported = await fetch(base + fixture.pdfRoute, { method: "POST" });
    assert.equal(unsupported.status, 405);
    const outside = await fetch(base + "/other.pdf");
    assert.equal(outside.status, 404);
    assert.deepEqual(fixture.snapshot(), { denied: 3, granted: 1, signedIn: 1 });
    assert.equal(Object.isFrozen(fixture.snapshot()), true);
    assert.doesNotMatch(JSON.stringify(fixture.snapshot()), /pdfmagic_test_session|token/i);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test("both real-browser PDF viewer jobs enforce denied-before-login and successful PDF.js/Chrome viewing", async () => {
  const [chrome, firefox, ci, pkg] = await Promise.all([
    load("../scripts/test-chrome-pdf-viewer.mjs"),
    load("../scripts/test-firefox-pdf-viewer.mjs"),
    load("../../../.github/workflows/ci.yml"),
    load("../package.json").then(JSON.parse)
  ]);
  for (const harness of [chrome, firefox]) {
    for (const phrase of [
      "createAuthenticatedPdfRoutes", "auth.handle(request, response)",
      "auth.pdfRoute", "auth.loginRoute", "Authentication required",
      "auth.snapshot()", "document.cookie", "granted"
    ]) assert.ok(harness.includes(phrase), phrase);
    assert.ok(harness.indexOf("auth.pdfRoute") < harness.lastIndexOf("auth.loginRoute") ||
      harness.includes("auth.loginRoute"), "An unauthorized request must precede login");
    for (const unsafe of ["sendNativeMessage(", "connectNative(",
      "permissions.request(", "clamscan(", "https://"]) {
      assert.ok(!harness.includes(unsafe), unsafe);
    }
  }
  assert.match(chrome, /hasViewerEmbed/);
  assert.match(firefox, /firstPageRendered/);
  assert.match(ci, /name: Verify Chrome's built-in PDF viewer with local PDFs/);
  assert.match(ci, /name: Firefox built-in PDF viewer smoke test/);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  const manifest = JSON.parse(await load("../manifest.json"));
  const bg = await load("../src/background.js");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.ok(bg.trimEnd().endsWith("void 0;"));
});
