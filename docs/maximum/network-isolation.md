# Network-disabled Maximum analysis worker (opener-0308)

A future **Maximum protection** inspection can invoke
`maximum_network_isolation.run_maximum_offline_worker((absolute_program, ...))`
to execute a *trusted, separately implemented analysis subprocess* with
macOS Seatbelt denying all `network*` operations, including both outbound
connections and inbound listening on loopback. The fixed, non-user-editable
profile is passed directly to `/usr/bin/sandbox-exec` before the worker starts.
The wrapper launches without a shell, closes inherited file descriptors,
provides a minimal fixed environment, discards potentially sensitive output,
and bounds the process invocation time. If macOS or the enforcement binary is
unavailable, sandbox initialization fails, execution times out or the worker
exits nonzero, the wrapper **fails closed**. It never falls back to launching
the worker without network controls.

For this task, only *network permission* is reduced. Other worker sandbox
capabilities (including file-system isolation and full process lifecycle
limits) need independently reviewed Maximum controls. `sandbox-exec` is a
deprecated Apple mechanism; macOS integration tests demonstrate real enforcement
on supported runners. A production replacement must have equivalent live
network-denial tests and must not use a permissive fallback.

This module is intentionally **not** wired into `scan-and-open.py` or the
installed application: Maximum is a planned, non-selectable profile and
its safe isolated inspection orchestrator does not yet exist. The Built-in
ClamAV scan and its independent signature updater retain their required
behavior, as do selected post-scan applications, user configuration, cache,
quarantine, and handoff protections. The fixed `OfflineWorkerCompletion` only
proves that a sandboxed subprocess returned zero; `authorizes_open` is always
false. It is never a malware-clean, fully analyzed, or admission decision.

`test-maximum-network-isolation.py` checks fixed policy and spawn arguments,
unavailable-sandbox failure, invalid command rejection, timeouts, nonzero exit,
and inalterable non-clean evidence on Linux. On macOS it additionally runs real
child processes that attempt to connect to a known live loopback TCP listener
and bind a listener; both attempts must be blocked while ordinary local
non-network work succeeds. The dedicated workflow runs these checks on PRs
and pushes to `main`. No Internet destination is used.

## Sanitizer network confinement (opener-0858)

The separate optional CoreGraphics sanitizer now uses a mandatory kernel network
restriction before receiving PDF bytes. On macOS, its existing bounded child
supervisor runs the converter through `/usr/bin/sandbox-exec` and the fixed
Seatbelt `(deny network*)` policy. On Linux, its existing memory-limit launcher
installs the shared seccomp network-denial filter before `exec`. Both deny
inbound listeners and outbound connections, including loopback, without
changing the required memory, time, output or process-group limits.

Missing or failed enforcement stops sanitization with no generated-copy offer;
there is no unsandboxed retry. The preexisting verification and independent
rescan of any generated copy remain mandatory. The installed ClamAV scanner,
its networked signature updater, quarantine and user customizations are
unchanged. `tests/maximum/sanitizer-network-denial.py` exercises real kernel
network denial on Linux and macOS alongside positive offline processing.
