// Pure, fail-closed verification for a future runtime.onMessage listener.
// Pass its browser-supplied MessageSender, never identity claims from a message.
// Importing this module does not install listeners or request permissions.
const EXTENSION_SCHEMES = new Set([
  "chrome-extension:", "moz-extension:", "safari-web-extension:"
]);

function ownData(object, key) {
  if (object === null || typeof object !== "object") return undefined;
  const descriptor = Object.getOwnPropertyDescriptor(object, key);
  return descriptor && Object.hasOwn(descriptor, "value") ? descriptor.value : undefined;
}

function extensionURL(value) {
  if (typeof value !== "string" || value.length > 2048) return null;
  const url = new URL(value);
  if (!EXTENSION_SCHEMES.has(url.protocol) || !url.hostname ||
      url.username || url.password || url.port) return null;
  return url;
}

/**
 * Require a same-extension, internal-page sender rather than merely a valid
 * message envelope. `browserRuntime` MUST be the actual trusted browser API
 * (browser.runtime or chrome.runtime); never obtain it from message.payload.
 *
 * The browser-supplied sender.id must match runtime.id, and its page URL must
 * belong to the extension origin returned by runtime.getURL("/"). Firefox's
 * moz-extension UUID is intentionally not assumed to equal its Gecko add-on ID.
 * Content scripts (sender.tab), webpages, external extensions and missing or
 * inconsistent origin metadata all fail closed. This is not native-host auth.
 */
export function isVerifiedInternalMessageSender(sender, browserRuntime) {
  try {
    const runtimeId = ownData(browserRuntime, "id");
    const getURL = ownData(browserRuntime, "getURL");
    if (typeof runtimeId !== "string" || runtimeId.length === 0 ||
        runtimeId.length > 255 || typeof getURL !== "function" ||
        ownData(sender, "id") !== runtimeId) return false;

    const base = getURL.call(browserRuntime, "/");
    const origin = extensionURL(base);
    const source = extensionURL(ownData(sender, "url"));
    if (!origin || !source || base !== `${origin.protocol}//${origin.host}/` ||
        source.protocol !== origin.protocol || source.host !== origin.host) {
      return false;
    }
    // Extension content scripts execute in tabs; they cannot impersonate an
    // internal page even though their browser-controlled sender.id may match.
    if (Object.getOwnPropertyDescriptor(sender, "tab") !== undefined) return false;

    // Browser versions that expose sender.origin must agree with the trusted
    // runtime URL. Never treat an opaque/sandboxed origin as internal.
    const declaredOrigin = Object.getOwnPropertyDescriptor(sender, "origin");
    if (declaredOrigin && (!Object.hasOwn(declaredOrigin, "value") ||
        declaredOrigin.value !== `${origin.protocol}//${origin.host}`)) return false;
    return true;
  } catch {
    // Proxy traps, accessors, invalid URLs or absent browser APIs deny access.
    return false;
  }
}
