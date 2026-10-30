import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { assessExplicitPdfCrossOrigin, CROSS_ORIGIN_PDF_MESSAGE } from "../src/explicit-pdf-cross-origin.js";

const doc = "https://reader.example.org/";
const resource = "https://files.example.org/";
const request = () => ({
  version: 1, requestId: "scan_78", source: "embedded-pdf",
  tabId: 4, frameId: 8, selectionId: "selection_8", userInitiated: true
});
const originContext = (target = resource) => ({
  requestId: "scan_78", tabId: 4, frameId: 8, selectionId: "selection_8",
  resourceId: "resource_4", documentOrigin: doc, resourceOrigin: target,
  verified: true, permissionGranted: true
});
const coordinator = (target) => ({
  crossOriginPdfReady: true,
  readVerifiedPdfOriginContext: () => originContext(target)
});
const manifest = () => ({
  manifest_version: 3, host_permissions: [],
  optional_host_permissions: ["https://files.example.org/*"]
});
function permissions(check = async () => true) {
  const listeners = new Set();
  const api = {
    calls: [],
    contains(query) { this.calls.push(query); return check(query); },
    onRemoved: {
      addListener(fn) { listeners.add(fn); },
      removeListener(fn) { listeners.delete(fn); }
    },
    revoke() { for (const fn of listeners) fn({ origins: [resource + "*"] }); },
    listenerCount() { return listeners.size; }
  };
  return api;
}

test("untrusted metadata and an inactive coordinator never authorize cross-origin access", async () => {
  const result = await assessExplicitPdfCrossOrigin();
  assert.deepEqual(result, {
    status: "unavailable", crossOrigin: false, sitePermissionVerified: false,
    requiresSitePermission: false, authorizesFetch: false,
    authorizesScan: false, authorizesOpen: false
  });
  assert.ok(Object.isFrozen(result));
  assert.match(CROSS_ORIGIN_PDF_MESSAGE, /another website/);
});

test("same-origin selection does not request a site grant or touch the network", async () => {
  const api = permissions(() => { throw Error("must not check"); });
  const result = await assessExplicitPdfCrossOrigin({
    request: request(), coordinator: coordinator(doc), permissionsApi: api
  });
  assert.equal(result.status, "same-origin");
  assert.equal(result.crossOrigin, false);
  assert.equal(result.authorizesFetch, false);
  assert.deepEqual(api.calls, []);
});

test("cross-origin PDFs are restricted by the shipped no-host-permission manifest", async () => {
  const shipped = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url), "utf8"));
  const api = permissions();
  const result = await assessExplicitPdfCrossOrigin({
    request: request(), coordinator: coordinator(), permissionsApi: api,
    manifest: shipped
  });
  assert.equal(result.status, "cross-origin-restricted");
  assert.equal(result.requiresSitePermission, true);
  assert.equal(result.sitePermissionVerified, false);
  assert.deepEqual(api.calls, []);
});

test("only an exact declared destination and two current browser grants verify site permission", async () => {
  const api = permissions();
  const result = await assessExplicitPdfCrossOrigin({
    request: request(), coordinator: coordinator(), manifest: manifest(), permissionsApi: api
  });
  assert.equal(result.status, "cross-origin-site-grant-verified");
  assert.equal(result.sitePermissionVerified, true);
  assert.equal(result.authorizesFetch, false);
  assert.equal(result.authorizesScan, false);
  assert.equal(result.authorizesOpen, false);
  assert.deepEqual(api.calls, [
    { origins: [resource + "*"] }, { origins: [resource + "*"] }
  ]);
  assert.equal(api.listenerCount(), 0);
});

test("different subdomains are cross-origin even within one parent domain", async () => {
  const api = permissions();
  const result = await assessExplicitPdfCrossOrigin({
    request: request(), coordinator: coordinator(), manifest: {
      ...manifest(), optional_host_permissions: [doc + "*"]
    }, permissionsApi: api
  });
  assert.equal(result.status, "cross-origin-restricted");
  assert.deepEqual(api.calls, []);
});

test("broad, unrelated or undeclared grants never substitute for exact origin", async () => {
  const api = permissions();
  for (const perms of [
    ["<all_urls>"], ["https://*.example.org/*"], ["https://*/*"],
    ["https://other.example.org/*"], ["http://files.example.org/*"],
    [resource + "*", "https://*.example.org/*"], []
  ]) {
    const result = await assessExplicitPdfCrossOrigin({
      request: request(), coordinator: coordinator(), permissionsApi: api,
      manifest: { ...manifest(), optional_host_permissions: perms }
    });
    assert.equal(result.status, "cross-origin-restricted", JSON.stringify(perms));
  }
  assert.deepEqual(api.calls, []);
});

