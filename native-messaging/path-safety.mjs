// Validate local executable paths used by native host setup and discovery.
// This does not grant any browser-supplied PDF path permission or scan access.
import { constants } from "node:fs";
import { access, lstat } from "node:fs/promises";
import { isAbsolute, join, parse, sep } from "node:path";

export function validateAbsolutePath(value) {
  if (typeof value !== "string" || !isAbsolute(value) ||
      Buffer.byteLength(value, "utf8") > 4096 ||
      /[\x00-\x1f\x7f]/.test(value) ||
      value.split(sep).some(part => part === "." || part === "..")) {
    throw new Error("Supplied path must be an absolute, canonical file path");
  }
  return value;
}

export async function validateExistingPath(value, { executable = false, directory = false } = {}) {
  validateAbsolutePath(value);
  const root = parse(value).root;
  const parts = value.slice(root.length).split(sep).filter(Boolean);
  if (parts.length === 0) throw new Error("Supplied path must name a real file or directory");
  let current = root;
  for (let index = 0; index < parts.length; index += 1) {
    current = join(current, parts[index]);
    const metadata = await lstat(current);
    if (metadata.isSymbolicLink()) throw new Error("symlink in supplied file path");
    if (index !== parts.length - 1 || directory) {
      if (!metadata.isDirectory()) throw new Error("Non-directory in supplied file path");
    } else if (!metadata.isFile()) {
      throw new Error("Native host must be an executable regular file");
    }
    if (index === parts.length - 1 && executable) {
      if (!(metadata.mode & 0o111)) throw new Error("Native host is not executable");
      await access(current, constants.X_OK);
    }
  }
  return value;
}
