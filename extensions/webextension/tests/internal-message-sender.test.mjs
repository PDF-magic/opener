import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { isVerifiedInternalMessageSender } from "../src/internal-message-sender.js";

const CHROME_ID = "abcdefghijklmnopabcdefghijklmnop";
const OTHER_ID = "ponmlkjihgfedcbaponmlkjihgfedcba";
const cases = [
  { id: CHROME_ID, url: `chrome-extension://${CHROME_ID}/` },
  { id: "addon@example.org", url: "moz-extension://12345678-abcd-5678-abcd-123456789abc/" },
  { id: "safari-extension-id", url: "safari-web-extension://1234abcd/" }
];

function runtime({ id, url }) {
  return { id, getURL(path) { assert.equal(path, "/"); return url; } };
}

function sender({ id, url }, path = "popup.html") {
  return { id, url: url + path };
}

test("accepts browser-owned internal pages for Chromium, Firefox and Safari", () => {
  for (const browser of cases) {
    const api = runtime(browser);
    assert.equal(isVerifiedInternalMessageSender(sender(browser), api), true);
    assert.equal(isVerifiedInternalMessageSender({
      ...sender(browser, "options.html?section=general#top"),
      origin: browser.url.slice(0, -1)
    }, api), true);
  }
});

test("rejects messages from other extensions, websites and content scripts", () => {
  for (const browser of cases) {
    const api = runtime(browser);
    for (const untrusted of [
      { id: "not-our-extension", url: browser.url + "popup.html" },
      { id: browser.id, url: "https://example.org/document.pdf" },
      { id: browser.id, url: browser.url.replace("/", "/attacker-") },
      { id: browser.id, url: browser.url + "popup.html", tab: { id: 4 } },
      { id: browser.id, url: browser.url + "popup.html", tab: undefined },
      { id: browser.id, url: browser.url + "popup.html", origin: "null" },
      { id: browser.id, url: browser.url + "popup.html", origin: "https://example.org" },
      { id: browser.id, url: "file:///Users/private/report.pdf" },
      { id: browser.id, url: "data:text/html,hello" },
      { id: browser.id, url: "https://example.org/popup.html#" + browser.id },
      { url: browser.url + "popup.html" },
      { id: browser.id }
    ]) assert.equal(isVerifiedInternalMessageSender(untrusted, api), false,
      JSON.stringify(untrusted));
  }
  const chrome = cases[0];
  assert.equal(isVerifiedInternalMessageSender({
    id: chrome.id, url: `chrome-extension://${OTHER_ID}/popup.html`
  }, runtime(chrome)), false);
  assert.equal(isVerifiedInternalMessageSender({
    id: chrome.id, url: `chrome-extension://${chrome.id}.evil.invalid/popup.html`
  }, runtime(chrome)), false);
});

test("requires a trusted and consistent browser runtime identity and URL", () => {
  const chrome = cases[0];
  const trustedSender = sender(chrome);
  for (const badRuntime of [
    undefined, null, {}, { id: chrome.id },
    { id: OTHER_ID, getURL: () => chrome.url },
    { id: chrome.id, getURL: () => `chrome-extension://${OTHER_ID}/` },
    { id: chrome.id, getURL: () => "https://example.org/" },
    { id: chrome.id, getURL: () => chrome.url + "popup.html" },
    { id: chrome.id, getURL: () => chrome.url + "?query" },
    { id: chrome.id, getURL: () => "not a url" },
    { id: chrome.id, getURL: null },
    { id: "", getURL: () => chrome.url }
  ]) assert.equal(isVerifiedInternalMessageSender(trustedSender, badRuntime), false);
});

test("never evaluates accessors or trusts caller-supplied identity claims", () => {
  const chrome = cases[0];
  const api = runtime(chrome);
  const forged = sender(chrome);
  Object.defineProperty(forged, "origin", { get() { throw Error("executed getter"); } });
  assert.equal(isVerifiedInternalMessageSender(forged, api), false);
  const getterId = sender(chrome);
  Object.defineProperty(getterId, "id", { get() { throw Error("executed getter"); } });
  assert.equal(isVerifiedInternalMessageSender(getterId, api), false);
  const getterUrl = sender(chrome);
  Object.defineProperty(getterUrl, "url", { get() { throw Error("executed getter"); } });
  assert.equal(isVerifiedInternalMessageSender(getterUrl, api), false);
  const runtimeGetter = { getURL: api.getURL };
  Object.defineProperty(runtimeGetter, "id", { get() { throw Error("executed getter"); } });
  assert.equal(isVerifiedInternalMessageSender(sender(chrome), runtimeGetter), false);
  assert.equal(isVerifiedInternalMessageSender(new Proxy({}, {
    getOwnPropertyDescriptor() { throw Error("proxy trap"); }
  }), api), false);
  // A message's claimed sender/origin is not a MessageSender from the browser.
  const fakePayload = { senderId: chrome.id, origin: chrome.url, verified: true };
  assert.equal(isVerifiedInternalMessageSender(fakePayload, api), false);
});

test("verification stays inert and does not register a listener or alter permissions", async () => {
  const src = await readFile(new URL("../src/internal-message-sender.js", import.meta.url), "utf8");
  for (const forbidden of [
    "onMessage.addListener", "onMessageExternal.addListener", "sendMessage(",
    "connectNative(", "sendNativeMessage(", "storage.set(", "storage.local",
    "node:child_process", "node:fs", "fetch("
  ]) assert.equal(src.includes(forbidden), false, forbidden);
  const background = await readFile(new URL("../src/background.js", import.meta.url), "utf8");
  assert.equal(background.includes("internal-message-sender"), false);
  const before = { protectionLevel: "built-in", scanBeforeOpen: true };
  const snapshot = JSON.stringify(before);
  assert.equal(isVerifiedInternalMessageSender(sender(cases[0]), runtime(cases[0])), true);
  assert.equal(JSON.stringify(before), snapshot);
});
