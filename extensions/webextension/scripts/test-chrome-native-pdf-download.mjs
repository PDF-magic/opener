// Real Chrome for Testing native PDF download-manager integration test.
// Uses generated loopback files and an entirely disposable browser profile.
// Does not install PDF Magic, grant permissions, open files or run a scanner.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, mkdir, readFile, readdir, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { createNativePdfDownloadFixture } from "./native-pdf-download-fixture.mjs";

const binary = process.argv[2] || process.env.CHROME_PATH;
assert.ok(binary, "Usage: node scripts/test-chrome-native-pdf-download.mjs CHROME_BINARY");
const version = execFileSync(binary, ["--version"], {
  encoding: "utf8", timeout: 5000
}).trim();
assert.match(version, /Chrome|Chromium/, "A real Chrome binary is required");

const fixture = createNativePdfDownloadFixture();
const server = createServer((request, response) => {
  if (fixture.handle(request, response)) return;
  response.writeHead(404, { "Cache-Control": "no-store" });
  response.end();
});
const profile = await mkdtemp(join(tmpdir(), "pdfmagic-chrome-native-download-"));
const downloadDir = join(profile, "downloads");
let browser;
let socket;
let stderrTail = "";
let listening = false;
let nextId = 0;
const pending = new Map();
const starts = [];
const progresses = [];

async function until(check, description, timeout = 30_000) {
  const stop = Date.now() + timeout;
  let latestError;
  while (Date.now() < stop) {
    try {
      const value = await check();
      if (value) return value;
    } catch (error) {
      latestError = error;
    }
    await delay(200);
  }
  throw new Error("Chrome native download smoke timed out: " + description +
    (latestError ? " (" + latestError.message + ")" : ""));
}
function command(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++nextId;
    const deadline = setTimeout(() => {
      pending.delete(id);
      reject(new Error("Chrome DevTools timeout: " + method));
    }, 10_000);
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

try {
  await mkdir(downloadDir);
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
    "--disable-extensions", "--no-proxy-server",
    "--proxy-bypass-list=<-loopback>", "--remote-debugging-port=0",
    "--user-data-dir=" + profile, "about:blank"
  ];
  // The exception is limited to a disposable CI test browser running as root.
  if (process.env.CHROME_TEST_NO_SANDBOX === "1") args.unshift("--no-sandbox");
  browser = spawn(binary, args, { stdio: ["ignore", "ignore", "pipe"] });
  browser.stderr.on("data", bytes => {
    stderrTail = (stderrTail + bytes.toString("utf8")).slice(-1600);
  });
  const endpoint = await until(async () => {
    if (browser.exitCode !== null || browser.signalCode !== null) {
      throw new Error("Chrome exited before DevTools was available");
    }
    const lines = (await readFile(join(profile, "DevToolsActivePort"), "utf8"))
      .trim().split("\n");
    if (!/^\d+$/.test(lines[0]) ||
        !lines[1]?.startsWith("/devtools/browser/")) return null;
    return "ws://127.0.0.1:" + lines[0] + lines[1];
  }, "disposable DevTools socket");

  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => {
    const deadline = setTimeout(() =>
      reject(new Error("Chrome DevTools connection timeout")), 8_000);
    socket.onopen = () => { clearTimeout(deadline); resolve(); };
    socket.onerror = () => {
      clearTimeout(deadline);
      reject(new Error("Chrome DevTools connection failed"));
    };
  });
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.method === "Browser.downloadWillBegin") {
      starts.push(message.params);
    } else if (message.method === "Browser.downloadProgress") {
      progresses.push(message.params);
    }
    const waiter = pending.get(message.id);
    if (!waiter) return;
    pending.delete(message.id);
    clearTimeout(waiter.deadline);
    if (message.error) waiter.reject(new Error("Chrome DevTools: " +
      message.error.message));
    else waiter.resolve(message.result);
  };

  // This is Chrome's own download manager, not downloads.download() from
  // an extension. Explicitly allow writes only under a temporary directory.
  await command("Browser.setDownloadBehavior", {
    behavior: "allow", downloadPath: downloadDir, eventsEnabled: true
  });
  const { targetId } = await command("Target.createTarget", { url: "about:blank" });
  try {
    const { sessionId } = await command("Target.attachToTarget", {
      targetId, flatten: true
    });
    await command("Page.enable", {}, sessionId);
    for (const item of fixture.cases) {
      const url = origin + item.path;
      // Chrome may report net::ERR_ABORTED for an intentional navigation
      // transfer to its native download manager. Only real download events
      // and correctly saved PDF bytes count as a success.
      try {
        const navigation = await command("Page.navigate", { url }, sessionId);
        assert.ok(!navigation.errorText ||
          navigation.errorText.includes("ERR_ABORTED"),
        "Unexpected PDF download navigation error");
      } catch (error) {
        if (!String(error.message).includes("ERR_ABORTED")) throw error;
      }
      const started = await until(() =>
        starts.find(event => event.url === url),
      "native downloadWillBegin for " + item.name);
      assert.equal(started.suggestedFilename, item.name);
      assert.ok(started.guid, "Chrome must assign a native download GUID");

      const finished = await until(() =>
        progresses.find(event => event.guid === started.guid &&
          event.state === "completed"),
      "native completed download for " + item.name, 45_000);
      assert.equal(finished.state, "completed");
      assert.ok(finished.totalBytes > 0);
      assert.equal(finished.receivedBytes, fixture.pdf.length);
      await until(async () => {
        const info = await stat(join(downloadDir, item.name));
        return info.size === fixture.pdf.length;
      }, "saved native PDF file " + item.name);
      assert.deepEqual(await readFile(join(downloadDir, item.name)), fixture.pdf,
        "Browser must save the exact PDF bytes, not an HTML/viewer shell");
      assert.ok(fixture.snapshot().requests[item.path] > 0,
        "Browser must retrieve the PDF over loopback HTTP");
      assert.equal(starts.filter(event => event.url === url).length, 1,
        "One navigation must create exactly one native download");
    }
    const expected = fixture.cases.map(item => item.name).sort();
    assert.deepEqual((await readdir(downloadDir)).sort(), expected,
      "Only the two requested downloads may appear");
    assert.equal(starts.length, fixture.cases.length,
      "No other browser download should be triggered");
  } finally {
    await command("Target.closeTarget", { targetId });
  }
  console.log("PASS Chrome browser-native PDF attachment and octet downloads: " + version);
} catch (error) {
  console.error("Chrome isolated download diagnostics:", stderrTail);
  throw error;
} finally {
  try { socket?.close(); } catch { /* Browser may have exited. */ }
  for (const item of pending.values()) clearTimeout(item.deadline);
  pending.clear();
  if (browser && browser.exitCode === null) browser.kill("SIGTERM");
  await delay(300);
  if (browser && browser.exitCode === null) browser.kill("SIGKILL");
  if (listening) await new Promise(resolve => server.close(resolve));
  await rm(profile, { recursive: true, force: true });
}
