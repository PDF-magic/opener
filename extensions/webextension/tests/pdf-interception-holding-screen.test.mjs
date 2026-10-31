import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { createPdfInterceptionHoldingScreen, PDF_HOLDING_COPY } from
  "../src/pdf-interception-holding-screen.js";

const context = { navigationId: "navigation_17", scanRequestId: "scan_17" };
function element(tagName, ownerDocument) {
  const attributes = new Map();
  return {
    tagName, nodeType: 1, ownerDocument, attributes, children: [],
    textContent: "", className: "", id: "", hidden: false,
    setAttribute(name, value) { attributes.set(name, value); },
    removeAttribute(name) { attributes.delete(name); },
    replaceChildren(...children) { this.children = children; }
  };
}
function fixture() {
  const document = { createElement(tag) { return element(tag, document); } };
  const root = element("section", document);
  root.id = "pdfInterceptionHoldingScreen";
  const coordinator = {
    verifiedPdfInterceptionReady: true,
    active: { ...context, state: "scanning",
      navigationHeld: true, nativeScanStarted: true, authorizesOpen: false },
    readVerifiedHeldPdfScan(ids) { this.lastRead = ids; return this.active; }
  };
  return { root, coordinator,
    screen: createPdfInterceptionHoldingScreen(root, coordinator) };
}
const read = path => readFile(new URL(path, import.meta.url), "utf8");
const denied = value => {
  assert.deepEqual(value, { status: "unavailable", displayed: false,
    scanVerified: false, authorizesScan: false, authorizesOpen: false });
  assert.ok(Object.isFrozen(value));
};

test("screen is hidden by default and requires an extension-owned root", () => {
  const { root } = fixture();
  assert.equal(root.hidden, true);
  assert.deepEqual(root.children, []);
  assert.equal(root.attributes.has("role"), false);
  assert.throws(() => createPdfInterceptionHoldingScreen(null));
  assert.throws(() => createPdfInterceptionHoldingScreen({ nodeType: 1 }));
  const wrong = fixture().root;
  wrong.id = "webPage";
  assert.throws(() => createPdfInterceptionHoldingScreen(wrong));
});

test("active correlated hold shows fixed accessible scanning presentation", () => {
  const f = fixture();
  const result = f.screen.show(context);
  assert.deepEqual(result, { status: "scanning", displayed: true,
    scanVerified: false, authorizesScan: false, authorizesOpen: false });
  assert.ok(Object.isFrozen(result));
  assert.equal(f.root.hidden, false);
  assert.deepEqual(f.coordinator.lastRead, context);
  assert.ok(Object.isFrozen(f.coordinator.lastRead));
  assert.equal(f.root.attributes.get("role"), "status");
  assert.equal(f.root.attributes.get("aria-live"), "polite");
  assert.equal(f.root.attributes.get("aria-busy"), "true");
  assert.equal(f.root.attributes.get("aria-labelledby"),
    "pdf-interception-holding-title");
  const [indicator, heading, description, urlLabel, urlText, warning] =
    f.root.children[0].children;
  assert.equal(indicator.attributes.get("aria-hidden"), "true");
  assert.equal(heading.tagName, "h1");
  assert.equal(heading.id, "pdf-interception-holding-title");
  assert.equal(heading.textContent, PDF_HOLDING_COPY.title);
  assert.equal(description.textContent, PDF_HOLDING_COPY.description);
  assert.equal(urlLabel.textContent, "Original PDF URL");
  assert.equal(urlText.id, "holdingScreenOriginalUrl");
  assert.equal(urlText.attributes.get("aria-labelledby"), urlLabel.id);
  assert.equal(urlText.textContent, "Original PDF URL unavailable.");
  assert.equal(warning.textContent, PDF_HOLDING_COPY.warning);
  assert.equal(f.root.children[0].children.length, 6);
  assert.ok(Object.isFrozen(PDF_HOLDING_COPY));
});

test("missing or unverified hold cannot display false scanning claims", () => {
  const f = fixture();
  denied(createPdfInterceptionHoldingScreen(f.root).show(context));
  assert.equal(f.root.hidden, true);
  for (const patch of [
    { state: "complete" }, { state: "queued" },
    { navigationHeld: false }, { nativeScanStarted: false },
    { authorizesOpen: true }, { navigationId: "other" },
    { scanRequestId: "other" }, { nativeScanStarted: null },
    { url: "https://private.test/file.pdf" }
  ]) {
    const t = fixture();
    Object.assign(t.coordinator.active, patch);
    denied(t.screen.show(context));
    assert.equal(t.root.hidden, true);
    assert.deepEqual(t.root.children, []);
  }
  const t = fixture();
  t.coordinator.verifiedPdfInterceptionReady = false;
  denied(t.screen.show(context));
});

