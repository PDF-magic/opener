# Explicit dependency-installation consent (opener-0960)

The PDF Magic Opener installer is a **per-user installer**, not a privileged
system installer. Invoke `bash install-allow-and-open.sh` as an ordinary user.
It refuses to run with root privileges, including through `sudo`, before
touching application bundles, LaunchAgents, Finder services, or preferences.

ClamAV remains an externally managed dependency (see
[the Homebrew decision](clamav-homebrew-decision.md)). The existing supported
ClamAV executable paths are checked first; installations at those paths do
not need Homebrew. When ClamAV is missing, the installer displays the exact
proposed `brew install clamav` command and warns that Homebrew can download
packages, change files in its own prefix, or request administrator access.
Only typing the literal `INSTALL` followed by Return at the **controlling
terminal** authorizes that command. Homebrew automatic formula updates are
disabled for this invocation. Other responses, inaccessible/non-TTY consoles,
or failed Homebrew commands stop installation without silently continuing.

Users may instead decline, install ClamAV separately (such as by explicitly
running `brew install clamav`), and rerun the PDF Magic installer. There is
no environment bypass, automated `sudo`, unattended Homebrew installation,
Homebrew bootstrap, package upgrade, or privilege escalation performed by
this installer. Package-manager authorization does not permit opening a PDF:
the existing scanner executable/version, signatures, file integrity, malware
verdict, cache, quarantine, and selected-application checks still apply.

The existing migration journal is a user-owned local installation marker; it
does not confer scan authorization or trigger privileged work. This task
does not change it, or the user-owned FreshClam database and configuration,
Quick Action, LaunchAgent, or post-scan browser preference. Homebrew discovery
(opener-0954) and packaging alternatives (opener-0958) remain separate tasks.
