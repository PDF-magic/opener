import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { createServer as createSocketServer } from "node:net";
import { mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

// Valid single-page PDF generated locally; no user documents or external URLs.
function createPdfFixture() {
  const drawing = "BT /F1 16 Tf 36 110 Td (Edge built-in PDF viewer test) Tj ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 240 180] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Length " + Buffer.byteLength(drawing, "ascii") +
      " >>\nstream\n" + drawing + "\nendstream"
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  for (let i = 0; i < objects.length; i++) {
    offsets.push(Buffer.byteLength(pdf, "ascii"));
    pdf += (i + 1) + " 0 obj\n" + objects[i] + "\nendobj\n";
  }
  const startxref = Buffer.byteLength(pdf, "ascii");
  pdf += "xref\n0 " + offsets.length + "\n0000000000 65535 f \n";
  for (const offset of offsets.slice(1)) {
    pdf += String(offset).padStart(10, "0") + " 00000 n \n";
  }
  pdf += "trailer\n<< /Size " + offsets.length +
    " /Root 1 0 R >>\nstartxref\n" + startxref + "\n%%EOF\n";
  return Buffer.from(pdf, "ascii");
}

test("local Edge viewer fixture has valid PDF structure and no external resources", () => {
  const pdf = createPdfFixture();
  const text = pdf.toString("ascii");
  assert.match(text, /^%PDF-1\.4\n/);
  assert.match(text, /\/Type \/Catalog/);
  assert.match(text, /\/Type \/Page /);
  assert.match(text, /Edge built-in PDF viewer test/);
  const pointer = Number(text.match(/startxref\n(\d+)\n%%EOF\n$/)?.[1]);
  assert.equal(text.slice(pointer, pointer + 5), "xref\n");
  const offsets = [...text.matchAll(/^(\d{10}) 00000 n $/gm)];
  assert.equal(offsets.length, 5);
  for (let i = 0; i < offsets.length; i++) {
    assert.ok(text.startsWith((i + 1) + " 0 obj\n", Number(offsets[i][1])));
  }
  assert.doesNotMatch(text, /https?:\/\/|\/URI\b|\/JavaScript\b|\/Launch\b/);
});

async function availablePort() {
  const socket = createSocketServer();
  await new Promise((done, fail) => {
    socket.once("error", fail);
    socket.listen(0, "127.0.0.1", done);
  });
  const port = socket.address().port;
  await new Promise(done => socket.close(done));
  return port;
}

test("real Edge opens inline PDF through its built-in viewer, not as a downloaded or HTML document", {
  skip: !process.env.EDGE_WEBDRIVER_BINARY,
  timeout: 120000
}, async () => {
  const executable = resolve(process.env.EDGE_WEBDRIVER_BINARY);
  assert.equal((await stat(executable)).isFile(), true);
  const fixture = createPdfFixture();
  const profile = await mkdtemp(join(tmpdir(), "pdf-magic-edge-viewer-"));
  const server = createServer((request, response) => {
    const pathname = request.url;
    if (request.method !== "GET" || !["/control.html", "/fixture.pdf"].includes(pathname)) {
      response.writeHead(404, { "Content-Type": "text/plain" });
      response.end("Not found");
      return;
    }
    const pdf = pathname === "/fixture.pdf";
    const content = pdf ? fixture : Buffer.from("<!doctype html><title>Edge control</title><p>HTML control</p>");
    response.writeHead(200, {
      "Content-Type": pdf ? "application/pdf" : "text/html; charset=utf-8",
      ...(pdf ? { "Content-Disposition": "inline" } : {}),
      "Content-Length": content.length,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    });
    response.end(content);
    if (pdf) servedPdf++;
  });
  let servedPdf = 0, driver = null, sessionId = null, port = 0;
  let origin;
  try {
    await new Promise((done, fail) => {
      server.once("error", fail);
      server.listen(0, "127.0.0.1", done);
    });
    origin = "http://127.0.0.1:" + server.address().port;
    port = await availablePort();
    const baseUrl = "http://127.0.0.1:" + port;
    driver = spawn(executable, ["--port=" + port, "--allowed-ips=127.0.0.1"], {
      stdio: "ignore", windowsHide: true
    });
    async function command(method, path, payload) {
      const response = await fetch(baseUrl + path, {
        method, headers: { "content-type": "application/json" },
        body: payload === undefined ? undefined : JSON.stringify(payload),
        signal: AbortSignal.timeout(15000)
      });
      const result = await response.json();
      if (!response.ok || result.value?.error) {
        throw new Error("Microsoft Edge viewer WebDriver command failed: " +
          (result.value?.error || response.status));
      }
      return result.value;
    }
    let ready = false;
    for (let i = 0; i < 80; i++) {
      if (driver.exitCode !== null) break;
      try {
        ready = (await command("GET", "/status")).ready === true;
        if (ready) break;
      } catch { /* local driver startup only */ }
      await delay(125);
    }
    assert.equal(ready, true, "EdgeDriver must start on loopback");
    const session = await command("POST", "/session", {
      capabilities: {
        alwaysMatch: {
          browserName: "MicrosoftEdge", pageLoadStrategy: "eager",
          "ms:edgeOptions": {
            args: [
              "--headless=new", "--disable-gpu", "--no-first-run",
              "--no-default-browser-check", "--disable-background-networking",
              "--disable-sync", "--user-data-dir=" + profile
            ]
          }
        }
      }
    });
    sessionId = session.sessionId;
    assert.match(session.capabilities.browserName, /MicrosoftEdge/i);
    assert.match(session.capabilities.browserVersion, /^\d+\./);

    const navigate = url => command("POST", "/session/" + sessionId + "/url", { url });
    const inspect = () => command("POST", "/session/" + sessionId + "/execute/sync", {
      script: [
        "const candidate = document.querySelector('embed[type=\"application/pdf\"], object[type=\"application/pdf\"]');",
        "const bounds = candidate?.getBoundingClientRect();",
        "return { url: location.href, mime: document.contentType,",
        "  viewerElement: Boolean(candidate),",
        "  viewerWidth: bounds?.width || 0, viewerHeight: bounds?.height || 0,",
        "  htmlControl: document.body?.textContent?.includes('HTML control') === true };"
      ].join("\n"), args: []
    });
    await navigate(origin + "/control.html");
    const control = await inspect();
    assert.equal(control.url, origin + "/control.html");
    assert.equal(control.mime, "text/html");
    assert.equal(control.htmlControl, true);
    assert.equal(control.viewerElement, false);

    // This intentionally exercises the fresh-profile *browser viewer* directly,
    // not the separately gated native scan-before-open application handoff.
    // Never set Edge PDF preferences, download behavior or user defaults.
    await navigate(origin + "/fixture.pdf");
    let observed;
    for (let i = 0; i < 60; i++) {
      observed = await inspect();
      if (observed.mime === "application/pdf" && observed.viewerElement &&
          observed.viewerWidth > 0 && observed.viewerHeight > 0) break;
      await delay(200);
    }
    assert.ok(servedPdf > 0, "Edge must request the loopback PDF fixture");
    assert.equal(observed.url, origin + "/fixture.pdf");
    assert.equal(observed.mime, "application/pdf",
      "Edge must navigate to PDF content instead of downloading it or displaying HTML");
    assert.equal(observed.viewerElement, true,
      "Edge must instantiate its built-in PDF viewer element");
    assert.ok(observed.viewerWidth > 0 && observed.viewerHeight > 0,
      "Edge PDF viewer must have visible document geometry");
    assert.equal(observed.htmlControl, false);
  } finally {
    if (sessionId && port) {
      try {
        await fetch("http://127.0.0.1:" + port + "/session/" + sessionId, {
          method: "DELETE", signal: AbortSignal.timeout(8000)
        });
      } catch { /* only disposable test browser */ }
    }
    try { driver?.kill(); } catch { /* already stopped */ }
    await new Promise(done => server.close(done));
    await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }
});

test("Edge PDF viewer smoke test requires the existing isolated Windows CI runner", async () => {
  const workflow = await import("node:fs/promises").then(fs =>
    fs.readFile(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8"));
  assert.match(workflow, /name: Microsoft Edge compatibility \(Windows\)/);
  assert.match(workflow, /runs-on: windows-2022/);
  assert.match(workflow, /EDGE_WEBDRIVER_BINARY/);
  assert.match(workflow, /node --test tests\/edge-pdf-viewer\.test\.mjs/);
  const [manifest, background] = await Promise.all([
    import("node:fs/promises").then(fs => fs.readFile(new URL("../manifest.json", import.meta.url), "utf8").then(JSON.parse)),
    import("node:fs/promises").then(fs => fs.readFile(new URL("../src/background.js", import.meta.url), "utf8"))
  ]);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.equal(manifest.web_accessible_resources, undefined);
  assert.ok(background.trimEnd().endsWith("void 0;"));
});
