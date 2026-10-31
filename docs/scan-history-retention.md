# Configurable optional local scan history retention (opener-0915)

The optional Scan History preferences page (itself default-hidden until
the separate history opt-in integration enables it) offers a retention picker
for **7, 30, 90 or 365 days**. The default is **30 days**, even before a
choice is saved. The selection persists as only
\`{"retention_days":30}\` in a user-owned private \`scan-history/retention.json\`
file; choosing a period does not create the SQLite database or begin history
collection.

Expired optional scan-history rows are deleted automatically:
- Whenever the trusted metadata writer appends a scan result, in that same
  SQLite transaction as the append;
- Whenever the already-enabled Scan History page becomes visible;
- Before a user explicitly displays recent results; and
- Immediately after a new retention period is saved.

Expiration compares UTC epoch seconds strictly earlier than the current
time minus selected days. The cutoff row itself is retained. Failures
surface as unavailable storage/retention, never as a clean scan or permission
to open a document. The existing 90-day clean-scan cache, operational logs,
PDF bytes, attachments, browsing history, and source URLs are untouched.
Clear History remains a separate, explicitly confirmed action: it removes
the SQLite artifacts, **not** the saved retention selection.

Native and Python implementations share a small allowlisted JSON format and
enforce private directory/file ownership, symlink refusal and exact history
table schema. Neither a missing history store nor merely loading settings
creates one. Future app or scanner integrations must still require explicit
consent before collecting optional history. Expiration is event-driven at
history access/recording points; this task does not install a background
system daemon or alter launch, malware, integrity, signature or quarantine
enforcement.
