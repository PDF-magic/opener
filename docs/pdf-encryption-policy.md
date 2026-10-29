# Encrypted and password-protected PDF inspection (opener-0426)

The optional, read-only `pdf_encryption_policy.inspect_pdf_encryption(bytes)`
checks the encryption state reported by the maintained strict pypdf parser.
It accepts only bounded immutable PDF bytes, not a path, password, or password
callback. It does not try a user password, an owner password, or an empty
password, and it does not decrypt any PDF object.

**Policy:** every encrypted PDF is treated as uninspectable and maps to the
existing `ENCRYPTED_RESPONSE` (`ScanResultStatus.encrypted`), which blocks
opening, clean-cache publication, fallback and manual override and preserves
quarantine. This includes PDFs with a nonempty user password, a separate
owner password, and PDFs technically decryptable with a blank user password.
Encryption alone cannot reliably reveal which credentials would work, so the
inspector does not assert that a password is required. No prompt is offered.

A parsed, unencrypted PDF returns `NOT_ENCRYPTED` as narrow evidence, **not**
a clean scan verdict or permission to open. Missing dependencies, malformed,
truncated, oversized, and uninspectable inputs fail closed with a generic,
path-free `PDFEncryptionInspectionError` and the preexisting
`INCOMPLETE_RESPONSE`. A literal `/Encrypt` string in document metadata is
not proof of PDF encryption; the inspector trusts strict parsed state.

The preexisting `pdf_structure_parser.parse_pdf_structure` already rejects
encrypted PDFs before reading protected page trees, and continues doing so.
This narrowly scoped feature does not change that parser (which is also being
developed by opener-0413), add a password prompt, activate Enhanced or Maximum,
or change the installed Built-in ClamAV gate, file integrity, signature
freshness, quarantine, user settings, or opening decisions. The deployed gate
continues to use `--alert-encrypted=yes`; actual integration of any new
optional parsing stages requires separately reviewed isolation and budgets.

Run `python3 test-pdf-encryption-policy.py -v` after installing the reviewed
`requirements-enhanced-pdf.txt` pin. CI runs this regression after its
existing PDF structure tests.
