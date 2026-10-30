# Explicit PDF scan request metadata contract (opener-0760)

An explicit **Scan This PDF** request needs a unique *attempt* identifier,
an initiating surface, a browser document location, an opaque identifier for
the selected PDF, and a verified direct user gesture. The passive
`describeExplicitPdfScanRequest(details)` helper defines and validates a
versioned, exact-key metadata record. It does **not** send a request.

| Required key | Meaning |
| --- | --- |
| `version` | Schema version `1`, for explicit compatibility checks |
| `requestId` | Per-attempt correlation/idempotency ID, 1–80 URL-safe ASCII characters |
| `source` | Exactly `toolbar`, `pdf-link`, or `embedded-pdf` |
| `tabId` | Nonnegative safe-integer ID supplied by a trusted browser API |
| `frameId` | Nonnegative safe-integer frame ID; toolbar requires `0` |
| `selectionId` | Opaque, separately minted ID for the specific current PDF selection, **not** a URL, path or content |
| `userInitiated` | Exactly `true`, supplied only for the directly invoked user action |

Both IDs are bounded to `[A-Za-z0-9_-]`; they must be distinct. Invalid
records, unknown fields, inherited properties, accessors, symbols and hostile
proxies fail closed with `null`. There is no property getter execution.
Validated results are frozen, detached metadata with
`status: "metadata-only"`, `scanVerified: false`,
`authorizesScan: false` and `authorizesOpen: false`.

**These fields are necessary but not sufficient.** Browser tab/frame and
user-action flags supplied by an arbitrary caller are not proof of identity,
consent or eligibility. A future, trusted browser adapter must independently
attest the actual direct click, authenticate tab/frame/selection provenance,
reject stale or reused selection IDs, recheck PDF eligibility and access
permissions, and bind the request ID to one live action. The native scan
coordinator—not this browser metadata descriptor—must safely resolve and
revalidate the selected PDF's canonical **local file identity**, stability,
permission, freshness, integrity, quarantine and mandatory ClamAV
scan-before-open policy. Native results and the user's selected application
continue to govern any later opening.

Never put a page URL, local file path, bytes, PDF MIME hint, browser-supplied
clean verdict, authorization flag, or user preferences in this descriptor.
Never forward this metadata directly as a native scan command. The current
extension background remains inactive and has no native scan permission;
this task does not connect a scanner or enable a context menu.

`tests/explicit-pdf-scan-request.test.mjs` contains eight Node regression
cases for all required fields, surface/frame validity, spoofing, malformed
metadata, privacy and no changes to scanner/browser permissions. The shared
WebExtensions `npm test` glob includes the suite under GitHub's existing
`scanner-tests` CI without adding a redundant workflow.
