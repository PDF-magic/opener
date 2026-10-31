// Real, simultaneous PDF-tab verification (opener-0808).
// Fresh Chrome for Testing profile, loopback fixtures only, no native scans.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const binary = process.argv[2] || process.env.CHROME_PATH;
assert.ok(binary, "Usage: node scripts/test-chrome-concurrent-pdf-tabs.mjs CHROME_BINARY");
const version = execFileSync(binary, ["--version"], {
  encoding: "utf8", timeout: 5000
}).trim();
assert.match(version, /Chrome|Chromium/, "A real Chrome for Testing browser is required");

function pdfFor(name) {
  const drawing = "BT /F1 18 Tf 50 730 Td (Concurrent PDF tab " + name + ") Tj ET\n";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    "<< /Length " + Buffer.byteLength(drawing, "ascii") + " >>\nstream\n" + drawing + "endstream",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
  ];
  let source = "%PDF-1.4\n";
  const offsets = [0];
  for (const [i, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(source, "ascii"));
    source += (i + 1) + " 0 obj\n" + object + "\nendobj\n";
  }
  const xref = Buffer.byteLength(source, "ascii");
  source += "xref\n0 " + (objects.length + 1) + "\n0000000000 65535 f \n";
  source += offsets.slice(1).map(value =>
    String(value).padStart(10, "0") + " 00000 n \n").join("");
  source += "trailer\n<< /Size " + (objects.length + 1) +
    " /Root 1 0 R >>\nstartxref\n" + xref + "\n%%EOF\n";
  const buffer = Buffer.from(source, "ascii");
  assert.equal(buffer.subarray(xref, xref + 5).toString("ascii"), "xref\n");
  assert.doesNotMatch(source, /https?:\/\/|\/URI\b|\/JavaScript\b|\/Launch\b/);
  return buffer;
}

const routes = ["/tab-one.pdf", "/tab-two.pdf", "/tab-three.pdf"];
const fixtures = new Map(routes.map((path, i) => [path, pdfFor(String(i + 1))]));
assert.equal(new Set([...fixtures.values()].map(value => value.toString("hex"))).size, 3);
const received = new Map(routes.map(path => [path, 0]));
const held = new Map();
let released = false;
const server = createServer((request, response) => {
  // Request exactly the expected three local fixture URLs. Never proxy.
  if (request.method !== "GET" || !fixtures.has(request.url)) {
    response.writeHead(404, { "Cache-Control": "no-store" });
    response.end();
    return;
  }
  const url = request.url;
  received.set(url, received.get(url) + 1);
  response.writeHead(200, {
    "Content-Type": "application/pdf", "Content-Disposition": "inline",
    "Content-Length": fixtures.get(url).length, "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  response.flushHeaders();
  if (released) response.end(fixtures.get(url));
  else held.set(url, response);
});

const profile = await mkdtemp(join(tmpdir(), "pdfmagic-concurrent-tabs-"));
let browser, socket, listening = false, stderrTail = "";
let nextId = 0;
const pending = new Map();
const targets = [];

function command(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const deadline = setTimeout(() => {
      pending.delete(id);
      reject(new Error("Chrome DevTools timeout: " + method));
    }, 16000);
    pending.set(id, { resolve, reject, deadline });
    try {
      socket.send(JSON.stringify({
        id, method, params, ...(sessionId ? { sessionId } : {})
      }));
    } catch (error) {
      clearTimeout(deadline);
      pending.delete(id);
      reject(error);
    }
  });
}

async function until(check, description, timeout = 30000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) {
      last = error;
    }
    await delay(200);
  }
  throw new Error("Concurrent PDF browser check timed out: " + description +
    (last ? " (" + last.message + ")" : ""));
}

