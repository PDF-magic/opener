import { copyFile, lstat, readFile } from "node:fs/promises";
import { join } from "node:path";

// Informational UI with exactly one inert, disabled scan control. Reject any
// enabled, scripted or remotely loaded interactions until reviewed integration.
const assets = Object.freeze(["popup.html", "popup.css"]);
const preferencesAction =
  '<a id="openPDFMagicPreferences" href="pdfmagicopener://preferences">Open PDF Magic Preferences</a>';
const disabledScanControl =
  '<button id="scanPDF" type="button" disabled aria-disabled="true" aria-describedby="scanPDFUnavailable">Scan PDF</button>';
const disabledScanExplanation =
  '<p id="scanPDFUnavailable">Scan PDF is unavailable until a verified native scanner is connected.</p>';
const disallowed = /<\s*(?:script|iframe|frame|object|embed|form|input|button|a|video|audio|select|textarea|details|summary)\b|\bon[a-z]+\s*=|\bcontenteditable\s*=|https?:\/\/|javascript\s*:|data\s*:|(?:@import|url\s*\(|expression\s*\()/i;

export function validatePopupAsset(name, content) {
  if (!assets.includes(name) || typeof content !== "string" ||
      !content || content.length > 8192 ||
      (name === "popup.html"
        ? (content.split(preferencesAction).length !== 2 ||
           content.split(disabledScanControl).length !== 2 ||
           content.split(disabledScanExplanation).length !== 2 ||
           disallowed.test(content
             .replace(preferencesAction, "")
             .replace(disabledScanControl, "")
             .replace(disabledScanExplanation, "")))
        : disallowed.test(content))) {
    throw new Error("Unsafe WebExtensions popup asset");
  }
  if (name === "popup.html" && (
    !/^<!doctype html>\n<html lang="en">\n/i.test(content) ||
    !content.includes('<link rel="stylesheet" href="popup.css">') ||
    !content.includes('role="status"') ||
    !content.includes("Not active") ||
    !content.includes("cannot scan, sanitize, or open PDF files yet.") ||
    !content.includes("</html>")
  )) {
    throw new Error("Unsafe or misleading WebExtensions popup markup");
  }
  if (name === "popup.css" && !content.includes("prefers-color-scheme")) {
    throw new Error("Missing accessible WebExtensions popup styles");
  }
}

export async function copyPopupAssets(root, output) {
  for (const name of assets) {
    const from = join(root, "src", name);
    const info = await lstat(from);
    if (!info.isFile() || info.isSymbolicLink() || info.size > 8192) {
      throw new Error("Invalid WebExtensions popup source file");
    }
    const source = await readFile(from, "utf8");
    validatePopupAsset(name, source);
    await copyFile(from, join(output, name));
  }
}
