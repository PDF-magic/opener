// Exercise the *built Chrome ZIP* after extraction, not the source tree.
// Chrome for Testing supports --load-extension; ordinary branded Chrome 137+
// deliberately does not. Use a disposable profile, local CDP and no web pages.
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const binary = process.argv[2] || process.env.CHROME_PATH;
const extension = process.argv[3];
assert.ok(binary && extension, "Usage: node scripts/test-chrome.mjs CHROME_BINARY EXTRACTED_ZIP_DIRECTORY");
const root = resolve(extension);
const version = execFileSync(binary, ["--version"], { encoding: "utf8", timeout: 5000 }).trim();
assert.match(version, /Chrome|Chromium/, "A real Chrome/Chromium binary is required");
const manifest = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
assert.equal(manifest.manifest_version, 3);
assert.equal(manifest.incognito, "not_allowed");
assert.deepEqual(manifest.permissions, []);
assert.deepEqual(manifest.host_permissions, []);
assert.deepEqual(manifest.optional_permissions, ["downloads"]);
assert.deepEqual(manifest.background, { service_worker: "background.js", type: "module" });

const profile = await mkdtemp(join(tmpdir(), "pdfmagic-chrome-"));
let browser;
let stderrTail = "";
let socket;
let requestId = 0;
const requests = new Map();

function command(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++requestId;
    const deadline = setTimeout(() => {
      requests.delete(id);
      reject(new Error("Chrome DevTools timeout: " + method));
    }, 8000);
    requests.set(id, { resolve, reject, deadline });
    try {
      socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    } catch (error) {
      clearTimeout(deadline);
      requests.delete(id);
      reject(error);
    }
  });
}

async function until(read, description) {
  const deadline = Date.now() + 30000;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await read();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await delay(200);
  }
  throw new Error("Chrome smoke check failed to observe " + description +
    (lastError ? ": " + lastError.message : ""));
}

