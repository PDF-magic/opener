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
import { createAuthenticatedPdfRoutes } from "./authenticated-pdf-routes.mjs";
import {
  LARGE_REMOTE_PDF_MIN_BYTES, createLargeRemotePdf,
  createLargeRemotePdfRoute
} from "./large-remote-pdf-fixture.mjs";

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
const auth = createAuthenticatedPdfRoutes(pdf);
const large = createLargeRemotePdfRoute(createLargeRemotePdf());
const routes = ["/built-in-viewer.pdf", "/mime-only", "/framed-a.pdf", "/framed-b.pdf"];
const embeddedOnly = process.argv.includes("--embedded-only");
const htmlRoutes = new Map([
  ["/embedded-frames.html", [
    "<!doctype html><title>Local PDF frame verification</title>",
    '<iframe id="pdf-a" src="/framed-a.pdf" width="480" height="360"></iframe>',
    '<iframe id="pdf-b" src="/framed-b.pdf" width="480" height="360"></iframe>',
    '<iframe id="ordinary-frame" src="/ordinary-frame.html"></iframe>'
  ].join("")],
  ["/ordinary-frame.html", "<!doctype html><title>Not a PDF</title><p>HTML control frame</p>"]
]);
const counts = new Map([...routes, ...htmlRoutes.keys()].map(path => [path, 0]));
const server = createServer((request, response) => {
  if (auth.handle(request, response)) return;
  if (large.handle(request, response)) return;
  // No upstream requests and no outgoing network. Unknown paths fail closed.
  if (request.method !== "GET" || !counts.has(request.url)) {
    response.writeHead(404, { "Cache-Control": "no-store" });
    response.end();
    return;
  }
  counts.set(request.url, counts.get(request.url) + 1);
  if (htmlRoutes.has(request.url)) {
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    });
    response.end(htmlRoutes.get(request.url));
    return;
  }
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

  for (const route of (embeddedOnly ? [] : routes.slice(0, 2))) {
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

  if (!embeddedOnly) {
    // A login preference or a PDF URL must never bypass endpoint authentication.
    // Exercise the actual browser session: 401 before sign-in, HttpOnly cookie
    // acquired through ordinary navigation, then a real rendered PDF viewer.
    const authPdf = "http://127.0.0.1:" + port + auth.pdfRoute;
    const authLogin = "http://127.0.0.1:" + port + auth.loginRoute;
    const { targetId: authTargetId } = await command("Target.createTarget", {
      url: "about:blank"
    });
    try {
      const { sessionId: authSessionId } = await command("Target.attachToTarget", {
        targetId: authTargetId, flatten: true
      });
      await command("Page.enable", {}, authSessionId);
      await command("Page.navigate", { url: authPdf }, authSessionId);
      await until(async () => {
        const { result, exceptionDetails } = await command("Runtime.evaluate", {
          expression: 'document.readyState === "complete" && ' +
            'document.body?.textContent?.includes("Authentication required")',
          returnByValue: true
        }, authSessionId);
        return !exceptionDetails && result?.value === true;
      }, "401 response before browser authentication");
      assert.equal(auth.snapshot().denied, 1);
      assert.equal(auth.snapshot().granted, 0,
        "An unauthenticated PDF must never be served to Chrome");

      await command("Page.navigate", { url: authLogin }, authSessionId);
      await until(async () => {
        const { result, exceptionDetails } = await command("Runtime.evaluate", {
          expression: 'document.readyState === "complete" && ' +
            'document.body?.textContent?.includes("Signed in") && document.cookie === ""',
          returnByValue: true
        }, authSessionId);
        return !exceptionDetails && result?.value === true;
      }, "browser-managed HttpOnly authentication cookie");
      assert.equal(auth.snapshot().signedIn, 1);

      await command("Page.navigate", { url: authPdf }, authSessionId);
      await until(async () => {
        const { frameTree } = await command("Page.getFrameTree", {}, authSessionId);
        if (frameTree.frame?.url !== authPdf) return null;
        const { root } = await command("DOM.getDocument", {
          depth: -1, pierce: true
        }, authSessionId);
        const { targetInfos } = await command("Target.getTargets");
        return hasViewerFrame(frameTree) ||
          targetInfos.some(info => builtinViewer.test(info.url || "")) ||
          hasViewerEmbed(root);
      }, "rendered authenticated PDF in Chrome's built-in viewer");
      assert.ok(auth.snapshot().granted > 0,
        "The protected PDF must be fetched with the browser session cookie");
    } finally {
      await command("Target.closeTarget", { targetId: authTargetId });
    }
    // Exercise a large PDF over real HTTP rather than a small in-memory page
    // or a static URL classification. The loopback endpoint supports single
    // byte ranges; the browser decides whether to request the whole resource.
    const largeUrl = "http://127.0.0.1:" + port + large.path;
    const { targetId: largeTargetId } = await command("Target.createTarget", {
      url: "about:blank"
    });
    try {
      const { sessionId: largeSessionId } = await command("Target.attachToTarget", {
        targetId: largeTargetId, flatten: true
      });
      await command("Page.enable", {}, largeSessionId);
      const navigation = await command("Page.navigate", { url: largeUrl }, largeSessionId);
      assert.equal(navigation.errorText, undefined);
      await until(async () => {
        const { frameTree } = await command("Page.getFrameTree", {}, largeSessionId);
        if (frameTree.frame?.url !== largeUrl) return null;
        const { root } = await command("DOM.getDocument", {
          depth: -1, pierce: true
        }, largeSessionId);
        const { targetInfos } = await command("Target.getTargets");
        return hasViewerFrame(frameTree) ||
          targetInfos.some(info => builtinViewer.test(info.url || "")) ||
          hasViewerEmbed(root);
      }, "built-in viewer for the large remote PDF", 60_000);
      assert.ok(large.size > LARGE_REMOTE_PDF_MIN_BYTES);
      assert.ok(large.snapshot().requests > 0,
        "Chrome must request the large remote PDF via real HTTP");
    } finally {
      await command("Target.closeTarget", { targetId: largeTargetId });
    }

  }

  if (embeddedOnly) {
    const pageUrl = "http://127.0.0.1:" + port + "/embedded-frames.html";
    const pdfUrls = ["/framed-a.pdf", "/framed-b.pdf"].map(
      path => "http://127.0.0.1:" + port + path
    );
    const { targetId } = await command("Target.createTarget", { url: "about:blank" });
    try {
      const { sessionId } = await command("Target.attachToTarget", {
        targetId, flatten: true
      });
      await command("Page.enable", {}, sessionId);
      const navigation = await command("Page.navigate", { url: pageUrl }, sessionId);
      assert.equal(navigation.errorText, undefined, "Embedded HTML navigation failed");

      // A 200 PDF response alone is not a viewer test. Require the top-level
      // page to remain HTML, two distinct real PDF child frames, and the
      // browser's own viewer/plugin surface rather than just the iframe tags.
      const state = await until(async () => {
        const { frameTree } = await command("Page.getFrameTree", {}, sessionId);
        if (frameTree.frame?.url !== pageUrl) return null;
        const frames = [];
        function collect(tree) {
          if (!tree) return;
          frames.push(tree.frame?.url);
          for (const child of tree.childFrames || []) collect(child);
        }
        collect(frameTree);
        if (!pdfUrls.every(url => frames.includes(url))) return null;
        if (!frames.includes("http://127.0.0.1:" + port + "/ordinary-frame.html")) {
          return null;
        }
        const { root } = await command("DOM.getDocument", {
          depth: -1, pierce: true
        }, sessionId);
        const { targetInfos } = await command("Target.getTargets");
        const hasBrowserViewer = hasViewerFrame(frameTree) ||
          hasViewerEmbed(root) ||
          targetInfos.some(info => builtinViewer.test(info.url || ""));
        if (!hasBrowserViewer) return null;
        if (!["/framed-a.pdf", "/framed-b.pdf", "/ordinary-frame.html",
          "/embedded-frames.html"].every(path => counts.get(path) > 0)) return null;
        return { frameTree, frames, hasBrowserViewer };
      }, "two independently fetched PDF iframes with a browser viewer");
      assert.equal(state.frameTree.frame.url, pageUrl,
        "Embedded PDFs must not replace the containing HTML page");
      assert.equal(state.frames.filter(url => pdfUrls.includes(url)).length, 2,
        "Both embedded PDF documents must have distinct child frames");
      assert.equal(state.hasBrowserViewer, true);
      assert.equal(counts.get("/mime-only"), 0,
        "Unrelated PDF documents must not be fetched in embedded-only mode");
      console.log("PASS two embedded PDF child frames and HTML control: " + version);
    } finally {
      await command("Target.closeTarget", { targetId });
    }
  }

  if (!embeddedOnly) console.log("PASS Chrome built-in PDF viewer opens local PDF, MIME-only, authenticated and large remote PDF: " + version);
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
