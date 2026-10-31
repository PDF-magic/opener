# Existing signature update-agent migration (opener-0942)

The installer validates and migrates the existing per-user LaunchAgent after
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