const viewerUrl = /^chrome-extension:\/\/mhjfbmdgcfjbbpaeojofohoefgiehjai\/index\.html(?:[?#]|$)/;
function viewerFrame(tree) {
  return tree && (viewerUrl.test(tree.frame?.url || "") ||
    (tree.childFrames || []).some(viewerFrame));
}
function viewerEmbed(node) {
  if (!node) return false;
  const attrs = node.attributes || [];
  const index = attrs.findIndex(x => x === "type");
  if (node.nodeName === "EMBED" && index >= 0 &&
      ["application/pdf", "application/x-google-chrome-pdf"].includes(attrs[index + 1])) {
    return true;
  }
  return ["children", "shadowRoots", "contentDocument", "templateContent",
    "importedDocument"].some(key => {
    const value = node[key];
    return Array.isArray(value) ? value.some(viewerEmbed) : viewerEmbed(value);
  });
}

async function inspect(tab) {
  const { frameTree } = await command("Page.getFrameTree", {}, tab.sessionId);
  const { root } = await command("DOM.getDocument", {
    depth: -1, pierce: true
  }, tab.sessionId);
  const evaluated = await command("Runtime.evaluate", {
    expression: "({ mime: document.contentType })", returnByValue: true
  }, tab.sessionId);
  return {
    url: frameTree.frame?.url,
    mime: evaluated.result?.value?.mime || null,
    // Chrome may publish its PDF viewer as an out-of-process iframe target
    // rather than a child in Page.getFrameTree or DOM.getDocument.
    localViewerFrame: viewerFrame(frameTree) || viewerEmbed(root)
  };
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
  const origin = "http://127.0.0.1:" + server.address().port;
  const args = [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-default-apps", "--disable-sync",
    "--no-proxy-server", "--proxy-bypass-list=<-loopback>",
    "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank"
  ];
  if (process.env.CHROME_TEST_NO_SANDBOX === "1") args.unshift("--no-sandbox");
  browser = spawn(binary, args, { stdio: ["ignore", "ignore", "pipe"] });
  browser.stderr.on("data", bytes => {
    stderrTail = (stderrTail + bytes.toString("utf8")).slice(-1500);
  });
  const endpoint = await until(async () => {
    if (browser.exitCode !== null || browser.signalCode !== null) {
      throw new Error("The isolated Chrome process exited before DevTools started");
    }
    const lines = (await readFile(join(profile, "DevToolsActivePort"), "utf8"))
      .trim().split("\n");
    if (!/^\d+$/.test(lines[0]) ||
        !lines[1]?.startsWith("/devtools/browser/")) return null;
    return "ws://127.0.0.1:" + lines[0] + lines[1];
  }, "disposable DevTools endpoint");

  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    const deadline = setTimeout(() =>
      reject(new Error("DevTools connection timed out")), 8000);
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

  // Create three distinct *live* targets before requesting any PDF bytes.
  for (const route of routes) {
    const { targetId } = await command("Target.createTarget", { url: "about:blank" });
    targets.push(targetId);
    const { sessionId } = await command("Target.attachToTarget", {
      targetId, flatten: true
    });
    await command("Page.enable", {}, sessionId);
    await command("DOM.enable", {}, sessionId);
    targets[targets.length - 1] = { targetId, sessionId, url: origin + route, route };
  }
  assert.equal(new Set(targets.map(tab => tab.targetId)).size, 3);
  assert.equal(new Set(targets.map(tab => tab.sessionId)).size, 3);

  // Start navigation for every tab without waiting for any one PDF to load.
  // All three HTTP requests MUST arrive while all response bodies remain held.
  const navigations = targets.map(tab =>
    command("Page.navigate", { url: tab.url }, tab.sessionId));
  await until(() => routes.every(route => held.has(route)),
    "three overlapping PDF requests before any body release");
  assert.deepEqual(routes.map(route => received.get(route)), [1, 1, 1]);
  assert.equal(released, false);
  released = true;
  for (const route of routes) held.get(route).end(fixtures.get(route));
  const navigationResults = await Promise.all(navigations);
  for (const navigation of navigationResults) {
    assert.equal(navigation.errorText, undefined, "Parallel PDF navigation failed");
  }

  // Each PDF tab has to own its own viewer, not just share another tab's
  // browser-wide internal extension target or HTTP success response.
  const observations = [];
  // In headless Chrome, out-of-process PDF viewers appear as independent
  // iframe targets, not necessarily under the parent's DOM/frame tree.
  // Foreground each still-open PDF tab and confirm *its own* document MIME.
  for (const tab of targets) {
    await command("Target.activateTarget", { targetId: tab.targetId });
    await command("Page.bringToFront", {}, tab.sessionId);
    const observed = await until(async () => {
      const evidence = await inspect(tab);
      return evidence.url === tab.url && evidence.mime === "application/pdf" ?
        evidence : null;
    }, "distinct PDF document in tab " + tab.route);
    observations.push(observed);
  }
  for (const [index, result] of observations.entries()) {
    assert.equal(result.url, targets[index].url);
    assert.equal(result.mime, "application/pdf",
      "Each independent tab must retain its own PDF document");
    assert.ok(received.get(targets[index].route) > 0);
  }
  // The disposable browser contains exactly these three user PDF targets.
  // Chrome publishes its renderer as a separate OOPIF with no openerId,
  // so verify three *distinct* PDF viewer iframe targets alongside the three
  // tab-local PDF documents rather than attributing one global viewer to all.
  const { targetInfos: liveTargets } = await command("Target.getTargets");
  const viewerTargets = liveTargets.filter(info =>
    info.type === "iframe" && viewerUrl.test(info.url || ""));
  assert.ok(viewerTargets.length >= 3,
    "Three PDF documents must have three independent built-in viewer targets");
  assert.equal(new Set(viewerTargets.map(info => info.targetId)).size,
    viewerTargets.length, "The same viewer cannot count twice");

  // Closing one PDF tab must not tear down or cross-navigate the other two.
  const closed = targets.splice(1, 1)[0];
  const close = await command("Target.closeTarget", { targetId: closed.targetId });
  assert.equal(close.success, true);
  await until(async () => {
    const { targetInfos } = await command("Target.getTargets");
    return !targetInfos.some(info => info.targetId === closed.targetId);
  }, "the independently closed PDF tab");
  for (const tab of targets) {
    await command("Target.activateTarget", { targetId: tab.targetId });
    await command("Page.bringToFront", {}, tab.sessionId);
    const result = await until(async () => {
      const view = await inspect(tab);
      return view.url === tab.url && view.mime === "application/pdf" ?
        view : null;
    }, "remaining PDF document after independent tab closure");
    assert.equal(result.url, tab.url);
    assert.equal(result.mime, "application/pdf");
  }

  console.log("PASS Chrome three simultaneous PDF tabs, independent viewers and closure isolation: " +
    version);
} catch (error) {
  // Only diagnostics from a disposable browser; no private PDF contents.
  console.error("Chrome concurrent PDF tab diagnostic:", stderrTail);
  throw error;
} finally {
  released = true;
  for (const [route, response] of held) {
    if (!response.writableEnded) {
      try { response.end(fixtures.get(route)); } catch { /* teardown */ }
    }
  }
  try { socket?.close(); } catch { /* browser may have terminated */ }
  for (const { deadline } of pending.values()) clearTimeout(deadline);
  pending.clear();
  if (browser && browser.exitCode === null) browser.kill("SIGTERM");
  await delay(300);
  if (browser && browser.exitCode === null) browser.kill("SIGKILL");
  if (listening) await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
