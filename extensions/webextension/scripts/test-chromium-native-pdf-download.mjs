// Real unbranded Chromium native PDF download smoke (opener-1059).
// Reuse Chrome's isolated, byte-for-byte browser download assertions, but
// reject a branded Chrome binary before any browser can launch.
// Never installs an extension, accesses user files or invokes a scanner.
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const binary = process.argv[2] || process.env.CHROMIUM_BINARY_PATH;
assert.ok(binary,
  "Usage: node scripts/test-chromium-native-pdf-download.mjs CHROMIUM_BINARY");
const version = execFileSync(binary, ["--version"], {
  encoding: "utf8", timeout: 5000
}).trim();
assert.match(version, /^Chromium\s+\d+(?:\.|$)/,
  "Must use real unbranded Chromium, not Google Chrome");

const sharedSmoke = fileURLToPath(
  new URL("./test-chrome-native-pdf-download.mjs", import.meta.url)
);
const result = spawnSync(process.execPath, [sharedSmoke, binary], {
  stdio: "inherit",
  timeout: 120_000,
  env: {
    ...process.env,
    // The shared smoke only serves loopback PDFs to a disposable profile.
    CHROME_TEST_NO_SANDBOX: process.env.CHROMIUM_TEST_NO_SANDBOX === "1" ? "1" : "0",
    // Chromium must never enter Chrome's macOS artifact handoff path.
    PDF_MAGIC_CHROME_HANDOFF_DIR: ""
  }
});
if (result.error) throw result.error;
assert.equal(result.signal, null, "Chromium download smoke must not be killed");
assert.equal(result.status, 0, "Chromium must complete real PDF downloads");
console.log("PASS Chromium native PDF attachment and octet downloads: " + version);
