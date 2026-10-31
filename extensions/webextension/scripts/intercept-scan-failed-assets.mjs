// An inert extension-owned page for a future authenticated interception gate.
import { copyFile, lstat, readFile } from "node:fs/promises";
import { join } from "node:path";

export const FAILED_INTERCEPTION_PAGE = "intercept-scan-failed.html";
export const FAILED_INTERCEPTION_CSS = "intercept-scan-failed.css";
const names = [FAILED_INTERCEPTION_PAGE, FAILED_INTERCEPTION_CSS];
const styleLink = '<link rel="stylesheet" href="intercept-scan-failed.css">';
const forbidden = /<\s*(?:script|iframe|frame|object|embed|form|input|button|a|video|audio|select|textarea|details|summary|img|svg|base|style|link)\b|\bon[a-z]+\s*=|\b(?:http-equiv|contenteditable)\s*=|https?:\/\/|javascript\s*:|data\s*:|file\s*:|(?:@import|url\s*\(|expression\s*\(|-moz-binding|behavior\s*:)/i;
const once = (content, fragment) => content.split(fragment).length === 2;

/** Reject executable, navigational or misleading failure-page assets. */
export function validateFailedInterceptionAsset(name, content) {
  if (!names.includes(name) || typeof content !== "string" ||
      !content || content.length > 8192) {
    throw new Error("Invalid automatic-interception failure page asset");
  }
  if (forbidden.test(name === FAILED_INTERCEPTION_PAGE ?
      content.replace(styleLink, "") : content)) {
    throw new Error("Unsafe automatic-interception failure page asset");
  }
  if (name === FAILED_INTERCEPTION_PAGE && (
    !content.startsWith('<!doctype html>\n<html lang="en">\n') ||
    !once(content, styleLink) ||
    !once(content, '<main class="blocked" role="alert" aria-labelledby="scan-failure-title">') ||
    !once(content, '<h1 id="scan-failure-title">PDF blocked: scan did not complete</h1>') ||
    !once(content, 'The PDF was not verified by the required scanner.') ||
    !once(content, 'will not open or release this PDF.') ||
    !once(content, 'cannot prevent opening in other browser viewers, Finder, or other applications.') ||
    !content.includes('<meta name="referrer" content="no-referrer">') ||
    !content.endsWith('</html>\n')
  )) {
    throw new Error("Missing fail-closed automatic-interception warning");
  }
  if (name === FAILED_INTERCEPTION_CSS &&
      (!content.includes("prefers-color-scheme: dark") ||
       !content.includes("max-width: 640px"))) {
    throw new Error("Missing accessible automatic-interception failure styles");
  }
}

/** Copy only approved, local, non-symlink assets into an extension package. */
export async function copyFailedInterceptionAssets(root, output) {
  for (const name of names) {
    const input = join(root, "src", name);
    const stat = await lstat(input);
    if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 8192) {
      throw new Error("Invalid automatic-interception page source file");
    }
    const content = await readFile(input, "utf8");
    validateFailedInterceptionAsset(name, content);
    await copyFile(input, join(output, name));
  }
}
