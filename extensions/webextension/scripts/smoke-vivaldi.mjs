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

function inspectPopup() {
  const manifest = chrome.runtime.getManifest();
  const scan = document.querySelector("#scanPDF");
  const status = document.querySelector('[role="status"]');
  if (!scan || !status || document.readyState !== "complete") {
    return { ready: false };
  }
  return {
    ready: true,
    manifest,
    heading: document.querySelector("#popup-title")?.textContent,
    status: status.textContent,
    availability: document.querySelector("#availability-title")?.textContent,
    disabled: scan.disabled,
    ariaDisabled: scan.getAttribute("aria-disabled"),
    ariaDescription: scan.getAttribute("aria-describedby"),
    reason: document.querySelector("#scanPDFUnavailable")?.textContent,
    preferences: document.querySelector("#openPDFMagicPreferences")?.getAttribute("href"),
    stylesheet: document.querySelector('link[rel="stylesheet"]')?.getAttribute("href"),
    stylesheetLoaded: [...document.styleSheets].some(
      (sheet) => sheet.href?.endsWith("/popup.css")
    ),
    scripts: document.querySelectorAll("script").length,
    // Query existing permissions only; never request new browser privileges.
    downloadsGranted: null
  };
}

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

  const target = await send("Target.createTarget",
    { url: "chrome-extension://" + extensionId + "/popup.html" });
  assert.ok(target.targetId, "Vivaldi must open the extension popup target");
  const attached = await send("Target.attachToTarget",
    { targetId: target.targetId, flatten: true });
  assert.ok(attached.sessionId);
  await send("Runtime.enable", {}, attached.sessionId);

  let popup;
  for (let i = 0; i < 60; i++) {
    try {
      const result = await send("Runtime.evaluate", {
        expression: "(" + inspectPopup.toString() + ")()",
        returnByValue: true,
        awaitPromise: true
      }, attached.sessionId, 5000);
      if (!result.exceptionDetails && result.result?.value?.ready) {
        popup = result.result.value;
        break;
      }
    } catch {
      // A context can be temporarily destroyed during the first navigation.
    }
    await pause(200);
  }
  assert.ok(popup?.ready, "Vivaldi must render the actual local extension popup");
  assert.equal(popup.manifest.name, "PDF Magic Opener");
  assert.equal(popup.manifest.manifest_version, 3);
  assert.equal(popup.manifest.incognito, "not_allowed");
  assert.deepEqual(popup.manifest.permissions, []);
  assert.deepEqual(popup.manifest.host_permissions, []);
  assert.deepEqual(popup.manifest.optional_permissions, ["downloads"]);
  assert.equal(popup.manifest.optional_host_permissions, undefined);
  assert.deepEqual(popup.manifest.background,
    { service_worker: "background.js", type: "module" });
  assert.equal(popup.heading, "PDF Magic Opener");
  assert.equal(popup.status, "Not active");
  assert.match(popup.availability, /Browser integration is not enabled/);
  assert.equal(popup.disabled, true);
  assert.equal(popup.ariaDisabled, "true");
  assert.equal(popup.ariaDescription, "scanPDFUnavailable");
  assert.match(popup.reason, /verified native scanner/);
  assert.equal(popup.preferences, "pdfmagicopener://preferences");
  assert.equal(popup.stylesheet, "popup.css");
  assert.equal(popup.stylesheetLoaded, true);
  assert.equal(popup.scripts, 0);

  const checkPermission = await send("Runtime.evaluate", {
    expression: "(new Promise(resolve => chrome.permissions.contains(" +
      "{permissions: ['downloads']}, resolve)))",
    returnByValue: true,
    awaitPromise: true
  }, attached.sessionId);
  assert.equal(checkPermission.result?.value, false,
    "Vivaldi must not silently grant optional downloads access");

  console.log("Vivaldi Stable smoke passed: installed MV3 popup, no grants or scanning.");
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
