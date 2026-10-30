import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const built = join(root, "dist");
const assetNames = [
  "manifest.json", "background.js", "popup.html", "popup.css",
  "icons/icon-16.png", "icons/icon-32.png",
  "icons/icon-48.png", "icons/icon-128.png"
];

test("Edge-compatible Chromium MV3 package preserves inert privileges and exact local assets", async () => {
  const source = JSON.parse(await readFile(join(root, "manifest.json"), "utf8"));
  const manifest = JSON.parse(await readFile(join(built, "manifest.json"), "utf8"));
  assert.deepEqual(manifest, source);
  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.incognito, "not_allowed");
  assert.equal(manifest.name, "PDF Magic Opener");
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.equal(manifest.optional_host_permissions, undefined);
  assert.equal(manifest.content_scripts, undefined);
  assert.equal(manifest.externally_connectable, undefined);
  assert.deepEqual(manifest.background, { service_worker: "background.js", type: "module" });
  assert.equal(manifest.action.default_title, "PDF Magic Opener (not active)");
  assert.equal(manifest.action.default_popup, "popup.html");
  assert.deepEqual(Object.keys(manifest.icons).sort(), ["128", "16", "32", "48"]);
  for (const name of assetNames) {
    const expected = name === "background.js" || name.startsWith("popup.") ?
      join(root, "src", name) : join(root, name);
    const [actual, original] = await Promise.all([
      readFile(join(built, name)), readFile(expected)
    ]);
    assert.deepEqual(actual, original, name + " must be packaged unchanged");
  }
  const worker = await readFile(join(built, "background.js"), "utf8");
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.doesNotMatch(worker.replace(/\/\/[^\n]*/g, ""), /addListener|sendNativeMessage|downloads\./);
});

async function allocatePort() {
  const socket = createServer();
  await new Promise((accept, reject) => {
    socket.once("error", reject);
    socket.listen(0, "127.0.0.1", accept);
  });
  const port = socket.address().port;
  await new Promise((accept) => socket.close(accept));
  return port;
}

test("real Microsoft Edge renders the packaged inactive toolbar popup safely", {
  skip: !process.env.EDGE_WEBDRIVER_BINARY,
  timeout: 90000
}, async () => {
  // The Windows Actions image provides matched Microsoft Edge + EdgeDriver.
  // Avoid external packages, browser downloads and arbitrary network targets.
  const driverPath = resolve(process.env.EDGE_WEBDRIVER_BINARY);
  assert.equal((await stat(driverPath)).isFile(), true);
  const port = await allocatePort();
  const baseUrl = "http://127.0.0.1:" + port;
  const profile = await mkdtemp(join(tmpdir(), "pdf-magic-edge-smoke-"));
  const driver = spawn(driverPath, ["--port=" + port, "--allowed-ips=127.0.0.1"], {
    stdio: "ignore", windowsHide: true
  });
  let sessionId = null;

  async function command(method, endpoint, data) {
    const response = await fetch(baseUrl + endpoint, {
      method,
      headers: { "content-type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify(data),
      signal: AbortSignal.timeout(15000)
    });
    const result = await response.json();
    if (!response.ok || result.value?.error) {
      throw new Error("Microsoft Edge WebDriver request failed: " +
        (result.value?.error ?? response.status));
    }
    return result.value;
  }

  try {
    let ready = false;
    for (let attempt = 0; attempt < 80; attempt += 1) {
      if (driver.exitCode !== null) break;
      try {
        ready = (await command("GET", "/status")).ready === true;
        if (ready) break;
      } catch { /* EdgeDriver may still be starting. */ }
      await new Promise((done) => setTimeout(done, 125));
    }
    assert.equal(ready, true, "Microsoft Edge Driver must start locally");
    const session = await command("POST", "/session", {
      capabilities: {
        alwaysMatch: {
          browserName: "MicrosoftEdge",
          "ms:edgeOptions": {
            args: [
              "--headless=new", "--disable-gpu", "--no-first-run",
              "--no-default-browser-check", "--disable-extensions",
              "--user-data-dir=" + profile
            ]
          }
        }
      }
    });
    sessionId = session.sessionId;
    assert.match(session.capabilities.browserName, /MicrosoftEdge/i);
    assert.match(session.capabilities.browserVersion, /^\d+\./);

    // Branded Edge no longer allows unpacked extension sideloading via flags.
    // Exercise the real Edge DOM/CSS from the packaged source instead.
    await command("POST", "/session/" + sessionId + "/url", {
      url: pathToFileURL(join(built, "popup.html")).href
    });
    const script = [
      'const heading = document.querySelector("#popup-title");',
      'const status = document.querySelector(\'[role="status"]\');',
      'const scan = document.querySelector("#scanPDF");',
      'const preferences = document.querySelector("#openPDFMagicPreferences");',
      'return {',
      '  title: document.title,',
      '  heading: heading?.textContent,',
      '  status: status?.textContent,',
      '  disabled: scan?.disabled,',
      '  ariaDisabled: scan?.getAttribute("aria-disabled"),',
      '  explanation: document.querySelector("#scanPDFUnavailable")?.textContent,',
      '  prefHref: preferences?.getAttribute("href"),',
      '  scriptCount: document.scripts.length,',
      '  bodyWidth: document.body.getBoundingClientRect().width,',
      '  panelPadding: getComputedStyle(document.querySelector(".panel")).paddingTop',
      '};'
    ].join("\n");
    const actual = await command("POST", "/session/" + sessionId + "/execute/sync", {
      script, args: []
    });
    assert.match(actual.title, /PDF Magic Opener/);
    assert.equal(actual.heading, "PDF Magic Opener");
    assert.match(actual.status, /Not active/);
    assert.equal(actual.disabled, true);
    assert.equal(actual.ariaDisabled, "true");
    assert.match(actual.explanation, /unavailable until a verified native scanner is connected/);
    assert.equal(actual.prefHref, "pdfmagicopener://preferences");
    assert.equal(actual.scriptCount, 0);
    assert.ok(actual.bodyWidth >= 260 && actual.bodyWidth <= 360);
    assert.equal(actual.panelPadding, "18px", "Edge must load the packaged CSS");
  } finally {
    if (sessionId) {
      try { await command("DELETE", "/session/" + sessionId); } catch { /* teardown */ }
    }
    driver.kill();
    try { await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }); } catch { /* temporary profile only */ }
  }
});
