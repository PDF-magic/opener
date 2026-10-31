// Synthetic, deliberately malformed HTTP PDFs for actual browser viewer tests.
// No real user documents, upstream requests, or PDF scanner privileges.
export const MALFORMED_REMOTE_PDF_CASES = Object.freeze([
  Object.freeze({
    path: "/malformed/truncated.pdf",
    reason: "truncated-pdf-without-pages-or-xref",
    body: Buffer.from("%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n", "ascii")
  }),
  Object.freeze({
    path: "/malformed/not-a-pdf.pdf",
    reason: "non-pdf-bytes-with-pdf-mime",
    body: Buffer.from("Not a PDF document. Deliberately invalid test content.\n", "ascii")
  })
]);

export function createMalformedRemotePdfRoutes() {
  const counts = new Map(MALFORMED_REMOTE_PDF_CASES.map(item => [item.path, 0]));

  function handle(request, response) {
    if (typeof request.url !== "string" ||
        !request.url.startsWith("/malformed/")) return false;

    if (request.method !== "GET") {
      response.writeHead(405, {
        "Allow": "GET", "Cache-Control": "no-store"
      });
      response.end();
      return true;
    }
    const item = MALFORMED_REMOTE_PDF_CASES.find(test => test.path === request.url);
    if (!item) {
      response.writeHead(404, { "Cache-Control": "no-store" });
      response.end();
      return true;
    }
    counts.set(item.path, counts.get(item.path) + 1);
    response.writeHead(200, {
      "Content-Type": "application/pdf",
      "Content-Disposition": "inline",
      "Content-Length": item.body.byteLength,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    });
    response.end(item.body);
    return true;
  }

  return Object.freeze({
    handle,
    cases: Object.freeze(MALFORMED_REMOTE_PDF_CASES.map(({ path, reason }) =>
      Object.freeze({ path, reason }))),
    snapshot: () => Object.freeze(Object.fromEntries(counts))
  });
}
