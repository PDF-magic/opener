import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  EXTENSION_CONFIG_VERSION,
  DEFAULT_EXTENSION_CONFIG,
  createDefaultExtensionConfig
} from "../src/configuration-defaults.js";

const expected = {
  downloadMonitoringEnabled: false,
  automaticScanRequestsEnabled: false,
  nativeMessagingEnabled: false,
  automaticOpenEnabled: false,
  notificationsEnabled: false
};

test("defaults have an explicit version and only safe disabled capabilities", () => {
  assert.equal(EXTENSION_CONFIG_VERSION, 1);
  assert.deepEqual(DEFAULT_EXTENSION_CONFIG, expected);
  assert.deepEqual(Object.keys(DEFAULT_EXTENSION_CONFIG).sort(), Object.keys(expected).sort());
  for (const value of Object.values(DEFAULT_EXTENSION_CONFIG)) {
    assert.equal(typeof value, "boolean");
    assert.equal(value, false);
  }
});

test("the exported baseline is immutable even in strict-mode modules", () => {
  assert.equal(Object.isFrozen(DEFAULT_EXTENSION_CONFIG), true);
  assert.throws(() => {
    DEFAULT_EXTENSION_CONFIG.downloadMonitoringEnabled = true;
  }, TypeError);
  assert.throws(() => {
    DEFAULT_EXTENSION_CONFIG.unreviewedPrivilege = true;
  }, TypeError);
  assert.deepEqual(DEFAULT_EXTENSION_CONFIG, expected);
});

test("each defaults snapshot is detached from the global baseline and other callers", () => {
  const first = createDefaultExtensionConfig();
  const second = createDefaultExtensionConfig();
  assert.deepEqual(first, expected);
  assert.deepEqual(second, expected);
  assert.notStrictEqual(first, second);
  assert.notStrictEqual(first, DEFAULT_EXTENSION_CONFIG);
  first.downloadMonitoringEnabled = true;
  first.automaticOpenEnabled = true;
  first.customUserPreference = "preserved by a later settings loader";
  assert.deepEqual(second, expected);
  assert.deepEqual(DEFAULT_EXTENSION_CONFIG, expected);
  assert.deepEqual(createDefaultExtensionConfig(), expected);
});

test("configuration defaults never claim scan approval or bypass user-selected handling", () => {
  const unsafe = [
    "skipScanner", "scanApproved", "fromCache", "allowOverwrite",
    "quarantineDisabled", "pdfVerified", "signatureFreshnessBypass",
    "selectedApplication", "defaultPdfHandler"
  ];
  for (const key of unsafe) assert.equal(Object.hasOwn(DEFAULT_EXTENSION_CONFIG, key), false);
});

test("defaults do not request browser privileges or change the inert manifest", async () => {
  const source = JSON.parse(
    await readFile(new URL("../manifest.json", import.meta.url), "utf8")
  );
  assert.deepEqual(source.permissions, []);
  assert.deepEqual(source.host_permissions, []);
  assert.equal(source.nativeMessaging, undefined);
  assert.equal(source.content_scripts, undefined);
  assert.deepEqual(Object.keys(source.action).sort(), ["default_icon", "default_title"]);
  assert.equal(source.action.default_title, "PDF Magic Opener (not active)");
  assert.deepEqual(source.action.default_icon, source.icons);
  assert.equal(source.action.default_popup, undefined);
  assert.equal(source.action.onClicked, undefined);
});

test("defaults module imports without browser APIs, storage or native side effects", async () => {
  const code = await readFile(new URL("../src/configuration-defaults.js", import.meta.url), "utf8");
  const executable = code.replace(/\/\/[^\n]*/g, "");
  for (const forbidden of [
    "localStorage", "sessionStorage", "chrome.", "browser.", "fetch(",
    "XMLHttpRequest", "WebSocket", "sendNativeMessage", "connectNative",
    "addListener(", "setItem(", "getItem(", "scan-and-open",
    "node:fs", "require(", "import("
  ]) {
    assert.equal(executable.includes(forbidden), false, forbidden);
  }
});

test("config defaults do not depend on active background registration", async () => {
  const pkg = JSON.parse(
    await readFile(new URL("../package.json", import.meta.url), "utf8")
  );
  assert.equal(pkg.scripts.test, "node --test tests/*.test.mjs");
  assert.equal(pkg.dependencies, undefined);
  assert.equal(pkg.devDependencies, undefined);
});
