// Passive classification of an observable HTTP Content-Disposition response.
// Attachment disposition is not proof of PDF content or permission to open.
const NONE = Object.freeze({
  isAttachmentResponse: false, evidence: "none", authorizesOpen: false
});
const ATTACHMENT = Object.freeze({
  isAttachmentResponse: true, evidence: "content-disposition", authorizesOpen: false
});
const MAX_HEADERS = 128;
const MAX_VALUE_LENGTH = 4096;
const TOKEN = /^[!#$%&'*+.^_\x60|~0-9A-Za-z-]+/;

function own(record, key) {
  const descriptor = Object.getOwnPropertyDescriptor(record, key);
  return descriptor && Object.hasOwn(descriptor, "value") ?
    descriptor.value : undefined;
}

function plain(record) {
  return record !== null && typeof record === "object" &&
    !Array.isArray(record) &&
    [Object.prototype, null].includes(Object.getPrototypeOf(record));
}

// RFC 6266-style disposition/parameters, including quoted semicolons and
// extended filename* tokens. Never decode, return, or log filenames.
function isAttachment(value) {
  if (typeof value !== "string" || value.length > MAX_VALUE_LENGTH ||
      /[\u0000-\u0008\u000a-\u001f\u007f]/u.test(value)) return false;
  let position = 0;
  const skipSpace = () => {
    while (value[position] === " " || value[position] === "\t") position++;
  };
  const token = () => {
    const match = TOKEN.exec(value.slice(position));
    if (!match) return null;
    position += match[0].length;
    return match[0];
  };
  skipSpace();
  if (token()?.toLowerCase() !== "attachment") return false;
  const names = new Set();
  while (true) {
    skipSpace();
    if (position === value.length) return true;
    if (value[position++] !== ";") return false;
    skipSpace();
    const name = token()?.toLowerCase();
    if (!name || names.has(name)) return false;
    names.add(name);
    skipSpace();
    if (value[position++] !== "=") return false;
    skipSpace();
    if (value[position] === '"') {
      position++;
      let closed = false;
      while (position < value.length) {
        const char = value[position++];
        if (char === '"') { closed = true; break; }
        if (char === "\\") {
          if (position === value.length) return false;
          position++; // quoted-pair; already checked control bytes above
        }
      }
      if (!closed) return false;
    } else if (!token()) {
      return false;
    }
    // The loop requires either the next ';' or end of input, so extraneous
    // bytes, unquoted separators and ambiguous parameter syntax fail closed.
  }
}

/**
 * Inspect only a trusted browser's main-frame responseHeaders data.
 * Browser event authentication and permission checks belong to the caller.
 * This helper never requests headers, installs listeners or scans/opens files.
 */
export function detectAttachmentResponse(details) {
  try {
    if (!plain(details) || own(details, "type") !== "main_frame" ||
        own(details, "frameId") !== 0) return NONE;
    const tabId = own(details, "tabId");
    if (!Number.isSafeInteger(tabId) || tabId < 0) return NONE;
    const headers = own(details, "responseHeaders");
    if (!Array.isArray(headers) || headers.length > MAX_HEADERS) return NONE;
    let disposition;
    for (let index = 0; index < headers.length; index++) {
      if (!Object.hasOwn(headers, index)) return NONE;
      const header = headers[index];
      if (!plain(header)) return NONE;
      const name = own(header, "name");
      if (typeof name !== "string" || name.length > 128 ||
          !TOKEN.test(name) || TOKEN.exec(name)?.[0] !== name) return NONE;
      if (name.toLowerCase() !== "content-disposition") continue;
      if (disposition !== undefined) return NONE; // duplicated headers ambiguous
      disposition = own(header, "value");
      if (typeof disposition !== "string") return NONE;
    }
    return isAttachment(disposition) ? ATTACHMENT : NONE;
  } catch {
    // Proxies, malformed events, and accessor properties are not evidence.
    return NONE;
  }
}
