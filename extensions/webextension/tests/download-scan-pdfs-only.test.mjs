import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  SCAN_PDFS_ONLY_LABEL,
  readScanPdfsOnlyPreference,
  considerDownloadForScan,
  createScanPdfsOnlySetting
} from "../src/download-scan-pdfs-only.js";

const mime = (id, type) => ({ id, mime: type });
const file = (id, name) => ({ id, filename: name });
const pdf = () => [mime(42, "application/pdf"), file(42, "/downloads/report.bin")];
const other = () => [mime(42, "text/plain"), file(42, "/downloads/report.txt")];

function node(tagName = "section", ownerDocument = null) {
  const events = new Map();
  return {
    nodeType: 1, tagName, ownerDocument, hidden: false, type: "",
    checked: false, disabled: false, textContent: "", children: [],
    attributes: {}, addEventListener(name, cb) {
      if (!events.has(name)) events.set(name, new Set());
      events.get(name).add(cb);
    },
    removeEventListener(name, cb) { events.get(name)?.delete(cb); },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes[name] = value; },
    async fire(name, event) {
      await Promise.all([...events.get(name) ?? []].map(cb => cb(event)));
    },
    get listenerCount() {
      return [...events.values()].reduce((n, s) => n + s.size, 0);
    }
  };
}

function fixture(config = { scanPdfsOnly: true, customChoice: "keep" }) {
  const doc = { createElement(tag) { return node(tag, doc); } };
  const root = node("section", doc);
  const writes = [];
  let stored = config;
  const store = {
    readConfiguration() { return Promise.resolve(stored); },
    saveScanPdfsOnly(value) {
      writes.push(value);
      stored = { ...stored, scanPdfsOnly: value };
      return Promise.resolve(true);
    }
  };
  const option = createScanPdfsOnlySetting(root, store);
  const input = () => root.children[0]?.children[0];
  return { root, store, option, writes, input, read: () => stored };
}

test("missing option defaults to PDF-only without changing any active capability", () => {
  assert.equal(readScanPdfsOnlyPreference({ customChoice: "keep" }), true);
  assert.equal(readScanPdfsOnlyPreference({ scanPdfsOnly: true }), true);
  assert.equal(readScanPdfsOnlyPreference({ scanPdfsOnly: false }), false);
  assert.equal(readScanPdfsOnlyPreference(Object.create(null)), true);
});

test("malformed, accessor and inherited preferences fail closed", () => {
  let getterCalls = 0;
  const accessor = {};
  Object.defineProperty(accessor, "scanPdfsOnly", {
    get() { getterCalls++; throw Error("private setting"); }
  });
  for (const value of [null, false, [], "true", new Date(), accessor,
    { scanPdfsOnly: "false" }, { scanPdfsOnly: null },
    Object.create({ scanPdfsOnly: false }),
    new Proxy({}, { getOwnPropertyDescriptor() { throw Error("private"); } })]) {
    assert.equal(readScanPdfsOnlyPreference(value), null);
  }
  assert.equal(getterCalls, 0);
});

test("PDF-only scope includes MIME PDFs even with a misleading filename", () => {
  const result = considerDownloadForScan({}, ...pdf());
  assert.deepEqual(result, {
    id: 42, pdfCandidate: true, included: true,
    authorizesScan: false, authorizesOpen: false
  });
  assert.equal(Object.isFrozen(result), true);
});

test("PDF-only scope includes filename PDFs with generic browser MIME", () => {
  const result = considerDownloadForScan({ scanPdfsOnly: true },
    mime(42, "application/octet-stream"), file(42, "/downloads/REPORT.PDF"));
  assert.equal(result.pdfCandidate, true);
  assert.equal(result.included, true);
});

test("PDF-only excludes non-PDF hints; disabling broadens only candidate consideration", () => {
  const candidates = other();
  assert.equal(considerDownloadForScan({}, ...candidates).included, false);
  const broadened = considerDownloadForScan({ scanPdfsOnly: false }, ...candidates);
  assert.equal(broadened.included, true);
  assert.equal(broadened.pdfCandidate, false);
  assert.equal(broadened.authorizesScan, false);
  assert.equal(broadened.authorizesOpen, false);
});

test("invalid, mismatched and hostile metadata never passes the scope filter", () => {
  const pairs = [
    [mime(42, "application/pdf"), file(43, "x.pdf")],
    [mime(42, "application/pdf"), { id: 42, filename: "x.pdf", extra: true }],
    [mime(42, "bad mime"), file(42, "x.pdf")],
    [{ id: 42, mime: "application/pdf", authorizesOpen: true }, file(42, "x.pdf")],
    [null, file(42, "x.pdf")],
    [mime(42, "application/pdf"), null],
    [mime(42, "application/pdf"), { id: 42, get filename() { throw Error("secret"); } }]
  ];
  for (const [a, b] of pairs) {
    assert.equal(considerDownloadForScan({ scanPdfsOnly: false }, a, b), null);
  }
  assert.equal(considerDownloadForScan({ scanPdfsOnly: "false" }, ...pdf()), null);
});

