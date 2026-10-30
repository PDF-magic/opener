import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const load = async (file) => JSON.parse(await readFile(join(root, file), "utf8"));
const read = (file) => readFile(join(root, file), "utf8");

test("toolbar offers a deliberate, permission-free native preferences link", async () => {
  const source = await load("manifest.json");
  assert.deepEqual(Object.keys(source.action).sort(), ["default_icon", "default_popup", "default_title"]);
  assert.equal(source.action.default_popup, "preferences.html");
  assert.equal(source.action.default_title, "PDF Magic Opener (not active)");
  assert.deepEqual(source.permissions, []);
  assert.deepEqual(source.host_permissions, []);
  const popup = await read("preferences.html");
  const action = '<a id="openPDFMagicPreferences" href="pdfmagicopener://preferences">Open PDF Magic Preferences</a>';
  assert.ok(popup.includes(action));
  assert.equal(popup.split(action).length, 2, "exactly one explicit user action");
  assert.match(popup, /Browser PDF scanning and opening are not active/);
  assert.match(popup, /installed macOS preferences app is required/);
  assert.doesNotMatch(popup, /<script|<form|<iframe|onload=|onclick=|javascript:|https?:\/\//i);
});

test("Chromium and Firefox package the exact approved popup bytes", async () => {
  const source = await read("preferences.html");
  for (const output of ["dist/preferences.html", "dist/firefox/preferences.html"]) {
    assert.equal(await read(output), source, output);
  }
  for (const path of ["dist/manifest.json", "dist/firefox/manifest.json"]) {
    const manifest = await load(path);
    assert.equal(manifest.action.default_popup, "preferences.html");
    assert.deepEqual(manifest.permissions, []);
    assert.deepEqual(manifest.host_permissions, []);
    assert.equal(manifest.nativeMessaging, undefined);
  }
});

test("native registration and exact URL handling do not modify the PDF scan gate", async () => {
  const app = await read("../../../PDFMagicOpenerApp/PDFMagicOpenerApp.swift");
  const plist = await read("../../../PDFMagicOpenerApp/Info.plist");
  assert.match(plist, /<key>CFBundleURLTypes<\/key>/);
  assert.match(plist, /<string>pdfmagicopener<\/string>/);
  assert.match(app, /url\.absoluteString == "pdfmagicopener:\/\/preferences"/);
  assert.match(app, /NSApplication\.shared\.activate/);
  assert.doesNotMatch(app, /scan.*\(url|open.*pdf|NSWorkspace\.shared\.open\(url/i);
});
