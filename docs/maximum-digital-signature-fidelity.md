# Signed-document fidelity regression (opener-0526)

This test-only regression verifies the handling of PDF documents that carry
digital signatures. The existing optional Maximum raster-only converter cannot
preserve a detached signature over the original document bytes.

The test creates two one-page synthetic, vector-art PDFs with genuine detached
PKCS#7/CMS signatures. A new ephemeral private key is held exclusively in
memory; no existing key, credential, or user document is accessed. Each source
has a real PDF signature field and widget, /FT /Sig, /V, /ByteRange,
/SubFilter /adbe.pkcs7.detached, and /AcroForm /SigFlags. The second fixture
also declares catalog /Perms /DocMDP.

Both Linux and macOS validate the exact signed byte ranges, use OpenSSL to
verify the detached CMS signature, and verify that modification of signed
artwork bytes invalidates it. The fixtures use untrusted synthetic self-signed
certificates; cryptographic signature verification here is **not** proof of
signer identity, certificate trust, authority, or revocation status.

The existing Maximum preflight must reject both signature-bearing documents
before invoking the renderer. The attempt cannot yield a converted-copy offer,
malware verdict, opening permission, fallback, or clean-cache publication.
Quarantine and the requirement for a separate scan remain intact. An unsigned
control ensures ordinary PDFs are not mistaken for signed inputs.

macOS CI also invokes the actual compiled CoreGraphics worker directly to
make the fidelity boundary explicit: the worker may decline to render entirely,
or it may produce a new raster-only PDF, but it must not carry forward a
signature dictionary, signing field, signed byte range, or original text.
Directly invoking the worker does **not** override the preflight refusal or
authorize a new file to open.

This deliberately does not attempt to transplant a cryptographic signature
onto newly rasterized bytes, verify arbitrary signature trust chains, or
accept undeclared or malformed signature structures. The scanner, sanitized
copy production code, preferences and installed protection mode are unchanged.
Maximum remains nonselectable.
