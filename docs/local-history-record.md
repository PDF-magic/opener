# Optional local scan history: record format (v1)

\`scan_history_record.py\` defines a **passive, immutable metadata contract** for
one scan request. This task does not collect, save, display, transmit, prune,
or enable local history. History remains optional and off until a later,
explicitly authorized integration adds opt-in controls and secure local storage.
The existing anonymous request-origin diagnostic log is separate and is not
migrated into this format.

The six exact, allowlisted JSON object fields are:

| Field | Type | Meaning |
| --- | --- | --- |
| \`schema_version\` | integer \`1\` | Reject other versions rather than silently misinterpreting them. |
| \`timestamp\` | nonnegative integer | UTC Unix seconds at the trusted scan event. |
| \`status\` | string | One of the ten \`scan_results.ScanResultStatus\` terminal values. |
| \`source\` | string | \`finder\`, \`browser\`, \`desktop-application\`, \`command-line\`, or \`unknown\`. |
| \`filename\` | string or null | Optional local document **basename** only; null by default. |
| \`opened\` | boolean or null | Verified file-open outcome; null means unverified, **not opened** cannot be inferred. |

Example (illustrative only; never emitted automatically):

\`\`\`json
{
  "schema_version": 1,
  "timestamp": 1793448000,
  "status": "scanFailed",
  "source": "finder",
  "filename": null,
  "opened": false
}
\`\`\`

Only a trusted, request-correlated native coordinator may supply authoritative
scan outcomes and opening evidence. The \`clean\` status alone is **never** proof
that opening succeeded, nor is a history record permission to bypass quarantine,
verification, scanner failures, or the normal opening gate.

Full paths, URLs, raw scanner messages, detection output, document contents,
user identifiers, and unknown fields are excluded. Filenames are optional and
reject path separators, control/format characters, empty names, and oversized
basenames; consumers must still use privacy-safe presentation. Invalid versions,
statuses, sources, types, or payload shapes are rejected. The format's
validation is not a substitute for authenticated provenance checks.

\`tests/scan/history-record.py\` exercises this contract in the required Linux
CI \`scanner-tests\` job; it does not touch live scans or user settings.
