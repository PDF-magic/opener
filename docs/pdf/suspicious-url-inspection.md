# Suspicious embedded PDF URL inspection (opener-0292)

The **inactive** Enhanced-stage inspector in `pdf_suspicious_urls.py` reviews
embedded URL-bearing PDF objects without opening, downloading, resolving, or
executing any destination. Call `inspect_pdf_suspicious_urls(pdf_bytes)` on
immutable in-memory bytes. This is **not** part of the installed Built-in
ClamAV scan gate and **never authorizes a document to open**.

The strict `pypdf==5.9.0` object walk covers catalog URI base dictionaries,
URI actions (including page links, annotation actions, action chains, and
unreferenced indirect objects), URL file specifications (`/FS /URL`), and URL
strings in form submission and import actions. The form-action semantics and
other external-launch behavior are handled by separate checklist tasks; this
stage classifies only URLs. It does not parse visible page text as URLs.

The immutable result exposes only URL and suspicious-URL counts, sorted
category identifiers, and `permits_open=False`. Categories cover HTTP
without TLS, non-web schemes, relative references, credentials embedded in
addresses, non-global IP literals, numeric/obfuscated hosts, localhost or
internal names, onion hosts, internationalized hosts, percent-encoded hosts,
encoded control characters, and nonstandard ports. These are **review
indicators**, not proof that a destination is malicious. Neither addresses,
paths, credentials, document content, nor query strings are returned or logged.

The input ceiling is 16 MiB, with limits of 4,096 indirect objects,
65,536 visited graph nodes, 1,024 pages, 512 URLs, and 2,048 characters per
URL. Missing parser support, encrypted or malformed PDFs, unsupported object
streams, broken references, invalid string encodings, control characters,
and exhausted budgets all raise the same path-free inspection error.
A clean classification is not a ClamAV result or permission to launch.

CI runs `test-pdf-suspicious-urls.py` with generated harmless PDFs; it checks
suspicious and benign classifications, orphan and chained actions, malformed
inputs, limits, no execution/network access, no leakage, and isolation from
scanner preferences. The installed scanner, quarantine retention, signature
freshness check, clean cache, and user-customized application choices remain
unchanged. A separately reviewed integration of all Enhanced requirements is
necessary before any Enhanced protection profile can be enabled.
