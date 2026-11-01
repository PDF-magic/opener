// Real Chromium download-history PDF open smoke (opener-1069).
// Browser-owned opening is NOT PDF Magic scan or handoff authorization.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright-core";
import { createNativePdfDownloadFixture } from "./native-pdf-download-fixture.mjs";

const binary = process.argv[2] || process.env.CHROMIUM_BINARY_PATH;
assert.ok(binary, "Usage: node scripts/test-chromium-history-open.mjs CHROMIUM_BINARY");
const version = execFileSync(binary, ["--version"], {
  encoding: "utf8", timeout: 5000
}).trim();
assert.match(version, /^Chromium\s+\d+(?:\.|$)/,
  "Use actual unbranded Chromium for the download history test");

const fixture = createNativePdfDownloadFixture();
const profile = await mkdtemp(join(tmpdir(), "pdfmagic-history-open-"));
const server = createServer((request, response) => {
  if (fixture.handle(request, response)) return;
  response.writeHead(404, { "Cache-Control": "no-store" });
  response.end();
});
let listening = false;
let context;

async function until(check, description, timeout = 30000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const result = await check();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error("Chromium history-open smoke timed out: " + description +
    (lastError ? " (" + lastError.message + ")" : ""));
}

try {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      listening = true;
      server.removeListener("error", reject);
      resolve();
    });
  });
  context = await chromium.launchPersistentContext(profile, {
    executablePath: binary,
    headless: true,
    acceptDownloads: true,
    downloadsPath: join(profile, "browser-downloads"),
    args: [
      "--no-first-run", "--no-default-browser-check",
      "--disable-background-networking", "--disable-default-apps",
      "--disable-sync", "--disable-extensions",
      "--no-proxy-server", "--proxy-bypass-list=<-loopback>"
    ],
    timeout: 45000
  });
  const page = context.pages()[0] ?? await context.newPage();
  const origin = "http://127.0.0.1:" + server.address().port;
  const landing = await page.goto(origin + "/native-download/index");
  assert.equal(landing?.status(), 200);
  const item = fixture.cases[0];
  const pending = page.waitForEvent("download", { timeout: 30000 });
  await page.locator(item.selector).click();
  const download = await pending;
  assert.equal(download.suggestedFilename(), item.name);
  assert.equal(await download.failure(), null);
  assert.deepEqual(await readFile(await download.path()), fixture.pdf,
    "Downloaded PDF bytes must match the independently generated fixture");
  assert.equal(fixture.snapshot().requests[item.path], 1);

  // Close the origin tab to distinguish the saved history entry from a
  // transient page or download shelf.
  await page.close();
  const history = await context.newPage();
  await history.goto("chrome://downloads/", { waitUntil: "domcontentloaded" });
  assert.equal(history.url(), "chrome://downloads/");
  // This is a fresh disposable profile containing exactly one download.
  // Do not filter Polymer shadow-DOM text: its filename is not guaranteed to
  // be exposed through Playwright's hasText filter on every Chromium version.
  const row = history.locator("downloads-item");
  try {
    await until(async () => (await row.count()) === 1,
      "completed PDF appearing in native download history");
  } catch (error) {
    const diagnostics = await history.evaluate(() => ({
      url: location.href,
      page: document.body?.innerText?.slice(0, 400) ?? "",
      manager: Boolean(document.querySelector("downloads-manager")),
      items: document.querySelector("downloads-manager")?.shadowRoot
        ?.querySelectorAll("downloads-item").length ?? 0
    }));
    throw new Error(error.message + " (" + JSON.stringify(diagnostics) + ")");
  }
  const fileLink = row.locator("#file-link");
  try {
    await until(async () => (await fileLink.count()) === 1,
      "history row exposing the browser-owned Open link", 12000);
  } catch (error) {
    // Only DOM structure for this generated PDF in a fresh test profile.
    const detail = await row.evaluate(element => ({
      fields: Object.keys(element.data ?? {}).sort().slice(0, 30),
      elements: [...(element.shadowRoot?.querySelectorAll("a,button") ?? [])]
        .map(node => ({
          name: node.localName,
          id: node.id,
          label: node.getAttribute("aria-label"),
          text: node.textContent?.trim().slice(0, 70)
        })).slice(0, 25)
    }));
    throw new Error(error.message + " (" + JSON.stringify(detail) + ")");
  }
  const before = await row.evaluate(element => ({
    name: element.data?.fileName,
    opened: element.data?.opened
  }));
  assert.equal(before.name, item.name);
  assert.notEqual(before.opened, true);

  // Trusted click on the real Chromium history entry. This is not the
  // WebExtensions downloads.open API and never grants scanner authority.
  await fileLink.click({ noWaitAfter: true, timeout: 15000 });
  await until(async () => await row.evaluate(element =>
    element.data?.opened === true), "Chromium marking the PDF as opened");
  assert.equal(fixture.snapshot().requests[item.path], 1,
    "History opening must reuse the downloaded file, not fetch it again");
  assert.equal(context.serviceWorkers().some(worker =>
    worker.url().startsWith("chrome-extension://")), false,
  "PDF Magic must not become active during browser-owned opening");
  console.log("PASS real Chromium history PDF Open click: " + version);
} finally {
  try { await context?.close(); } finally {
    if (listening) await new Promise(resolve => server.close(resolve));
    await rm(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}
