import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  MAX_EXPLICIT_PDF_DOWNLOAD_BYTES, MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES,
  copyExplicitPdfWithinSizeLimit as copy
} from "../src/explicit-pdf-download-size.js";

function destination() {
  const state = { writes: [], commits: [], aborts: 0 };
  return {
    state,
    write: async (chunk) => { state.writes.push(chunk.byteLength); return true; },
    commit: async (bytes) => { state.commits.push(bytes); return true; },
    abort: async () => { state.aborts++; }
  };
}
async function* chunks(...sizes) {
  for (const size of sizes) yield new Uint8Array(size);
}

test("uses a fixed 100 MiB hard maximum and bounded 8 MiB transfer chunks", () => {
  assert.equal(MAX_EXPLICIT_PDF_DOWNLOAD_BYTES, 104857600);
  assert.equal(MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES, 8388608);
  assert.ok(MAX_EXPLICIT_PDF_DOWNLOAD_BYTES > MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES);
});

test("streams in-bound chunks and commits only after complete consumption", async () => {
  const dest = destination();
  const result = await copy({ source: chunks(4, 6), destination: dest, maxBytes: 10 });
  assert.deepEqual(result, {
    status: "size-verified-transfer", bytesTransferred: 10,
    transferComplete: true, sizeVerified: true,
    scanVerified: false, authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
  assert.deepEqual(dest.state, { writes: [4, 6], commits: [10], aborts: 0 });
});

test("rejects over-limit streams before forwarding the violating chunk", async () => {
  const dest = destination();
  const result = await copy({ source: chunks(4, 7), destination: dest, maxBytes: 10 });
  assert.equal(result.status, "size-limit-exceeded");
  assert.deepEqual(dest.state, { writes: [4], commits: [], aborts: 1 });
  assert.equal(result.sizeVerified, false);
  assert.equal(result.authorizesOpen, false);
  assert.equal(Object.isFrozen(result), true);
});

test("stops reading the source after overflow and closes its iterator", async () => {
  const dest = destination();
  const flags = { read: 0, closed: false };
  async function* source() {
    try {
      flags.read++; yield new Uint8Array(5);
      flags.read++; yield new Uint8Array(6);
      flags.read++; yield new Uint8Array(1); // Must not be reached.
    } finally {
      flags.closed = true;
    }
  }
  assert.equal((await copy({ source: source(), destination: dest, maxBytes: 10 })).status,
    "size-limit-exceeded");
  assert.equal(flags.read, 2);
  assert.equal(flags.closed, true);
  assert.equal(dest.state.aborts, 1);
});

test("rejects invalid, unlimited and expanded caps without reading data", async () => {
  for (const maxBytes of [
    -1, 0, null, false, true, "10", 1.5, NaN, Infinity,
    MAX_EXPLICIT_PDF_DOWNLOAD_BYTES + 1
  ]) {
    const dest = destination();
    const result = await copy({ source: chunks(4), destination: dest, maxBytes });
    assert.equal(result.status, "unavailable", String(maxBytes));
    assert.deepEqual(dest.state, { writes: [], commits: [], aborts: 0 });
  }
});

test("does not accept empty transfers, missing lengths or malformed chunks", async () => {
  const invalid = [
    chunks(),
    (async function* () { yield new Uint8Array(0); })(),
    (async function* () { yield "PDF"; })(),
    (async function* () { yield new ArrayBuffer(8); })(),
    (async function* () { yield new Uint8Array(MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES + 1); })()
  ];
  for (const source of invalid) {
    const dest = destination();
    const result = await copy({ source, destination: dest, maxBytes: 10 });
    assert.equal(result.status, "unavailable");
    assert.equal(dest.state.commits.length, 0);
    assert.equal(dest.state.aborts, 1);
  }
});

test("never commits partial output after read, write or commit failures", async () => {
  const scenarios = [
    { source: (async function* () {
      yield new Uint8Array(2);
      throw Error("/private/report.pdf");
    })() },
    { source: chunks(2, 3), write: async () => false },
    { source: chunks(2), write: async () => { throw Error("secret"); } },
    { source: chunks(2), commit: async () => false },
    { source: chunks(2), commit: async () => { throw Error("secret"); } }
  ];
  for (const scenario of scenarios) {
    const dest = destination();
    if (scenario.write) dest.write = scenario.write;
    if (scenario.commit) dest.commit = scenario.commit;
    const result = await copy({
      source: scenario.source, destination: dest, maxBytes: 10
    });
    assert.equal(result.status, "unavailable");
    assert.equal(dest.state.aborts, 1);
    assert.equal(JSON.stringify(result).includes("secret"), false);
  }
});

test("missing destination methods and accessor-based sinks fail closed", async () => {
  for (const destination of [
    null, {}, { write() {}, commit() {} },
    { write: async () => true, commit: async () => true },
    Object.defineProperty({ commit: async () => true, abort: async () => {} },
      "write", { get() { throw Error("must not run"); } })
  ]) {
    assert.equal((await copy({ source: chunks(3), destination })).status, "unavailable");
  }
});

test("successful transfer never bypasses scanning, changes preferences or activates downloads", async () => {
  const read = path => readFile(new URL(path, import.meta.url), "utf8");
  const [source, acquisition, manifestText, worker, ci] = await Promise.all([
    read("../src/explicit-pdf-download-size.js"),
    read("../src/explicit-pdf-download-acquisition.js"),
    read("../manifest.json"), read("../src/background.js"),
    read("../../../.github/workflows/ci.yml")
  ]);
  const manifest = JSON.parse(manifestText);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.ok(worker.trimEnd().endsWith("void 0;"));
  assert.match(acquisition, /downloads\.download\(\)/);
  assert.match(ci, /node --test tests\/explicit-pdf-download-size\.test\.mjs/);
  for (const forbidden of [
    "fetch(", "XMLHttpRequest", "chrome.", "browser.", "globalThis.",
    "downloads.open(", "permissions.request(", "sendNativeMessage(",
    "connectNative(", "localStorage", "clamscan(", "window.open("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
});
