// A deterministic 16 MiB+ PDF served as an HTTP response with byte ranges.
// Browser-only test fixture: no external URLs, user files or scanner access.
import assert from "node:assert/strict";
import { Readable } from "node:stream";

export const LARGE_REMOTE_PDF_PATH = "/large/remote.pdf";
export const LARGE_REMOTE_PDF_MIN_BYTES = 16 * 1024 * 1024;
const CHUNK_BYTES = 64 * 1024;

// A valid, one-page PDF whose uncompressed content stream contains a large,
// inert whitespace region. The large bytes belong to a real PDF stream,
// rather than an appended trailer that the viewer may ignore.
export function createLargeRemotePdf() {
  const content = "BT /F1 18 Tf 60 730 Td (Large Remote PDF Viewer Test) Tj ET\n" +
    " ".repeat(LARGE_REMOTE_PDF_MIN_BYTES);
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
      "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    "<< /Length " + Buffer.byteLength(content) + " >>\nstream\n" +
      content + "\nendstream",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
  ];
  let output = "%PDF-1.4\n";
  const offsets = [0];
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(output));
    output += (index + 1) + " 0 obj\n" + object + "\nendobj\n";
  }
  const xref = Buffer.byteLength(output);
  output += "xref\n0 " + (objects.length + 1) +
    "\n0000000000 65535 f \n" +
    offsets.slice(1).map(n => String(n).padStart(10, "0") + " 00000 n \n").join("") +
    "trailer\n<< /Size " + (objects.length + 1) +
    " /Root 1 0 R >>\nstartxref\n" + xref + "\n%%EOF\n";
  const pdf = Buffer.from(output, "ascii");
  assert.ok(pdf.length > LARGE_REMOTE_PDF_MIN_BYTES);
  return pdf;
}

function parseRange(raw, size) {
  if (raw === undefined) return { start: 0, end: size - 1, partial: false };
  if (typeof raw !== "string") return null;
  const match = /^bytes=(\d*)-(\d*)$/.exec(raw);
  if (!match || (match[1] === "" && match[2] === "")) return null;
  const startText = match[1];
  const endText = match[2];
  const start = startText === "" ? null : Number(startText);
  const end = endText === "" ? null : Number(endText);
  if ((start !== null && !Number.isSafeInteger(start)) ||
      (end !== null && !Number.isSafeInteger(end))) return null;
  if (start === null) {
    if (end === null || end === 0) return null;
    return { start: Math.max(0, size - end), end: size - 1, partial: true };
  }
  if (start >= size || (end !== null && start > end)) return null;
  return { start, end: Math.min(end ?? size - 1, size - 1), partial: true };
}

/**
 * Serve a fixed generated PDF through a real, bounded HTTP response. The
 * caller must bind the server to 127.0.0.1. HEAD, full GET, and single HTTP
 * byte ranges mimic remote document servers; malformed ranges fail with 416.
 */
export function createLargeRemotePdfRoute(pdf) {
  assert.ok(Buffer.isBuffer(pdf) &&
    pdf.subarray(0, 5).toString("ascii") === "%PDF-" &&
    pdf.length > LARGE_REMOTE_PDF_MIN_BYTES,
  "Expected a generated large PDF");
  let requests = 0;
  let fullRequests = 0;
  let rangeRequests = 0;
  let invalidRanges = 0;

  function handle(request, response) {
    if (request.url !== LARGE_REMOTE_PDF_PATH) return false;
    if (request.method !== "GET" && request.method !== "HEAD") {
      response.writeHead(405, { Allow: "GET, HEAD", "Cache-Control": "no-store" });
      response.end();
      return true;
    }
    const range = parseRange(request.headers.range, pdf.length);
    if (!range) {
      invalidRanges++;
      response.writeHead(416, {
        "Content-Range": "bytes */" + pdf.length,
        "Content-Length": "0", "Accept-Ranges": "bytes",
        "Cache-Control": "no-store"
      });
      response.end();
      return true;
    }

    requests++;
    if (range.partial) rangeRequests++;
    else fullRequests++;
    const length = range.end - range.start + 1;
    response.writeHead(range.partial ? 206 : 200, {
      "Content-Type": "application/pdf",
      "Content-Disposition": "inline",
      "Cache-Control": "no-store",
      "Accept-Ranges": "bytes",
      "Content-Length": length,
      "X-Content-Type-Options": "nosniff",
      ...(range.partial ? {
        "Content-Range": "bytes " + range.start + "-" + range.end +
          "/" + pdf.length
      } : {})
    });
    if (request.method === "HEAD") {
      response.end();
      return true;
    }
    function* parts() {
      for (let i = range.start; i <= range.end; i += CHUNK_BYTES) {
        yield pdf.subarray(i, Math.min(i + CHUNK_BYTES, range.end + 1));
      }
    }
    const stream = Readable.from(parts());
    stream.on("error", () => response.destroy());
    response.once("close", () => stream.destroy());
    stream.pipe(response);
    return true;
  }
  return Object.freeze({
    handle,
    path: LARGE_REMOTE_PDF_PATH,
    size: pdf.length,
    snapshot: () => Object.freeze({ requests, fullRequests, rangeRequests,
      invalidRanges })
  });
}
