// Isolated loopback HTTP fixture for real browser-owned PDF downloads.
// No credentials, user files, network fetches or scanner APIs.
import assert from "node:assert/strict";

function createPdf() {
  const stream = "BT /F1 16 Tf 48 710 Td (PDF Magic Native Download Smoke) Tj ET\n";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
      "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    "<< /Length " + Buffer.byteLength(stream) + " >>\nstream\n" +
      stream + "endstream",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
  ];
  let body = "%PDF-1.4\n";
  const offsets = [0];
  for (const [i, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(body));
    body += (i + 1) + " 0 obj\n" + object + "\nendobj\n";
  }
  const xref = Buffer.byteLength(body);
  body += "xref\n0 " + (objects.length + 1) +
    "\n0000000000 65535 f \n" +
    offsets.slice(1).map(n => String(n).padStart(10, "0") +
      " 00000 n \n").join("") +
    "trailer\n<< /Size " + (objects.length + 1) +
    " /Root 1 0 R >>\nstartxref\n" + xref + "\n%%EOF\n";
  return Buffer.from(body, "ascii");
}

export const NATIVE_PDF_DOWNLOAD_CASES = Object.freeze([
  Object.freeze({
    path: "/native-download/attachment.pdf",
    name: "pdfmagic-attachment.pdf",
    mime: "application/pdf",
    selector: "#attachment"
  }),
  Object.freeze({
    path: "/native-download/octet",
    name: "pdfmagic-octet.pdf",
    mime: "application/octet-stream",
    selector: "#octet"
  })
]);

export function createNativePdfDownloadFixture() {
  const pdf = createPdf();
  assert.ok(pdf.length > 200 && pdf.subarray(0, 5).toString() === "%PDF-");
  const counts = new Map(NATIVE_PDF_DOWNLOAD_CASES.map(item => [item.path, 0]));
  let landingRequests = 0;

  function handle(request, response) {
    if (typeof request.url !== "string" ||
        !request.url.startsWith("/native-download/")) return false;
    if (request.method !== "GET") {
      response.writeHead(405, { "Allow": "GET", "Cache-Control": "no-store" });
      response.end();
      return true;
    }
    if (request.url === "/native-download/index") {
      landingRequests++;
      response.writeHead(200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff"
      });
      response.end('<!doctype html><title>Local PDF downloads</title>' +
        NATIVE_PDF_DOWNLOAD_CASES.map(item =>
          '<a id="' + item.selector.slice(1) + '" href="' + item.path +
          '">Download test PDF</a>').join("\n"));
      return true;
    }
    const item = NATIVE_PDF_DOWNLOAD_CASES.find(c => c.path === request.url);
    if (!item) {
      response.writeHead(404, { "Cache-Control": "no-store" });
      response.end();
      return true;
    }
    counts.set(item.path, counts.get(item.path) + 1);
    response.writeHead(200, {
      "Content-Type": item.mime,
      "Content-Disposition": 'attachment; filename="' + item.name + '"',
      "Content-Length": pdf.length,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff"
    });
    response.end(pdf);
    return true;
  }
  return Object.freeze({
    handle,
    pdf,
    cases: NATIVE_PDF_DOWNLOAD_CASES,
    snapshot: () => Object.freeze({
      requests: Object.freeze(Object.fromEntries(counts)),
      landingRequests
    })
  });
}
