# Password-protected PDF fidelity checks (opener-0523)

Maximum's optional raster-only sanitized-copy converter cannot faithfully
process an encrypted document without accessing its protected contents.
**Correct fidelity behavior is to refuse conversion**, not silently remove
pages, return blank images, prompt for passwords, decrypt, or offer the
original PDF as a substitute.

`test-maximum-password-protected.py` builds real, synthetic, two-page
encrypted PDFs with distinct vector content using pinned `pypdf`. The
cases exercise RC4-40 user/owner passwords, RC4-128 user/owner passwords,
and RC4-128 encryption with an empty user password but nonempty owner
password. The last case matters because an empty user password does **not**
make the PDF unencrypted or authorizes skipping the scanner.

Each case verifies that all existing Maximum copy interfaces reject the
input: `attempt_sanitized_pdf_copy` reports a fixed unsupported-input
sanitizer failure, `assess_sanitized_pdf_copy` blocks with
`encryptedSource`, and `offer_sanitized_pdf_copy` returns no copy.
The test explicitly asserts that no password prompt, `PdfReader.decrypt`
call or converter invocation occurs. The original input bytes are unchanged
and no password appears in reports.

On macOS, the test additionally sends each encrypted document to the
**real compiled CoreGraphics conversion worker**, which must exit nonzero
with no output bytes. An unencrypted control separately proves that the
sanitizer can reach its converter path and still reject invalid output.

The CI workflow runs these tests on Ubuntu (policy, noninterference,
fixtures) and macOS (policy plus real worker). This is a **test-only**
extension: `maximum_sanitized_copy.py`, the CoreGraphics worker, live
ClamAV protections, quarantine, configuration, user preferences and
clean-cache/launch gates are unchanged. Maximum remains unselectable.
Rejection is not a malware detection; it does not authorize bypass,
fallback, or opening.
