# Terminate Maximum workers that exceed process limits (opener-0312)

The opt-in Maximum worker from [opener-0306](maximum-isolated-analysis.md)
now uses `maximum_process_termination.run_limited_worker()` instead of
`subprocess.run()`. Only the trusted caller constructs an inspector command
and environment; the PDF only supplies bounded bytes via the child stdin.

The supervisor starts one new POSIX **session/process group** for each worker,
keeps a monotonic **30-second maximum wall deadline**, and sends
`SIGKILL` to that entire group when processing exceeds the deadline, writes
stall, output exceeds **4 KiB**, or the process exits abnormally. It also
cleans up the group after *successful* completion so child-created processes
cannot intentionally remain behind, then reaps the direct child.
Uninspectable or missing results continue to block; the response contains
only fixed path-free errors, never the PDF contents or child diagnostics.

Unlike an unbounded `subprocess.run(..., stdout=PIPE)`, the supervisor
reads stdout in fixed chunks and refuses excess data **before** buffering it.
The companion **opener-0311 output-size hardening** additionally constrains
each nonblocking read to the *remaining* room within the cumulative 4,096-byte
budget plus one detection byte. A 4,096-byte response is accepted, the very
next byte fails closed, and multiple smaller writes cannot evade the ceiling.
Linux and macOS tests explicitly verify those exact boundaries.

Stdin writes are nonblocking and share the same deadline, preventing a hung
parser from indefinitely blocking the parent on a full pipe. All operations
use Python's isolated interpreter, closed extra file descriptors, no shell
and a minimal environment as before.

This supplements, without replacing, the child-side CPU and Linux memory
ceilings from opener-0306. The dedicated process group cannot constrain a
malicious process that explicitly creates a separate session; OS sandbox
prohibitions on child execution and privilege boundaries remain independent
prerequisites. Memory limit implementation is owned by [PR #206](https://github.com/PDF-magic/opener/pull/206)
(opener-0309), and nothing here changes its implementation.

The installed Built-in scanner, quarantine, cache, file integrity, browser
and saved preferences remain untouched. Maximum stays non-selectable;
completion of this worker alone never authorizes a PDF to open.

`test-maximum-process-termination.py` exercises **real subprocesses** for
timeouts, group termination with descendants, output floods, blocked stdin,
normal cleanup, abnormal exits and invariant validation on macOS and Linux.
The original isolated-analysis regression suite runs alongside it.
