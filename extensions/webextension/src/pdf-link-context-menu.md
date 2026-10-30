# Supported PDF-link context-menu action (opener-0758)

The exported describePdfLinkContextMenu(details) is a passive **Scan This PDF**
context-menu descriptor builder, not an installed menu item.

A future, separately authorized browser adapter may supply authenticated
contextMenus.onShown-style data with its contexts array and linkUrl. Only the
link context and bounded HTTP(S) URLs with a final .pdf path are supported.
Queries, fragments and safe percent-encoded path characters are handled by
the existing shared PDF-candidate detector. Unsupported schemes, credentials,
query-only hints, malformed paths, accessors and inherited data fail closed.

Eligible links receive an immutable, URL-free action descriptor with the
title "Scan This PDF", link-only context and enabled:false,
authorizesScan:false and authorizesOpen:false. Other links return null.
No browser URL, cookie, filename, or scan verdict is returned.

**Prerequisites for a live action:** the installed WebExtension currently has
no contextMenus permission, and the packaged background worker is intentionally
inert. A separately permission-authorized integration must register a menu,
dynamically restrict it to eligible link contexts, and verify an authenticated
native scanner bridge and explicit user consent before enabling any click.
A generic all-links enabled item would violate this security boundary.

No permissions, background listeners, native messages, file downloads,
scanner policies, ClamAV freshness/integrity gates, quarantine behavior,
app-opening decisions or saved user choices are changed. Tests verify
eligible/invalid links, contexts, immutable disabled output, privacy, and
unchanged security policy. The suite runs under npm test and separately in
the required scanner-tests GitHub Actions job.
