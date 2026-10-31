# Repair Installation action (opener-0965)

From a **complete, trusted PDF Magic Opener source checkout**, double-click
**Repair Installation.command** in Finder or run:
```sh
./Repair\ Installation.command
```
This is an explicit, **interactive** maintenance action, not an automatic
startup repair. It refuses root/sudo, symlinked or missing installation
sources, arguments, absent controlling terminals, redirected input and
anything other than the literal `REPAIR` confirmation. The action itself
does not use sudo, contact a download URL, install Homebrew, or change files
before authorization. It then executes the *existing* installer from the
same source checkout, not a dynamically downloaded script or arbitrary path.

**Scope:** the established installer can restore managed PDF opener
application helpers, reconcile its verified registration, and update ClamAV
signature definitions using the installed update workflow. Existing
browser selection, FreshClam proxy/mirror customizations, LaunchAgent
preferences and unrelated Finder Quick Actions must not be overwritten.
The installer's protected backup, staging, migration, signature freshness
and executable verification gates remain authoritative. The action is not
a scanner bypass or a promise that corrupted malware databases are healthy.

If ClamAV already exists at one of the supported locations, its package
is **not reinstalled**; the original installer contains that check. If
ClamAV is missing, the original installer separately requires terminal
consent to the Homebrew command. Unsupported ClamAV versions still fail
the active scanner gate and are not silently replaced, downgraded, or
accepted as healthy. There is no privileged or unattended repair path.

A refused or failed repair must not be reported as successful. See the
existing installation prerequisite reporting for missing Xcode tools,
Homebrew, Finder Quick Action or ClamAV. If the original source checkout
is not available, obtain a trusted complete checkout rather than copying
individual installer files from an unknown location. Do not run this
action from inside an already installed app bundle: installer source files
are intentionally not packaged there.

The existing migration and rollback behavior governs failed operations;
this action neither implements a parallel recovery mechanism nor resets
user-selected PDF default associations.
