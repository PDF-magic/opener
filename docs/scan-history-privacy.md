# Optional scan history: sensitive-data exclusion (opener-0906)

Optional history must retain only bounded, canonical scan metadata. It must **not**
retain raw PDF bytes, extracted document text, embedded attachments, visited
pages or browser history, or the source URL of a document. These exclusions apply
regardless of how a PDF was obtained. There is no exception currently requiring
source URL retention.

The existing passive `ScanHistoryRecord` format permits only the exact fields
`schema_version`, `timestamp`, `status`, `source`, `filename` and `opened`.
`source` is a coarse enum (for example, `browser`), **not** a visited-page
list or a URL. `filename` is an optional, validated local basename; it is not
extracted document text. Unknown fields are rejected when deserializing.

The optional SQLite writer `store_scan_metadata` persists only its primary key,
scan timestamp, canonical final status, verified scanner-engine version (or null),
and actually enforced protection-profile identifier. It does not accept PDF
contents, attachment data, text, browser histories, filenames or source URLs.
It now refuses a pre-existing database table with additional or hidden columns
instead of silently writing through an unreviewed, potentially privacy-unsafe
schema. Such a failure is an optional storage error, never permission to open a
file or a replacement for scanner verification.

`tests/scan/history-privacy.py`, required by the existing `scanner-tests` CI
job, checks the JSON allowlist, rejects attempts to supply each prohibited
data category, inspects the actual persisted SQLite schema and rows using only
synthetic data, and rejects tables with unexpected or generated columns.

History collection is **not automatically enabled** by this change. Existing
scanner gates, the separate operational request audit, the clean-verdict cache,
and user preferences are unchanged. Future history features must preserve these
privacy boundaries and obtain explicit opt-in before collection.