try {
  const args = [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-default-apps", "--disable-sync",
    "--remote-debugging-port=0", "--user-data-dir=" + profile,
    "--disable-extensions-except=" + root, "--load-extension=" + root,
    "about:blank"
  ];
  // Only needed for local root-owned CI containers, never by default.
  if (process.env.CHROME_TEST_NO_SANDBOX === "1") args.unshift("--no-sandbox");
  browser = spawn(binary, args, { stdio: ["ignore", "ignore", "pipe"] });
  browser.stderr.on("data", (bytes) => {
    stderrTail = (stderrTail + bytes.toString("utf8")).slice(-2500);
  });
  const connection = await until(async () => {
    if (browser.exitCode !== null || browser.signalCode !== null) {
      throw new Error("Chrome exited before DevTools startup");
    }
    const lines = (await readFile(join(profile, "DevToolsActivePort"), "utf8")).trim().split("\n");
    if (!/^\d+$/.test(lines[0]) || !lines[1]?.startsWith("/devtools/browser/")) return null;
    return "ws://127.0.0.1:" + lines[0] + lines[1];
  }, "the isolated DevTools endpoint");
  socket = new WebSocket(connection);
  await new Promise((resolve, reject) => {
    const deadline = setTimeout(() => reject(new Error("Chrome DevTools socket timeout")), 8000);
    socket.onopen = () => { clearTimeout(deadline); resolve(); };
    socket.onerror = () => { clearTimeout(deadline); reject(new Error("Chrome DevTools connection failed")); };
  });
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    const pending = requests.get(message.id);
    if (!pending) return;
    requests.delete(message.id);
    clearTimeout(pending.deadline);
    if (message.error) pending.reject(new Error("Chrome DevTools: " + message.error.message));
    else pending.resolve(message.result);
  };

  // An unpacked extension must actually install and register its MV3 worker.
  // A JSON-only manifest test cannot satisfy this assertion.
  const extensionId = await until(async () => {
    const { targetInfos } = await command("Target.getTargets");
    const workers = targetInfos.filter((t) =>
      t.type === "service_worker" &&
      /^chrome-extension:\/\/[a-p]{32}\/background\.js$/.test(t.url));
    if (workers.length === 0) return null;
    // Chrome for Testing may register other built-in service workers even in a
    // temporary profile. Identify our extension by its actual runtime name,
    // never by the count or ordering of unrelated browser workers.
    for (const worker of workers) {
      try {
        const attached = await command("Target.attachToTarget", {
          targetId: worker.targetId, flatten: true
        });
        const evaluated = await command("Runtime.evaluate", {
          expression: "chrome.runtime.getManifest().name",
          returnByValue: true
        }, attached.sessionId);
        if (!evaluated.exceptionDetails && evaluated.result?.value === "PDF Magic Opener") {
          return worker.url.split("/")[2];
        }
      } catch {
        // An unrelated built-in worker is not our extension.
      }
    }
    return null;
  }, "a loaded PDF Magic Opener MV3 service worker");

  const { targetId } = await command("Target.createTarget", {
    url: "chrome-extension://" + extensionId + "/popup.html"
  });
  const { sessionId } = await command("Target.attachToTarget", { targetId, flatten: true });
  await command("Runtime.enable", {}, sessionId);
  const observed = await until(async () => {
    const { result, exceptionDetails } = await command("Runtime.evaluate", {
      expression: '(() => { ' +
        'if (document.readyState !== "complete" || !document.querySelector("#popup-title")) return null;' +
        'const m = chrome.runtime.getManifest();' +
        'const scan = document.querySelector("#scanPDF");' +
        'return { origin: location.origin, title: document.querySelector("#popup-title").textContent.trim(),' +
        'status: document.querySelector("[role=status]")?.textContent.trim(),' +
        'inactive: document.body.textContent.includes("cannot scan, sanitize, or open PDF files yet"),' +
        'scanDisabled: scan?.disabled === true && scan?.getAttribute("aria-disabled") === "true",' +
        'preferences: document.querySelector("#openPDFMagicPreferences")?.getAttribute("href"),' +
        'scripts: document.querySelectorAll("script").length, styles: document.styleSheets.length,' +
        'manifest: { name: m.name, incognito: m.incognito, permissions: m.permissions,' +
        'host_permissions: m.host_permissions, optional_permissions: m.optional_permissions } }; })()',
      returnByValue: true
    }, sessionId);
    if (exceptionDetails) throw new Error("The Chrome extension popup could not be inspected");
    return result?.value || null;
  }, "the rendered extension popup");

  assert.equal(observed.origin, "chrome-extension://" + extensionId);
  assert.equal(observed.title, "PDF Magic Opener");
  assert.match(observed.status, /Not active/);
  assert.equal(observed.inactive, true);
  assert.equal(observed.scanDisabled, true, "Scan PDF must not become actionable");
  assert.equal(observed.preferences, "pdfmagicopener://preferences");
  assert.equal(observed.scripts, 0, "The popup must remain script-free");
  assert.ok(observed.styles >= 1, "Chrome must load the packaged stylesheet");
  assert.deepEqual(observed.manifest, {
    name: "PDF Magic Opener", incognito: "not_allowed",
    permissions: [], host_permissions: [], optional_permissions: ["downloads"]
  });
  console.log("PASS Chrome for Testing package install, popup and inactive scanner: " + version);
} catch (error) {
  // Only browser startup diagnostics from this fresh, local-only test profile.
  // Never log document content, environment variables, or browser profile files.
  console.error("Chrome startup diagnostic tail:", stderrTail);
  throw error;
} finally {
  try { socket?.close(); } catch { /* browser may already have exited */ }
  for (const { deadline } of requests.values()) clearTimeout(deadline);
  requests.clear();
  if (browser && browser.exitCode === null) browser.kill("SIGTERM");
  await delay(300);
  if (browser && browser.exitCode === null) browser.kill("SIGKILL");
  await rm(profile, { recursive: true, force: true });
}