test("explicit load renders a labeled accessible checkbox without saving", async () => {
  const f = fixture();
  assert.equal(f.root.hidden, true);
  assert.deepEqual(await f.option.load(), { status: "ready", scanPdfsOnly: true });
  const label = f.root.children[0];
  assert.equal(label.tagName, "label");
  assert.equal(f.input().tagName, "input");
  assert.equal(f.input().type, "checkbox");
  assert.equal(f.input().checked, true);
  assert.equal(label.children[1].textContent, SCAN_PDFS_ONLY_LABEL);
  assert.match(f.root.children[1].textContent, /does not enable scanning other file types/);
  assert.equal(f.root.children[2].attributes["aria-live"], "polite");
  assert.deepEqual(f.writes, []);
});

test("a trusted user change saves only the chosen boolean and preserves other settings", async () => {
  const f = fixture();
  await f.option.load();
  f.input().checked = false;
  await f.input().fire("change", { isTrusted: true, target: f.input() });
  assert.deepEqual(f.option.state(), { status: "ready", scanPdfsOnly: false });
  assert.deepEqual(f.writes, [false]);
  assert.deepEqual(f.read(), { scanPdfsOnly: false, customChoice: "keep" });
  assert.equal(f.root.children[2].textContent, "Download preference saved.");
  f.input().checked = true;
  await f.input().fire("change", { isTrusted: true, target: f.input() });
  assert.deepEqual(f.writes, [false, true]);
  assert.equal(f.option.state().scanPdfsOnly, true);
});

test("synthetic and mismatched events cannot change saved settings", async () => {
  const f = fixture();
  await f.option.load();
  f.input().checked = false;
  for (const event of [{ isTrusted: false, target: f.input() },
    { isTrusted: true }, { isTrusted: "true", target: f.input() },
    { isTrusted: true, target: {} }]) {
    await f.input().fire("change", event);
  }
  assert.deepEqual(f.writes, []);
  assert.equal(f.input().checked, true);
});

test("save refusal, rejection and unconfirmed persistence restore previous choice", async () => {
  for (const implementation of [
    () => Promise.resolve(false),
    () => Promise.reject(Error("/private/secret")),
    () => Promise.resolve(true),
    () => ({ accepted: true })
  ]) {
    const f = fixture();
    f.store.saveScanPdfsOnly = implementation;
    await f.option.load();
    f.input().checked = false;
    await f.input().fire("change", { isTrusted: true, target: f.input() });
    assert.equal(f.input().checked, true);
    assert.equal(f.input().disabled, false);
    assert.deepEqual(f.option.state(), { status: "ready", scanPdfsOnly: true });
    assert.match(f.root.children[2].textContent, /Could not confirm/);
    assert.doesNotMatch(f.root.children[2].textContent, /private|secret/);
  }
});

test("pending saves disable repeated changes and use a fresh authoritative read", async () => {
  const f = fixture();
  let release;
  f.store.saveScanPdfsOnly = next => new Promise(resolve => {
    f.writes.push(next);
    release = () => resolve(true);
  });
  await f.option.load();
  f.input().checked = false;
  const pending = f.input().fire("change", { isTrusted: true, target: f.input() });
  assert.equal(f.input().disabled, true);
  await f.input().fire("change", { isTrusted: true, target: f.input() });
  assert.deepEqual(f.writes, [false]);
  release();
  await pending;
  assert.equal(f.option.state().scanPdfsOnly, true, "unconfirmed writes are not claimed");
});

test("clear and dispose remove handlers and invalidate pending reads", async () => {
  const f = fixture();
  let release;
  f.store.readConfiguration = () => new Promise(resolve => { release = resolve; });
  const pending = f.option.load();
  f.option.clear();
  release({ scanPdfsOnly: false });
  await pending;
  assert.equal(f.root.hidden, true);
  assert.deepEqual(f.option.state(), { status: "unavailable", scanPdfsOnly: null });
  f.store.readConfiguration = () => Promise.resolve({ scanPdfsOnly: true });
  await f.option.load();
  const previous = f.input();
  f.option.dispose();
  f.option.dispose();
  assert.equal(previous.listenerCount, 0);
  assert.equal(f.root.hidden, true);
  assert.deepEqual(await f.option.load(), { status: "unavailable", scanPdfsOnly: null });
});

test("store failures never invent a preference or overwrite one", async () => {
  for (const store of [
    {}, null,
    { readConfiguration() { return Promise.reject(Error("secret")); },
      saveScanPdfsOnly() { throw Error("no"); } },
    { readConfiguration() { return Promise.resolve({ scanPdfsOnly: "yes" }); },
      saveScanPdfsOnly() { throw Error("no"); } }
  ]) {
    const doc = { createElement(tag) { return node(tag, doc); } };
    const root = node("section", doc);
    const controller = createScanPdfsOnlySetting(root, store);
    assert.deepEqual(await controller.load(),
      { status: "unavailable", scanPdfsOnly: null });
    assert.equal(root.hidden, true);
  }
});

test("the new setting does not activate browser, native or scanner functionality", async () => {
  const source = await readFile(new URL("../src/download-scan-pdfs-only.js", import.meta.url), "utf8");
  const worker = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.equal(worker.trimEnd().endsWith("void 0;"), true);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  for (const forbidden of ["storage.local", "chrome.", "browser.", "sendNativeMessage(",
    "connectNative(", "downloads.open(", "addListener(", "clamscan", "scan-and-open.py"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
