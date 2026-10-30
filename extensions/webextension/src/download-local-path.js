import { retrieveCompletedDownloadFilename } from "./download-filename.js";

// An absolute path reported by a browser is still untrusted metadata: it is
// never a scan verdict, evidence that a file exists, or authority to open it.

/**
 * Retrieve a completed download's absolute local filesystem path, if the
 * browser exposes one. Delegates exact-ID lookup, permission verification,
 * revocation handling, and private-error isolation to the reviewed filename
 * lookup. Importing this module never reads browser globals or files.
 *
 * Reject relative filenames, URL-shaped paths, UNC/device paths, traversal
 * components and ambiguous separators. A future trusted native coordinator
 * must independently validate identity, canonicalization, and scan safety.
 */
export async function retrieveCompletedDownloadLocalPath(
  downloadsApi, permissionsApi, completion
) {
  const result = await retrieveCompletedDownloadFilename(
    downloadsApi, permissionsApi, completion
  );
  if (result === null) return null;

  const path = result.filename;
  const windows = /^[A-Za-z]:[/\\]/u.test(path);
  const posix = path.startsWith("/") && !path.startsWith("//");
  if (!windows && !posix) return null;

  // Reject Windows alternate data streams and device/UNC namespaces; a
  // browser-supplied name alone cannot grant access to remote resources.
  if (windows && path.slice(2).includes(":")) return null;
  const parts = windows ? path.slice(3).split(/[/\\]/u) : path.slice(1).split("/");
  if (parts.length === 0 || parts.some((part) =>
    part === "" || part === "." || part === "..")) return null;

  // Do not expose extra browser metadata or persist the sensitive path.
  return Object.freeze({ id: result.id, localPath: path });
}
