// Real Chrome built-in PDF viewer smoke test (opener-0800).
// Runs only against a disposable Chrome for Testing profile and loopback PDFs.
// No installed user profile, extension privilege, native scanner or PDF opener.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const binary = process.argv[2] || process.env.CHROME_PATH;
assert.ok(binary, "Usage: node scripts/test-chrome-pdf-viewer.mjs CHROME_FOR_TESTING_BINARY");
const version = execFileSync(binary, ["--version"], {
  encoding: "utf8", timeout: 5000
}).trim();
assert.match(version, /Chrome|Chromium/, "An actual Chrome binary is required");

// An independently generated, one-page, valid PDF with readable text. No
// external fixtures, arbitrary URL downloads or browser extension resources.
function makePdf() {
  const stream = "BT /F1 18 Tf 60 730 Td (PDF Magic Chrome Viewer Smoke Test) Tj ET\n";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
      "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    "<< /Length " + Buffer.byteLength(stream) + " >>\nstream\n" +
      stream + "endstream",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
  ];
  let body = "%PDF-1.4\n";
  const offsets = [0];
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(body));
    body += (index + 1) + " 0 obj\n" + object + "\nendobj\n";
  }
  const startXref = Buffer.byteLength(body);
  body += "xref\n0 " + (objects.length + 1) + "\n0000000000 65535 f \n" +
    offsets.slice(1).map(n => String(n).padStart(10, "0") + " 00000 n \n").join("") +
    "trailer\n<< /Size " + (objects.length + 1) +
    " /Root 1 0 R >>\nstartxref\n" + startXref + "\n%%EOF\n";
  return Buffer.from(body, "ascii");
}

const pdf = makePdf();
const routes = ["/built-in-viewer.pdf", "/mime-only"];
const counts = new Map(routes.map(path => [path, 0]));
const server = createServer((request, response) => {
  // No upstream requests and no outgoing network. Unknown paths fail closed.
  if (request.method !== "GET" || !counts.has(request.url)) {
    response.writeHead(404, { "Cache-Control": "no-store" });
    response.end();
    return;
  }
  counts.set(request.url, counts.get(request.url) + 1);
  response.writeHead(200, {
    "Content-Type": "application/pdf",
    "Content-Disposition": "inline",
    "Content-Length": pdf.length,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  response.end(pdf);
});
const profile = await mkdtemp(join(tmpdir(), "pdfmagic-chrome-viewer-"));
let browser;
let socket;
let stderrTail = "";
let nextId = 0;
const pending = new Map();
let listening = false;

function command(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const deadline = setTimeout(() => {
      pending.delete(id);
      reject(new Error("Chrome DevTools command timeout: " + method));
    }, 8000);
    pending.set(id, { resolve, reject, deadline });
    try {
      socket.send(JSON.stringify({ id, method, params,
        ...(sessionId ? { sessionId } : {}) }));
    } catch (error) {
      clearTimeout(deadline);
      pending.delete(id);
      reject(error);
    }
  });
}

async function until(check, label, timeout = 20000) {
  const stop = Date.now() + timeout;
  let last;
  while (Date.now() < stop) {
    try {
      const result = await check();
      if (result) return result;
    } catch (error) {
      last = error;
    }
    await delay(200);
  }
  throw new Error("Chrome PDF viewer was not observed: " + label +
    (last ? " (" + last.message + ")" : ""));
}

