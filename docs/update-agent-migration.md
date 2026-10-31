# Existing signature update-agent migration (opener-0942)

The installer preserves the exclusive-create fresh-install agent provisioning and
validates/migrates the existing per-user LaunchAgent after
verifying the staged application, but before stopping or bootstrapping agents.

* Fresh installs create the established trusted four-hour FreshClam agent.
* Compatible agents retain a custom interval or calendar schedule,
  RunAtLoad/Disabled preferences, and safe log filenames in the established
  Studio log directory. Unchanged configurations are not rewritten.
* Unexpected commands, unrecognized launchd properties, malformed plists,
  symlinked agents/log files, unsafe permissions, and changed files abort
  migration without overwriting the original file or bootstrapping the agent.
* The scanner, signature database, quarantine and PDF-opening decisions
  are untouched. Separate signature-config migrations are out of scope.

CI uses only synthetic user home directories and never reads real LaunchAgents.

## Single active updater (opener-0947)

After the plist migration succeeds, the installer checks the established
`gui/<user ID>/local.studio.pdf-malware-signatures` service, boots out that
specific loaded service **by label** (even if launchd registered it from an
older plist path), and bootstraps the validated canonical plist exactly once.
It verifies registration afterward. Failed stop, lingering service, failed
bootstrap or failed verification abort installation instead of risking a
duplicate or reporting success. No other service labels or user LaunchAgent
files are inspected, stopped, or modified. Existing schedules, Disabled
settings, logs, signature data and scanner safety gates are unchanged.

The existing required scanner-tests CI step executes synthetic launchctl
regressions for fresh installation, repeated installation, already-loaded
services, and failure handling without invoking the system's launchctl.
