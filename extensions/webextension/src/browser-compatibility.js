/**
 * Unprivileged WebExtensions API compatibility layer (opener-0572).
 *
 * This module has no import-time effects and never registers listeners,
 * requests permissions, forwards messages, opens files, or issues scan verdicts.
 * It adapts only the harmless runtime metadata methods explicitly invoked by
 * the caller. Firefox/Safari may expose `browser` Promise APIs; Chromium and
 * Safari may expose `chrome` callback APIs. Namespace is not a browser ID.
 */

const genericFailure = () => new Error("Browser extension runtime operation failed");

const isRuntime = (candidate) =>
  candidate !== null && typeof candidate === "object" &&
  typeof candidate.getManifest === "function" &&
  typeof candidate.getURL === "function";

/**
 * Bind to an explicitly provided browser globals object; no API is called.
 * Callers can pass globalThis only at their integration boundary.
 *
 * @param {{browser?: object, chrome?: object}} namespaces
 * @returns {{namespace: string, getManifest: function, getResourceURL: function,
 *            getPlatformInfo: function}}
 */
export function createBrowserCompatibility(namespaces = {}) {
  if (namespaces === null || typeof namespaces !== "object") {
    throw new TypeError("Browser extension namespaces are required");
  }

  const browserRuntime = namespaces.browser?.runtime;
  const chromeRuntime = namespaces.chrome?.runtime;
  const useBrowser = isRuntime(browserRuntime);
  const runtime = useBrowser ? browserRuntime : chromeRuntime;
  if (!isRuntime(runtime)) {
    throw new Error("A WebExtensions runtime is required");
  }

  const namespace = useBrowser ? "browser" : "chrome";

  const getManifest = () => {
    try {
      return runtime.getManifest();
    } catch {
      throw genericFailure();
    }
  };

  const getResourceURL = (resourcePath) => {
    if (typeof resourcePath !== "string" || resourcePath.length > 256 ||
        !/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(resourcePath) ||
        resourcePath.split("/").some((segment) =>
          segment === "" || segment === "." || segment === "..")) {
      throw new TypeError("Resource path must be a relative extension asset path");
    }
    try {
      return runtime.getURL(resourcePath);
    } catch {
      throw genericFailure();
    }
  };

  // Optional metadata, not a permission check or a scanner-safety verdict.
  const getPlatformInfo = async () => {
    if (typeof runtime.getPlatformInfo !== "function") {
      throw new Error("Browser platform metadata is unavailable");
    }
    if (useBrowser) {
      try {
        return await runtime.getPlatformInfo();
      } catch {
        throw genericFailure();
      }
    }
    return new Promise((resolve, reject) => {
      try {
        runtime.getPlatformInfo((info) => {
          // Access lastError inside the callback, as Chrome requires.
          try {
            if (runtime.lastError) {
              reject(genericFailure());
            } else {
              resolve(info);
            }
          } catch {
            reject(genericFailure());
          }
        });
      } catch {
        reject(genericFailure());
      }
    });
  };

  return Object.freeze({ namespace, getManifest, getResourceURL, getPlatformInfo });
}
