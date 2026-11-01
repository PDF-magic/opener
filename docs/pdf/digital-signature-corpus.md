# Digital-signature PDF security corpus (opener-1040)

The test-only `digital_signature_corpus.py` generator produces two complete,
one-page PDFs containing **genuine detached CMS/PKCS#7 signatures**: an
approval-signature widget and a certification-permission example with
`/Perms /DocMDP`, a `/Sig` field and `/Reference` transform parameters.
Both have a serialized `/ByteRange` that excludes the hexadecimal signature
contents, and the test verifies the exact signed bytes and rejects alteration.

The RSA signing keys are generated in memory at test time and discarded; the
repository stores no private keys or signed user documents. Fixture bytes
therefore vary between independent test runs. The synthetic self-signed
certificates are **not trusted signers**: OpenSSL verification checks only CMS
integrity, not identity, certificate trust, timestamp validity or revocation.

These samples are separate from the six unchanged protection-profile baseline
PDFs and from the earlier Maximum fidelity regression. Passive permission
inspection reports a certification declaration as **unverified metadata**, never
permission to open. No document is launched, PDF action executed, or live
scanner, quarantine, policy, user preference or handoff path modified.

Run `PYTHONPATH=. python3 tests/pdf/digital-signature-corpus.py -v` with
`pypdf==6.21.3` and test-only `cryptography==46.0.4` installed and OpenSSL
available. GitHub Actions runs this test for changes to the corpus.