test("malformed IDs, accessors, proxies and inherited claims fail closed", () => {
  const bad = [undefined, null, [], {}, { ...context, extra: true },
    { ...context, scanRequestId: "z".repeat(81) },
    { ...context, navigationId: 10 },
    { ...context, navigationId: "https://private.test/file.pdf" },
    Object.create(context)];
  const getter = { ...context };
  Object.defineProperty(getter, "navigationId", {
    get() { throw Error("private file"); }
  });
  bad.push(getter, new Proxy({}, {
    ownKeys() { throw Error("private file"); }
  }));
  for (const candidate of bad) {
    const f = fixture();
    denied(f.screen.show(candidate));
    assert.equal(f.root.hidden, true);
  }
  for (const active of [null,
    Object.create(fixture().coordinator.active),
    new Proxy({}, { ownKeys() { throw Error("private file"); } })]) {
    const f = fixture();
    f.coordinator.active = active;
    denied(f.screen.show(context));
  }
});

test("coordinator changes during the read prevent rendering", () => {
  for (const change of [
    c => { c.verifiedPdfInterceptionReady = false; },
    c => { c.readVerifiedHeldPdfScan = () => c.active; }
  ]) {
    const f = fixture();
    f.coordinator.readVerifiedHeldPdfScan = function () {
      change(this);
      return this.active;
    };
    denied(f.screen.show(context));
    assert.equal(f.root.hidden, true);
  }
  const f = fixture();
  f.coordinator.readVerifiedHeldPdfScan = () => Promise.resolve(f.coordinator.active);
  denied(f.screen.show(context));
});

test("clear, mismatched updates and dispose erase scanning text", () => {
  const f = fixture();
  f.screen.show(context);
  f.screen.clear();
  assert.equal(f.root.hidden, true);
  assert.deepEqual(f.root.children, []);
  assert.equal(f.root.attributes.has("aria-busy"), false);
  f.screen.show(context);
  denied(f.screen.show({ ...context, scanRequestId: "wrong" }));
  assert.equal(f.root.hidden, true);
  f.screen.show(context);
  f.screen.dispose();
  f.screen.dispose();
  denied(f.screen.show(context));
  assert.deepEqual(f.root.children, []);
});

test("current held scan displays exact original URL but never an opening action", async () => {
  const f = fixture();
  const originalUrl = "https://example.test/a%2Fb.pdf?signature=x%2By#page=2";
  f.coordinator.trustedHoldingScreenReady = true;
  f.coordinator.readCurrentHoldingId = () => context.navigationId;
  f.coordinator.readOriginalHoldingUrl = async ({ holdingId }) =>
    ({ holdingId, originalUrl });
  assert.equal(f.screen.show(context).authorizesOpen, false);
  const text = f.root.children[0].children[4];
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(text.textContent, originalUrl);
  f.screen.clear();
  assert.equal(text.textContent, "Original PDF URL unavailable.");
  assert.equal(f.root.hidden, true);
  denied(f.screen.show({ ...context, scanRequestId: "mismatch" }));
  assert.equal(f.root.children.length, 0);
});

test("late original URL reads cannot repaint after holding screen disposal", async () => {
  const f = fixture();
  let deliver;
  f.coordinator.trustedHoldingScreenReady = true;
  f.coordinator.readCurrentHoldingId = () => context.navigationId;
  f.coordinator.readOriginalHoldingUrl = () =>
    new Promise(resolve => { deliver = resolve; });
  f.screen.show(context);
  const text = f.root.children[0].children[4];
  f.screen.dispose();
  deliver({ holdingId: context.navigationId,
    originalUrl: "https://example.test/a.pdf?token=secret" });
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(text.textContent, "Original PDF URL unavailable.");
  assert.equal(f.root.hidden, true);
});

test("inactive browser permissions, scanner and customizations remain untouched", async () => {
  const [source, css, doc, manifest, safari, background, pkg, ci] =
    await Promise.all([
      read("../src/pdf-interception-holding-screen.js"),
      read("../src/pdf-interception-holding-screen.css"),
      read("../src/pdf-interception-holding-screen.md"),
      read("../manifest.json").then(JSON.parse),
      read("../../safari/manifest.json").then(JSON.parse),
      read("../src/background.js"),
      read("../package.json").then(JSON.parse),
      read("../../../.github/workflows/ci.yml")
    ]);
  for (const forbidden of [
    "globalThis.", "chrome.", "browser.", "addListener(", "fetch(",
    "XMLHttpRequest", "downloads.open(", "downloads.download(",
    "sendNativeMessage(", "connectNative(", "innerHTML", "window.open(",
    "location.href", "localStorage", "sessionStorage", "node:fs"
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /prefers-color-scheme/);
  assert.match(css, /\[hidden\]/);
  assert.doesNotMatch(css, /@import|url\s*\(|javascript:/i);
  assert.match(doc, /opener-0785/);
  assert.match(doc, /inactive/);
  assert.match(doc, /scanner/i);
  assert.match(doc, /user preferences/i);
  assert.match(ci, /node --test tests\/pdf-interception-holding-screen\.test\.mjs/);
  assert.match(pkg.scripts.test, /tests\/\*\.test\.mjs/);
  assert.deepEqual(manifest.permissions, []);
  assert.deepEqual(manifest.host_permissions, []);
  assert.deepEqual(manifest.optional_permissions, ["downloads"]);
  assert.deepEqual(safari.permissions, ["nativeMessaging"]);
  assert.deepEqual(safari.host_permissions, []);
  assert.match(background, /void 0;/);
});
