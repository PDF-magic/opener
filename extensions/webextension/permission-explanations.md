# Explain every requested browser permission (opener-0588, §9.2)

PDF Magic Opener must give a specific, understandable explanation **before**
requesting each browser API or website-origin permission. The review-only
[`permission-explanations.json`](permission-explanations.json) records the
purpose, accessible permission explanation, data impact, consent requirement
and scanner-safety boundary for each separately identified potential API.

**This file does not request or grant permissions.** Only separately reviewed
manifest entries and opt-in runtime code can request access. Merely listing
a potential future API here does not authorize its use.

## Currently requested permissions

Required browser API permissions: **none**. Required host origins: **none**.
Optional host origins: **none**. The separately scoped opener-0583 change
may declare optional `downloads` access, which is **not granted at install**
and must be requested only after a deliberate opt-in user gesture.

## Explanation for each potential permission

| Permission | User-facing reason | What consent permits and what it does not |
| --- | --- | --- |
| `downloads` | Observe download events to identify PDFs for optional monitoring. | The browser may reveal download filenames, URLs and history. Explicit opt-in required; permission does not scan a PDF or authorize opening it. |
| `nativeMessaging` | Communicate with an authenticated, registered **local** companion app. | Only after host verification, a separately reviewed message protocol and direct user approval; never authority to bypass the scanner. |
| `notifications` | Show status notifications for a separately enabled feature. | May show visible desktop notices; avoid sensitive document details and preserve denial as an option. |
| `storage` | Persist settings you explicitly choose within the extension. | May retain those settings between sessions; do not store PDF bytes or paths by default or silently override preferences. |

These explain **possible** future capabilities, not four currently granted
permissions. The existing permission inventory and conditions remain in
[`permissions.md`](permissions.md). No current feature justifies `tabs`,
`history`, `<all_urls>`, arbitrary website origins or `file://` access.

## Enforcement and future consent UI

The existing `npm test` runs `tests/permission-explanations.test.mjs`
alongside the shared extension tests. The test checks source, Chromium
and Firefox manifests: every declared required **or optional** API permission
must have a distinct nonempty explanation, data-impact statement, opt-in
condition and scanner-safety limit. Undocumented host-origin requests fail.
Negative fixtures demonstrate that adding `tabs`, `history`, broad site
access or an incomplete explanation causes test failures.

When an actual permission-prompt UI is introduced in a separately reviewed
task, it **must display the relevant user-facing explanation before asking**
for browser approval. This file alone does not display a prompt. A denied
request must leave the feature disabled and never weaken mandatory scanning.

Browser permission grants are never malware-clean verdicts: mandatory ClamAV
freshness, file integrity, quarantine and user-selected destinations remain
unchanged.
