# Effective automatic interception status (opener-0797)

The **Browsers → Automatic PDF interception** settings area now gives a
read-only, labeled **Effective interception status: Inactive** summary
and an individual **Interception status: Inactive** value for each
eligible, installed browser. It remains visible when there are no eligible
browsers. These are effective deployment indicators, **not opt-in values**.
Changing an **Enable Automatic PDF Interception** preference never changes
the displayed status or starts a scan.

The browser toolbar popup independently shows **Automatic PDF interception →
Status: Inactive** in an accessible status region. This is informational
extension-owned HTML, with no script, background handlers or extra permissions.
The strict popup asset validator requires exactly one status region with
truthful inactive copy, preventing accidental removal or misleading status
during packaging.

**Why inactive?** The currently shipped extension has an inert background,
no verified native scan-before-render bridge and no proven interception
enforcement for any supported browser. The existing deployment capability
matrix also reports every browser as inactive. A saved checkbox, candidate
browser API or permission shape alone cannot establish active protection.
No scanned PDF may be opened on the strength of these status indicators.

**Future prerequisite:** A separately reviewed and authenticated runtime
integration would have to verify effective browser permission, current
PDF/navigation identity, synchronous before-render blocking, native scanner
trust and full scan completion before reporting active. This task does not
implement that runtime or speculate that opting in activates it.

Tests exercise both accessible surfaces, distinguish effective status
from saved opt-ins and verify unchanged extension privileges, scanner
fail-closed behavior and application customizations. CI runs the dedicated
Python test and existing packaged WebExtension popup suites.