const builtinViewer = /^chrome-extension:\/\/mhjfbmdgcfjbbpaeojofohoefgiehjai\/index\.html(?:[?#]|$)/;
function hasViewerFrame(tree) {
  if (!tree) return false;
  return builtinViewer.test(tree.frame?.url || "") ||
    (tree.childFrames || []).some(hasViewerFrame);
}
function hasViewerEmbed(node) {
  if (!node) return false;
  const attributes = node.attributes || [];
  const typeIndex = attributes.findIndex(value => value === "type");
  if (node.nodeName === "EMBED" && typeIndex >= 0 &&
      ["application/pdf", "application/x-google-chrome-pdf"].includes(
        attributes[typeIndex + 1])) return true;
  return ["children", "shadowRoots", "contentDocument", "templateContent",
    "importedDocument"].some(key => {
    const children = node[key];
    return Array.isArray(children) ? children.some(hasViewerEmbed) :
      hasViewerEmbed(children);
  });
}

try {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.removeListener("error", reject);
      listening = true;
      resolve();
    });
  });
  const port = server.address().port;
  const args = [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-default-apps", "--disable-sync",
    "--no-proxy-server", "--proxy-bypass-list=<-loopback>",
    "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank"
  ];
  // Sandbox exception applies only to this disposable Linux CI test process.
  if (process.env.CHROME_TEST_NO_SANDBOX === "1") args.unshift("--no-sandbox");
  browser = spawn(binary, args, { stdio: ["ignore", "ignore", "pipe"] });
  browser.stderr.on("data", bytes => {
    stderrTail = (stderrTail + bytes.toString("utf8")).slice(-2000);
  });
  const endpoint = await until(async () => {
    if (browser.exitCode !== null || browser.signalCode !== null) {
      throw new Error("Chrome exited before DevTools startup");
    }
    const lines = (await readFile(join(profile, "DevToolsActivePort"), "utf8"))
      .trim().split("\n");
    if (!/^\d+$/.test(lines[0]) ||
        !lines[1]?.startsWith("/devtools/browser/")) return null;
    return "ws://127.0.0.1:" + lines[0] + lines[1];
  }, "disposable DevTools socket");

  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    const deadline = setTimeout(() => reject(new Error("DevTools connection timeout")), 8000);
    socket.onopen = () => { clearTimeout(deadline); resolve(); };
    socket.onerror = () => {
      clearTimeout(deadline);
      reject(new Error("Chrome DevTools connection failed"));
    };
  });
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    clearTimeout(waiter.deadline);
    if (message.error) waiter.reject(new Error("Chrome DevTools: " + message.error.message));
    else waiter.resolve(message.result);
  };
  await command("Target.setDiscoverTargets", { discover: true });

  for (const route of routes) {
    const url = "http://127.0.0.1:" + port + route;
    const { targetId } = await command("Target.createTarget", { url: "about:blank" });
    try {
      const { sessionId } = await command("Target.attachToTarget", {
        targetId, flatten: true
      });
      await command("Page.enable", {}, sessionId);
      const navigation = await command("Page.navigate", { url }, sessionId);
      assert.equal(navigation.errorText, undefined, "PDF navigation must not fail");

      const view = await until(async () => {
        const { frameTree } = await command("Page.getFrameTree", {}, sessionId);
        if (frameTree.frame?.url !== url) return null;
        const { root } = await command("DOM.getDocument", {
          depth: -1, pierce: true
        }, sessionId);
        const { targetInfos } = await command("Target.getTargets");
        const viewer = hasViewerFrame(frameTree) ||
          targetInfos.some(info => builtinViewer.test(info.url || "")) ||
          hasViewerEmbed(root);
        if (!viewer) return null;
        return { url: frameTree.frame.url, viewer };
      }, "Chrome's built-in viewer for " + route);
      assert.equal(view.url, url, "Chrome must retain the original PDF navigation");
      assert.equal(view.viewer, true, "A PDF response alone is not a viewer test");
      assert.ok(counts.get(route) > 0, "Chrome must actually fetch the local PDF");
    } finally {
      await command("Target.closeTarget", { targetId });
    }
  }

  console.log("PASS Chrome built-in PDF viewer opens local PDF and MIME-only PDF: " + version);
} catch (error) {
  // Only local disposable Chrome diagnostics; never log user file contents.
  console.error("Chrome local viewer diagnostic:", stderrTail);
  throw error;
} finally {
  try { socket?.close(); } catch { /* browser may have terminated */ }
  for (const { deadline } of pending.values()) clearTimeout(deadline);
  pending.clear();
  if (browser && browser.exitCode === null) browser.kill("SIGTERM");
  await delay(300);
  if (browser && browser.exitCode === null) browser.kill("SIGKILL");
  if (listening) await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
