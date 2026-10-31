// Small deterministic, text-only PDF for an isolated localhost Brave viewer test.
// No user files, remote URLs, JavaScript actions, embedded resources or scanner input.
export function createBraveViewerTestPdf() {
  const stream = "BT /F1 18 Tf 24 90 Td (Brave built-in PDF viewer smoke test) Tj ET\n";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 160] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Length " + Buffer.byteLength(stream) + " >>\nstream\n" + stream + "endstream"
  ];
  let content = "%PDF-1.4\n";
  const offsets = [0];
  for (let index = 0; index < objects.length; index++) {
    offsets.push(Buffer.byteLength(content));
    content += String(index + 1) + " 0 obj\n" + objects[index] + "\nendobj\n";
  }
  const xrefOffset = Buffer.byteLength(content);
  content += "xref\n0 " + String(offsets.length) + "\n";
  content += "0000000000 65535 f \n";
  for (const offset of offsets.slice(1)) {
    content += String(offset).padStart(10, "0") + " 00000 n \n";
  }
  content += "trailer\n<< /Size " + String(offsets.length) +
    " /Root 1 0 R >>\nstartxref\n" + String(xrefOffset) + "\n%%EOF\n";
  return Buffer.from(content, "ascii");
}
