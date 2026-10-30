import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { Script } from "node:vm";
import test from "node:test";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (path) => readFile(join(root, path), "utf8");

function forbiddenApi(name) {
  return new Proxy(Object.create(null), {
    get(_target, key) {
      throw new Error(`Firefox background unexpectedly accessed ${name}.${String(key)}`);
    },
    set(_target, key) {
      throw new Error(`Firefox background unexpectedly modified ${name}.${String(key)}`);
    }
  });
}

function executeFirefoxBackground(source, availableApis) {
  const forbidden = (name) => () => {
    throw new Error(`Firefox background unexpectedly invoked ${name}`);
  };
  const sandbox = Object.assign(Object.create(null), {
    fetch: forbidden("fetch"),
    setTimeout: forbidden("setTimeout"),
    setInterval: forbidden("setInterval"),
    importScripts: forbidden("importScripts"),
    XMLHttpRequest: forbidden("XMLHttpRequest"),
    WebSocket: forbidden("WebSocket"),
    localStorage: forbiddenApi("localStorage"),
    indexedDB: forbiddenApi("indexedDB")
  });
  if (availableApis.includes("browser")) sandbox.browser = forbiddenApi("browser");
  if (availableApis.includes("chrome")) sandbox.chrome = forbiddenApi("chrome");
  const globalsBefore = Object.keys(sandbox).sort();

  // Firefox MV3 loads background.scripts as a classic script, not an ESM
  // service worker. This also rejects top-level import/export syntax.
  const script = new Script(source, { filename: "firefox/background.js" });
  assert.equal(script.runInNewContext(sandbox, { timeout: 1_000 }), undefined);
  assert.deepEqual(Object.keys(sandbox).sort(), globalsBefore,
    "background startup must not create or remove global properties");
}

test("Firefox loads the shipped background as a classic, non-module script", async () => {
  const manifest = JSON.parse(await load("dist/firefox/manifest.json"));
  assert.deepEqual(manifest.background, { scripts: ["background.js"] });
  assert.equal(manifest.background.service_worker, undefined);
  assert.equal(manifest.background.type, undefined);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  const built = await load(`dist/firefox/${manifest.background.scripts[0]}`);
  assert.equal(built, await load("src/background.js"),
    "Firefox must execute the validated shared background bytes");
  executeFirefoxBackground(built, ["browser", "chrome"]);
});

test("Firefox background startup and restart never access privileged APIs", async () => {
  const built = await load("dist/firefox/background.js");
  for (const apiSet of [["browser", "chrome"], ["browser"], ["chrome"], []]) {
    // Separate VM contexts model a fresh startup and a subsequent restart.
    for (let run = 0; run < 2; run++) {
      executeFirefoxBackground(built, apiSet);
    }
  }
});
