import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { subscribeToHistoryFreeDownloadActivity } from "../src/browsing-history-privacy.js";

const root = fileURLToPath(new URL("../", import.meta.url));

function eventSource() {
  const callbacks = new Set();
  return {
    addListener(listener) { callbacks.add(listener); },
    removeListener(listener) { callbacks.delete(listener); },
    emit(value) { for (const cb of [...callbacks]) cb(value); },
    get size() { return callbacks.size; }
  };
}

function api() {
  return { onCreated: eventSource(), onChanged: eventSource(), onErased: eventSource() };
}

test("no listener starts until explicit subscription, and stopping is irreversible", () => {
  const downloads = api();
  const received = [];
  assert.deepEqual([downloads.onCreated.size, downloads.onChanged.size, downloads.onErased.size], [0, 0, 0]);
  const stop = subscribeToHistoryFreeDownloadActivity(downloads, (event) => received.push(event));
  assert.deepEqual([downloads.onCreated.size, downloads.onChanged.size, downloads.onErased.size], [1, 1, 1]);
  downloads.onCreated.emit({ id: 2 });
  stop();
  stop();
  assert.deepEqual([downloads.onCreated.size, downloads.onChanged.size, downloads.onErased.size], [0, 0, 0]);
  downloads.onChanged.emit({ id: 2, state: { current: "complete" } });
  assert.equal(received.length, 1);
});

test("untrusted browser history metadata is never forwarded or stored", () => {
  const downloads = api();
  const received = [];
  const stop = subscribeToHistoryFreeDownloadActivity(downloads, (event) => received.push(event));
  downloads.onCreated.emit({
    id: 77, filename: "/private/sensitive.pdf", mime: "application/pdf",
    url: "https://private.example/sensitive.pdf?token=secret",
    finalUrl: "https://private.example/redirect", referrer: "https://secret.example/",
    tabId: 91, startTime: "2026-10-30T01:00:00Z",
    byExtensionId: "another-extension", totalBytes: 1234
  });
  downloads.onChanged.emit({
    id: 77, filename: { previous: "/private/old.pdf", current: "/private/new.pdf" },
    url: { current: "https://private.example/other" },
    state: { previous: "in_progress", current: "complete" },
    danger: { current: "safe" }
  });
  downloads.onErased.emit(77);
  stop();
  assert.deepEqual(received, [
    { kind: "created", authorizesOpen: false },
    { kind: "changed", authorizesOpen: false },
    { kind: "erased", authorizesOpen: false }
  ]);
  assert.ok(received.every(Object.isFrozen));
  assert.ok(received.every((event) => Object.keys(event).length === 2));
  assert.equal(JSON.stringify(received).includes("private"), false);
  assert.equal(JSON.stringify(received).includes("77"), false);
  assert.equal(JSON.stringify(received).includes("secret"), false);
});

test("anonymous categories reuse bounded immutable values, not per-download state", () => {
  const downloads = api();
  const seen = [];
  const stop = subscribeToHistoryFreeDownloadActivity(downloads, (value) => seen.push(value));
  for (let id = 0; id < 500; id++) {
    downloads.onCreated.emit({ id, filename: `/tmp/${id}.pdf`, url: `https://secret.test/${id}` });
  }
  stop();
  assert.equal(seen.length, 500);
  assert.ok(seen.every((value) => value === seen[0]));
  assert.deepEqual(seen[0], { kind: "created", authorizesOpen: false });
});

test("missing APIs and registration failures fail closed without lingering handlers", () => {
  const downloads = api();
  assert.throws(() => subscribeToHistoryFreeDownloadActivity(downloads, null), TypeError);
  assert.throws(() => subscribeToHistoryFreeDownloadActivity({}, () => {}), TypeError);
  downloads.onChanged.addListener = () => { throw new Error("registration unavailable"); };
  assert.throws(() => subscribeToHistoryFreeDownloadActivity(downloads, () => {}), /registration unavailable/);
  assert.deepEqual([downloads.onCreated.size, downloads.onChanged.size, downloads.onErased.size], [0, 0, 0]);
});

test("consumer errors are isolated without leaking download details", () => {
  const downloads = api();
  const caught = [];
  const stop = subscribeToHistoryFreeDownloadActivity(downloads, () => {
    throw new Error("consumer failed");
  }, { onError(error) { caught.push(error.message); } });
  downloads.onCreated.emit({ id: 1, url: "https://private.example/secret" });
  stop();
  assert.deepEqual(caught, ["consumer failed"]);
});

test("browser manifest never requests history or host access", async () => {
  for (const path of ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"]) {
    const manifest = JSON.parse(await readFile(join(root, path), "utf8"));
    assert.deepEqual(manifest.permissions, []);
    assert.deepEqual(manifest.host_permissions, []);
    assert.deepEqual(manifest.optional_permissions, ["downloads"]);
    assert.equal(manifest.optional_host_permissions, undefined);
    assert.equal(JSON.stringify(manifest).includes('"history"'), false);
    assert.equal(manifest.content_scripts, undefined);
  }
});

test("extension runtime source never reads browser history or persists browsing events", async () => {
  const files = (await readdir(join(root, "src"))).filter((name) => name.endsWith(".js"));
  assert.ok(files.includes("browsing-history-privacy.js"));
  for (const file of files) {
    const source = await readFile(join(root, "src", file), "utf8");
    const executable = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
    for (const forbidden of [
      /\b(?:chrome|browser)\s*\.\s*history\b/,
      /\b(?:chrome|browser)\s*\.\s*downloads\s*\.\s*search\s*\(/,
      /\b(?:chrome|browser)\s*\.\s*storage\s*\./,
      /\b(?:localStorage|sessionStorage|indexedDB)\s*\./,
      /\b(?:sendBeacon|XMLHttpRequest)\s*\(/
    ]) assert.equal(forbidden.test(executable), false, `${file}: prohibited history/storage API ${forbidden}`);
  }
  const worker = await readFile(join(root, "src", "background.js"), "utf8");
  assert.equal(worker, "// Inactive shared WebExtensions background entry point.\n" +
    "// Do not listen for messages, inspect PDFs or request native access here.\nvoid 0;\n");
});
