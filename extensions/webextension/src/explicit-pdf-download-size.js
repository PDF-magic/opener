// A hard byte budget for a trusted, explicitly selected PDF byte stream.
// The browser downloads.download() API does NOT expose a maximum-size option;
// callers must arrange an independently authorized, bounded streaming route.
export const MAX_EXPLICIT_PDF_DOWNLOAD_BYTES = 100 * 1024 * 1024;
export const MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024;

const REJECTED = Object.freeze({
  status: "unavailable", transferComplete: false, sizeVerified: false,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
});
const TOO_LARGE = Object.freeze({
  status: "size-limit-exceeded", transferComplete: false, sizeVerified: false,
  scanVerified: false, authorizesScan: false, authorizesOpen: false
});

function ownMethod(value, key) {
  if (value === null || typeof value !== "object") return null;
  const descriptor = Object.getOwnPropertyDescriptor(value, key);
  return descriptor && Object.hasOwn(descriptor, "value") &&
    typeof descriptor.value === "function" ? descriptor.value : null;
}

/**
 * Transfer an authenticated PDF candidate through a byte-counting boundary.
 *
 * A separately trusted integration supplies a streaming source and a PRIVATE,
 * atomic/quarantined destination implementing async write(chunk), commit(bytes)
 * and abort(). The destination MUST NOT expose partial files, open a PDF, or
 * mark a transfer complete until commit succeeds. Each chunk is checked
 * BEFORE write is called, including if the remote size is absent or dishonest.
 *
 * The source must yield Uint8Array chunks no larger than 8 MiB and support
 * asynchronous iteration. A missing/invalid budget, read/write failure,
 * invalid chunk or empty stream fails closed. Once the byte cap is exceeded,
 * the iterator is closed and the destination is aborted best-effort.
 *
 * This is a passive library, NOT a live network request or the installed
 * WebExtension downloads.download() path. Connecting a supported streaming
 * transport and an atomic destination is separately required to guarantee
 * an on-disk cap. A successful result is NOT a scan verdict or open authority.
 */
export async function copyExplicitPdfWithinSizeLimit({
  source, destination, maxBytes = MAX_EXPLICIT_PDF_DOWNLOAD_BYTES
} = {}) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 ||
      maxBytes > MAX_EXPLICIT_PDF_DOWNLOAD_BYTES ||
      source === null || source === undefined ||
      !destination || typeof destination !== "object") return REJECTED;

  const write = ownMethod(destination, "write");
  const commit = ownMethod(destination, "commit");
  const abort = ownMethod(destination, "abort");
  if (!write || !commit || !abort) return REJECTED;

  let iterator = null;
  let started = false;
  let completed = false;
  let tooLarge = false;
  let count = 0;

  try {
    const iterate = source[Symbol.asyncIterator];
    if (typeof iterate !== "function") return REJECTED;
    iterator = iterate.call(source);
    if (!iterator || typeof iterator.next !== "function" ||
        typeof iterator.return !== "function") return REJECTED;
    started = true;

    while (true) {
      const step = await iterator.next();
      if (step === null || typeof step !== "object") break;
      if (step.done === true) {
        if (count === 0) break; // Empty/unknown PDF is not accepted.
        const persisted = commit.call(destination, count);
        if (!persisted || typeof persisted.then !== "function" ||
            await persisted !== true) break;
        completed = true;
        return Object.freeze({
          status: "size-verified-transfer", bytesTransferred: count,
          transferComplete: true, sizeVerified: true,
          scanVerified: false, authorizesScan: false, authorizesOpen: false
        });
      }
      if (step.done !== false || !(step.value instanceof Uint8Array)) break;
      const bytes = step.value.byteLength;
      if (!Number.isSafeInteger(bytes) || bytes < 1 ||
          bytes > MAX_EXPLICIT_PDF_DOWNLOAD_CHUNK_BYTES) break;
      if (bytes > maxBytes - count) {
        tooLarge = true; // Do not forward the first over-budget chunk.
        break;
      }
      const pending = write.call(destination, step.value);
      if (!pending || typeof pending.then !== "function" ||
          await pending !== true) break;
      count += bytes;
    }
  } catch {
    // Source/destination errors may contain credentials or paths.
  } finally {
    if (!completed && started) {
      // Cancel reading even when the stream supplied no reliable length.
      try { await iterator.return(); } catch {}
      // Abort the entire partial destination, never commit a truncated PDF.
      try { await abort.call(destination); } catch {}
    }
  }

  return tooLarge ? TOO_LARGE : REJECTED;
}
