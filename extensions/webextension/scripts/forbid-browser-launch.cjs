"use strict";

// Mockable WebExtension contract tests must not silently start real browsers.
// Preload into Node's test workers; dedicated live-browser CI jobs are unaffected.
const childProcess = require("node:child_process");
const { syncBuiltinESMExports } = require("node:module");
const { basename } = require("node:path");

const browserExecutables = new Set([
  "chrome", "google-chrome", "google-chrome-stable", "chromium",
  "chromium-browser", "firefox", "safari", "brave", "brave-browser",
  "microsoft-edge", "microsoft-edge-stable", "msedge", "opera",
  "vivaldi", "arc"
]);

function isBrowserExecutable(command) {
  if (typeof command !== "string") return false;
  return browserExecutables.has(basename(command).toLowerCase().replace(/\.exe$/, ""));
}

function refuseBrowser(command) {
  if (isBrowserExecutable(command)) {
    throw new Error("Mock browser tests must not launch a real browser: " + basename(command));
  }
}

for (const method of ["spawn", "spawnSync", "execFile", "execFileSync"]) {
  const original = childProcess[method];
  childProcess[method] = function(command, ...args) {
    refuseBrowser(command);
    return original.call(this, command, ...args);
  };
}

for (const method of ["exec", "execSync"]) {
  const original = childProcess[method];
  childProcess[method] = function(command, ...args) {
    // Reject the direct shell command form; real-browser smokes run in separate jobs.
    const first = typeof command === "string" ? command.trim().match(/^['"]?([^\s'";|&]+)/)?.[1] : null;
    refuseBrowser(first);
    return original.call(this, command, ...args);
  };
}

// ESM imports of child_process methods must see these same guarded functions.
syncBuiltinESMExports();
