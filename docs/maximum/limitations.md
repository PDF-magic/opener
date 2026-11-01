# Limits of PDF sanitization

PDF Magic Opener's **Maximum** rasterized-copy sanitizer is a **planned,
optional building block**, not a protection mode available in the installed
application. The installed **Built-in** scan gate remains authoritative.
**Maximum is not selectable.** Do not assume every PDF you open is sanitized,
including PDFs that have passed a normal malware scan.

## What conversion does, and what it cannot prove

For a supported source, the optional converter renders pages as pixels and
rebuilds a *new, image-only PDF*. It does not reuse the original PDF catalog,
JavaScript, forms, attachments, hyperlinks, annotations, multimedia, metadata
or executable actions. The resulting file is a materially changed derivative,
**not a cleaned or repaired original**. See the
[conversion contract](sanitized-copy.md) and
[active-content removal](active-content-removal.md).

**Sanitization is not an antivirus scan, an exploit-proof sandbox, or a
guarantee of safety.** A raster page can still display deceptive instructions,
phishing links as visible text, misleading content or malicious imagery; a
PDF renderer or later viewer can also have vulnerabilities. Removing active
PDF structures reduces one attack surface but does not establish that either
the source or the generated PDF is malware-free.

A successful `SanitizedCopyOffer` has `permits_open=False` and
`needs_separate_scan=True`. A generated PDF must pass its **own fresh
ClamAV scan**, signature-freshness checks, file-integrity verification and
verified viewer handoff before opening. A prior clean verdict or cache entry
cannot be reused to authorize it. Quarantine is not removed, and no
sanitization failure may authorize opening. See
[generated-copy rescanning](generated-rescan.md).

## What users lose or may see differently

- **Text and accessibility:** characters become raster pixels, not
  selectable or searchable text. OCR is **not performed**, and semantic text,
  tags, reading order and accessibility information are not preserved.
- **Interactivity and content:** editable forms, form values, links,
  annotations and their appearance data, attachments, embedded media,
  scripts, layers and document metadata are not preserved. A form field or
  annotation that was visible in the source might not render as expected.
- **Signatures:** a generated copy does **not** retain the original
  cryptographic PDF signature or verification status; flattening can
  invalidate signatures. Keep the untouched original for signature review.
- **Visual fidelity:** fonts, tiny text, vector detail, color, transparency,
  page overlays and scanned images may appear different, blurry, omitted or
  clipped. Page dimensions, order and validated right-angle rotation are
  checked, but that does **not** guarantee every visible detail is faithful.

Review any generated copy against the original before relying on it for
critical reading, recordkeeping or evidence. Fidelity regressions test
specific synthetic documents, not every real-world PDF. See
[text readability](text-readability.md),
[annotation limitations](annotation-fidelity.md),
[signature fidelity](digital-signature-fidelity.md) and
[the separate OCR decision](ocr-restoration.md).

## Unsupported inputs and resource bounds

The optional converter **blocks instead of falling back to the original**
when it cannot safely produce and verify a visual-only copy. Examples include
encrypted/password-protected or malformed PDFs, signature-restricted documents,
XFA forms, PDF portfolios, optional-content layers, unsupported rich-media
annotations, cropped pages, unsupported stream filters and conversion or
structural-validation failures. Ordinary JavaScript or attachments may be
accepted as source material *only* when the full supported raster conversion
removes them; their presence does not constitute permission to open.

Current conversion limits include a **16 MiB** source, **16 pages**,
**2,048 pixels per page side**, **24 million total pixels**, a **32 MiB**
generated-PDF output and a **45-second** converter deadline. Processing also
has resource restrictions; hitting a cap, timeout, unavailable dependency or
inconclusive validation produces **no copy offer**, not a partially sanitized
PDF or a clean verdict. These are implementation limits, not assurances that
all documents below the limits are supported or safe. See
[blocked and unsupported cases](unsupported-sanitization.md) and
[output structure verification](sanitized-structure.md).

The optional module does not, by itself, save or open the copy, choose a PDF
viewer, relax scanner settings, remove macOS quarantine or change existing
customizations. Until a complete Maximum interface and its prerequisites are
implemented, **do not describe sanitization as an active, automatic PDF
protection**.
