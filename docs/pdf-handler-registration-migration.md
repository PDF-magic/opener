# PDF handler registration migration (opener-0948)

The legacy `Open PDFs in Brave.app` and current `PDF Magic Opener.app` share
the established `local.studio.brave-pdf-opener` Launch Services bundle ID.
A rename can leave a stale Launch Services registration at the old location.

After verifying and installing the staged scan-handler application, the installer
uses macOS NSWorkspace to enumerate registrations for **that ID alone**.
It registers the current bundle before withdrawing an absent, exactly named
legacy alias, then requires exactly one current registration. Repeat installs
never unregister the working application.

An existing old bundle, any unknown registration path (even if absent), unsafe
links, invalid inventory, or a failed registration operation blocks installation
rather than withdrawing another app. The helper does not delete bundles,
reset Launch Services globally, alter PDF default preferences, change the
post-scan browser selection, or modify scanner policy. The existing default
restoration prompt remains opt-in and occurs after reconciliation.

Tests cover fresh, repeated, successful and conflicting migration scenarios
without invoking any real system registration commands.
