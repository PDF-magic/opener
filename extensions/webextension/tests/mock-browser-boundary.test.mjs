import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import test from "node:test";

const guard = new URL("../scripts/forbid-browser-launch.cjs", import.meta.url);
const runGuarded = (script) => spawnSync(process.execPath, [
  "--require", guard.pathname, "--eval", script
], { encoding: "utf8" });

test("mock-only tests reject direct Chrome, Firefox and Safari launches", () => {
  for (const [method, executable] of [
    ["spawn", "google-chrome"], ["spawnSync", "/usr/bin/chromium"],
    ["execFile", "firefox"], ["execFileSync", "/Applications/Safari.app/Contents/MacOS/Safari"],
    ["exec", "brave --version"], ["execSync", "msedge --version"]
  ]) {
    const invocation = method.startsWith("exec") && !method.includes("File")
      ? `cp.${method}(${JSON.stringify(executable)})`
      : `cp.${method}(${JSON.stringify(executable)}, [])`;
    const result = runGuarded(`const cp = require("node:child_process"); ${invocation};`);
    assert.notEqual(result.status, 0, `${method} must reject ${executable}`);
    assert.match(result.stderr, /Mock browser tests must not launch a real browser/);
  }
});

test("mock-only guard also covers imported ESM subprocess methods", () => {
  const result = runGuarded(
    'import("node:child_process").then(({spawnSync}) => spawnSync("firefox", []));'
  );
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Mock browser tests must not launch a real browser/);
});

test("mock-only guard permits ordinary Node subprocesses", () => {
  const result = runGuarded(
    'const {spawnSync} = require("node:child_process");' +
    'const result = spawnSync(process.execPath, ["-e", "process.stdout.write(String(123))"], {encoding:"utf8"});' +
    'if (result.status !== 0 || result.stdout !== "123") process.exit(1);'
  );
  assert.equal(result.status, 0, result.stderr);
});

test("CI runs the complete mocked extension suite without browser binaries", async () => {
  const ci = await readFile(new URL("../../../.github/workflows/browser-mocks.yml", import.meta.url), "utf8");
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.match(ci, /runs-on: ubuntu-latest/);
  assert.match(ci, /node --require \.\/scripts\/forbid-browser-launch\.cjs --test --test-concurrency=1 tests\/\*\.test\.mjs/);
  assert.match(ci, /npm run build/);
  assert.match(ci, /npm run package:chrome/);
  assert.match(ci, /npm run package:firefox/);
  assert.doesNotMatch(ci, /browser-actions\/|playwright|puppeteer|install.*(?:chrome|firefox|chromium)/i);
  assert.equal(pkg.scripts.test, "node --test --test-concurrency=1 tests/*.test.mjs");
});