test("denied, unverified, and inaccessible browser permission APIs stay restricted", async () => {
  for (const api of [
    null, {}, { contains: async () => true },
    permissions(async () => false),
    permissions(async () => "true"),
    permissions(() => undefined),
    permissions(async () => { throw Error("sensitive details"); })
  ]) {
    const result = await assessExplicitPdfCrossOrigin({
      request: request(), coordinator: coordinator(), permissionsApi: api, manifest: manifest()
    });
    assert.notEqual(result.status, "cross-origin-site-grant-verified");
    assert.equal(result.authorizesFetch, false);
  }
});

test("permission removal during asynchronous grant check fails closed", async () => {
  let resolve;
  const api = permissions(() => new Promise(done => { resolve = done; }));
  const pending = assessExplicitPdfCrossOrigin({
    request: request(), coordinator: coordinator(), permissionsApi: api, manifest: manifest()
  });
  api.revoke();
  resolve(true);
  assert.equal((await pending).status, "cross-origin-restricted");
  assert.equal(api.listenerCount(), 0);
});

test("redirects and document changes during awaited permissions invalidate the selection", async () => {
  let resolve;
  const api = permissions(() => new Promise(done => { resolve = done; }));
  const trusted = coordinator();
  const pending = assessExplicitPdfCrossOrigin({
    request: request(), coordinator: trusted, permissionsApi: api, manifest: manifest()
  });
  trusted.readVerifiedPdfOriginContext = () => originContext("https://redirect.example.org/");
  resolve(true);
  assert.equal((await pending).status, "unavailable");
});

test("changed resource identity, tab/frame or origin provenance are rejected", async () => {
  const trusted = coordinator();
  for (const invalid of [
    { ...originContext(), frameId: 0 },
    { ...originContext(), requestId: "other" },
    { ...originContext(), resourceId: "" },
    { ...originContext(), permissionGranted: false },
    { ...originContext(), verified: "true" },
    { ...originContext(), extra: "https://secret.invalid/" },
    { ...originContext(), documentOrigin: "http://reader.example.org/" },
    { ...originContext(), resourceOrigin: "https://user@files.example.org/" },
    { ...originContext(), resourceOrigin: "https://files.example.org:444/" },
    { ...originContext(), resourceOrigin: "https://files.example.org/other" },
    { ...originContext(), resourceOrigin: "null" },
    { ...originContext(), resourceOrigin: "blob:https://files.example.org/id" },
    { ...originContext(), resourceOrigin: "https://FILES.example.org/" },
    { ...originContext(), resourceOrigin: "https://127.0.0.1/" }
  ]) {
    trusted.readVerifiedPdfOriginContext = () => invalid;
    const outcome = await assessExplicitPdfCrossOrigin({
      request: request(), coordinator: trusted, manifest: manifest(), permissionsApi: permissions()
    });
    assert.equal(outcome.status, "unavailable");
  }
});

test("hostile objects, getters and inherited capability claims fail closed", async () => {
  const trusted = coordinator();
  const hostile = originContext();
  Object.defineProperty(hostile, "resourceOrigin", {
    get() { throw Error("do not call page getter"); }
  });
  for (const item of [hostile, Object.create(originContext()), [],
    new Proxy({}, { ownKeys() { throw Error("private"); } })]) {
    trusted.readVerifiedPdfOriginContext = () => item;
    assert.equal((await assessExplicitPdfCrossOrigin({
      request: request(), coordinator: trusted, manifest: manifest(), permissionsApi: permissions()
    })).status, "unavailable");
  }
  const getter = {};
  Object.defineProperty(getter, "crossOriginPdfReady", {
    get() { throw Error("do not call"); }
  });
  assert.equal((await assessExplicitPdfCrossOrigin({
    request: request(), coordinator: getter
  })).status, "unavailable");
});

test("module import and assessment never fetch, request grants, inspect pages or invoke a scanner", async () => {
  const src = await readFile(new URL("../src/explicit-pdf-cross-origin.js", import.meta.url), "utf8");
  for (const forbidden of ["fetch(", "XMLHttpRequest", "chrome.", "browser.",
    "permissions.request(", "connectNative(", "sendNativeMessage(", "document.",
    "querySelector(", "window.open(", "download(", "node:fs", "localStorage"]) {
    assert.equal(src.includes(forbidden), false, forbidden);
  }
  const manifestData = JSON.parse(await readFile(
    new URL("../manifest.json", import.meta.url), "utf8"
  ));
  assert.deepEqual(manifestData.host_permissions, []);
  assert.equal(manifestData.optional_host_permissions, undefined);
  assert.equal((await assessExplicitPdfCrossOrigin({
    request: request(), coordinator: coordinator(), manifest: manifestData,
    permissionsApi: permissions()
  })).status, "cross-origin-restricted");
});
