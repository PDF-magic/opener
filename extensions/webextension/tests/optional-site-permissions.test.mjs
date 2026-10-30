import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { requestOptionalSitePermission } from "../src/optional-site-permissions.js";

const origin = "https://docs.example.org/";
const pattern = "https://docs.example.org/*";
const manifest = () => ({
  manifest_version: 3,
  host_permissions: [],
  optional_host_permissions: [pattern]
});
const browser = (request = async () => true, contains = async () => true) => ({
  request,
  contains
});
const consent = { siteOrigin: origin, siteFeatureEnabled: true, userInitiated: true };
const blocked = (r) => {
  assert.equal(r.sitePermissionVerified, false);
  assert.equal(r.authorizesOpen, false);
};

test("requests only one declared optional HTTPS site with verified consent", async () => {
  const requests = [];
  const api = browser(async (p) => { requests.push(["request", p]); return true; },
    async (p) => { requests.push(["contains", p]); return true; });
  const result = await requestOptionalSitePermission(api, manifest(), consent);
  assert.deepEqual(result, { status: "granted", sitePermissionVerified: true, authorizesOpen: false });
  assert.ok(Object.isFrozen(result));
  assert.deepEqual(requests, [
    ["request", { origins: [pattern] }],
    ["contains", { origins: [pattern] }]
  ]);
});

test("calls the permission prompt synchronously in the user's action", async () => {
  let invoked = false;
  const pending = requestOptionalSitePermission(
    browser(() => { invoked = true; return Promise.resolve(true); }), manifest(), consent
  );
  assert.equal(invoked, true);
  assert.equal((await pending).status, "granted");
});

test("never requests access without explicit feature opt-in and user action", async () => {
  let called = 0;
  const api = browser(() => { called++; return Promise.resolve(true); });
  for (const options of [
    {}, { ...consent, siteFeatureEnabled: false },
    { ...consent, userInitiated: false },
    { ...consent, siteFeatureEnabled: 1 },
    { ...consent, userInitiated: 1 }
  ]) {
    const result = await requestOptionalSitePermission(api, manifest(), options);
    blocked(result);
    assert.equal(result.status, "unavailable");
  }
  assert.equal(called, 0);
});

test("missing or unrelated optional site declarations cannot grant access", async () => {
  let called = 0;
  const api = browser(() => { called++; return Promise.resolve(true); });
  for (const m of [
    {}, { ...manifest(), optional_host_permissions: [] },
    { ...manifest(), optional_host_permissions: undefined },
    { ...manifest(), optional_host_permissions: ["https://other.example.org/*"] },
    { ...manifest(), host_permissions: [pattern] },
    { ...manifest(), manifest_version: 2 }
  ]) {
    blocked(await requestOptionalSitePermission(api, m, consent));
  }
  assert.equal(called, 0);
});

test("rejects broad or mixed optional patterns rather than fallback to wide access", async () => {
  let called = 0;
  const api = browser(() => { called++; return Promise.resolve(true); });
  for (const wild of ["<all_urls>", "https://*/*", "*://docs.example.org/*",
    "https://*.example.org/*", "http://docs.example.org/*", "file:///*"] ) {
    blocked(await requestOptionalSitePermission(api,
      { ...manifest(), optional_host_permissions: [pattern, wild] }, consent));
  }
  assert.equal(called, 0);
});

test("rejects noncanonical URLs, ports, paths, IP addresses, and unsafe schemes", async () => {
  const api = browser(() => { throw new Error("must not request"); });
  for (const bad of [
    "http://docs.example.org/", "https://docs.example.org/path",
    "https://docs.example.org/?q=1", "https://docs.example.org/#fragment",
    "https://docs.example.org:444/", "https://127.0.0.1/",
    "https://localhost/", "file:///private/file.pdf",
    "https://*.example.org/", "https://docs.example.org.evil.test/",
    "https://DOCS.example.org/", "https://user@docs.example.org/",
    "https://docs.example.org", "data:text/plain,test", ""
  ]) {
    assert.equal((await requestOptionalSitePermission(api, manifest(),
      { ...consent, siteOrigin: bad })).status, "unavailable", bad);
  }
});

test("unsupported browser APIs, callback-only APIs, and errors fail closed", async () => {
  for (const api of [null, {}, { request() {} },
    browser(() => undefined), browser(() => { throw Error("internal secret"); }),
    browser(async () => { throw Error("internal secret"); }),
    browser(async () => true, () => undefined),
    browser(async () => true, async () => { throw Error("internal secret"); })
  ]) {
    const result = await requestOptionalSitePermission(api, manifest(), consent);
    assert.equal(result.status, "unavailable");
    blocked(result);
  }
});

test("denials and unverified grants never become authorization", async () => {
  for (const api of [browser(async () => false), browser(async () => "true"),
    browser(async () => true, async () => false),
    browser(async () => true, async () => "true")]) {
    const result = await requestOptionalSitePermission(api, manifest(), consent);
    assert.equal(result.status, "denied");
    blocked(result);
  }
});

test("malicious getter-driven manifest or permissions API cannot trigger side effects", async () => {
  let executed = 0;
  const unsafe = { ...manifest() };
  Object.defineProperty(unsafe, "optional_host_permissions", {
    get() { executed++; throw Error("do not invoke"); }
  });
  blocked(await requestOptionalSitePermission(browser(), unsafe, consent));
  const api = {};
  Object.defineProperty(api, "request", { get() { executed++; throw Error("do not invoke"); } });
  blocked(await requestOptionalSitePermission(api, manifest(), consent));
  assert.equal(executed, 0);
});

test("the shipped manifests request no site hosts and no runtime module activates grants", async () => {
  const source = await readFile(new URL("../src/optional-site-permissions.js", import.meta.url), "utf8");
  for (const forbidden of [
    "chrome.permissions", "browser.permissions", "globalThis.browser", "globalThis.chrome",
    "<all_urls>", "addListener(", "sendNativeMessage(", "window.open("
  ]) assert.equal(source.includes(forbidden), false, forbidden);
  // Test current manifests independently of future API-permission work.
  for (const path of ["manifest.json", "dist/manifest.json", "dist/firefox/manifest.json"]) {
    const p = JSON.parse(await readFile(new URL(`../${path}`, import.meta.url), "utf8"));
    assert.deepEqual(p.host_permissions, []);
    assert.equal(p.optional_host_permissions, undefined);
    assert.equal((await requestOptionalSitePermission(browser(), p, consent)).status, "unavailable");
  }
});
