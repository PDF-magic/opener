// Real Vivaldi Stable WebExtensions smoke test (opener-0602).
// Launch the installed browser with its native CDP pipe. No Playwright,
// downloaded browser substitute, user profile, public page, PDF or scanner.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const extensionPath = resolve(root, "dist");
const executablePath = process.env.VIVALDI_BROWSER_PATH || "/usr/bin/vivaldi-stable";
const profile = await mkdtemp(join(tmpdir(), "pdf-magic-vivaldi-"));
const pause = (ms) => new Promise((done) => setTimeout(done, ms));
let browser;
let browserLog = "";
const pending = new Map();
let sequence = 0;

function send(method, params = {}, sessionId, timeout = 25000) {
  return new Promise((resolveCommand, rejectCommand) => {
    const id = ++sequence;
    const timer = setTimeout(() => {
      pending.delete(id);
      rejectCommand(new Error("Vivaldi CDP timed out: " + method +
        "; " + browserLog.slice(-700)));
    }, timeout);
    pending.set(id, {
      resolve: (data) => { clearTimeout(timer); resolveCommand(data); },
      reject: (error) => { clearTimeout(timer); rejectCommand(error); }
    });
    const request = { id, method, params };
    if (sessionId) request.sessionId = sessionId;
    browser.stdio[3].write(JSON.stringify(request) + "\0", (error) => {
      if (error && pending.has(id)) {
        pending.get(id).reject(error);
        pending.delete(id);
      }
    });
  });
}

// Popup markup is also independently verified in the shared npm tests.
// Keep the live Vivaldi smoke test on browser-level CDP; Vivaldi's renderer
// sessions do not reliably implement Chrome's Runtime debugging protocol.

try {
  const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  const packaged = JSON.parse(await readFile(join(extensionPath, "manifest.json"), "utf8"));
  assert.deepEqual(packaged, source);
  assert.equal(packaged.manifest_version, 3);
  assert.equal(packaged.incognito, "not_allowed");
  assert.deepEqual(packaged.permissions, []);
  assert.deepEqual(packaged.host_permissions, []);
  assert.deepEqual(packaged.optional_permissions, ["downloads"]);
  assert.equal(packaged.optional_host_permissions, undefined);

  // The Extensions.loadUnpacked CDP command requires a private debugging
  // pipe and --enable-unsafe-extension-debugging. Both exist only in this
  // disposable test process, never the product or user configuration.
  browser = spawn(executablePath, [
    "--user-data-dir=" + profile,
    "--remote-debugging-pipe",
    "--enable-unsafe-extension-debugging",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-sandbox",
    "about:blank"
  ], { stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"] });
  browser.stderr.on("data", (chunk) => {
    browserLog = (browserLog + chunk.toString("utf8")).slice(-3000);
  });
  browser.on("error", (error) => { browserLog += error.message; });
  browser.on("exit", () => {
    for (const task of pending.values()) {
      task.reject(new Error("Vivaldi browser closed during CDP smoke"));
    }
    pending.clear();
  });
  let data = "";
  browser.stdio[4].on("data", (chunk) => {
    data += chunk.toString("utf8");
    let end;
    while ((end = data.indexOf("\0")) !== -1) {
      const packet = data.slice(0, end);
      data = data.slice(end + 1);
      if (!packet) continue;
      const message = JSON.parse(packet);
      const task = pending.get(message.id);
      if (!task) continue;
      pending.delete(message.id);
      if (message.error) {
        task.reject(new Error("Vivaldi CDP " + message.error.message));
      } else {
        task.resolve(message.result);
      }
    }
  });

  const version = await send("Browser.getVersion");
  assert.match(version.product, /Chrome|Vivaldi|Chromium/,
    "Official Vivaldi must respond to its browser debugging protocol");
  const install = await send("Extensions.loadUnpacked",
    { path: extensionPath, enableInIncognito: false });
  const extensionId = install.id;
  assert.match(extensionId, /^[a-p]{32}$/,
    "Vivaldi must actually install the unpacked MV3 extension");

  const inventory = await send("Extensions.getExtensions");
  const installed = inventory.extensions?.find((item) => item.id === extensionId);
  assert.ok(installed, "Vivaldi must report the installed unpacked extension");
  assert.equal(installed.enabled, true,
    "The Vivaldi extension must be enabled after installation");
  console.log("Vivaldi installed extension:", extensionId,
    "name:", installed.name, "version:", installed.version);

  const popupURL = "chrome-extension://" + extensionId + "/popup.html";
  const target = await send("Target.createTarget", { url: popupURL });
  assert.ok(target.targetId, "Vivaldi must open the extension popup target");

  // Target metadata is emitted by the browser process, not renderer Runtime.
  // Requiring the expected document title proves the local popup has loaded.
  let popupInfo;
  for (let attempt = 0; attempt < 30; attempt++) {
    const list = await send("Target.getTargets");
    const found = list.targetInfos?.find((entry) => entry.targetId === target.targetId);
    if (found?.url === popupURL && found.title?.includes("PDF Magic Opener")) {
      popupInfo = found;
      break;
    }
    await pause(200);
  }
  assert.ok(popupInfo,
    "Vivaldi must load the packaged local popup with its expected document title");

  const originalHtml = await readFile(join(root, "src/popup.html"), "utf8");
  const bundledHtml = await readFile(join(extensionPath, "popup.html"), "utf8");
  assert.equal(bundledHtml, originalHtml);
  assert.match(bundledHtml, /<title>PDF Magic Opener/);
  assert.match(bundledHtml, /role="status"/);
  assert.match(bundledHtml, /Not active/);
  assert.match(bundledHtml, /id="scanPDF"[^>]*disabled[^>]*aria-disabled="true"/);
  assert.match(bundledHtml,
    /Scan PDF is unavailable until a verified native scanner is connected/);
  const bundledCss = await readFile(join(extensionPath, "popup.css"), "utf8");
  assert.equal(bundledCss, await readFile(join(root, "src/popup.css"), "utf8"));
  assert.match(bundledHtml,
    /id="openPDFMagicPreferences" href="pdfmagicopener:\/\/preferences"/);
  console.log("Vivaldi Stable smoke passed: installed MV3 extension and loaded inert popup.");
} finally {
  if (browser && browser.exitCode === null && browser.signalCode === null) {
    browser.kill("SIGTERM");
    for (let i = 0; i < 20 && browser.exitCode === null &&
         browser.signalCode === null; i++) await pause(100);
    if (browser.exitCode === null && browser.signalCode === null) {
      browser.kill("SIGKILL");
    }
  }
  await rm(profile, { recursive: true, force: true });
}
