# Maximum worker output-size limits — opener-0311

The isolated Maximum PDF worker from opener-0306 has a 4,096-byte numeric JSON response contract. Its original parent used unbounded subprocess stdout capture and rejected large output only after the entire response was in memory. This task enforces that ceiling **while reading the subprocess pipe**, preventing unlimited output from exhausting parent memory.

The bounded parent transport multiplexes worker stdin and stdout on nonblocking file descriptors. It reads at most 4,097 bytes total and immediately rejects output over 4,096 bytes. On output overflow, startup error, pipe failure, or wall timeout, it kills and reaps the child process group and reports a fixed path-free failure. Stderr remains discarded; no PDF content or worker diagnostics enter an error or log. The transport preserves the 16 MiB input ceiling, 30-second deadline, isolated interpreter, minimal environment, and closed inherited descriptors.

The existing isolated analysis response validation still checks the exact protocol, inspector name, numeric metrics, and non-authorizing flag. Success from the child is **not** proof a PDF is safe to open. The active ClamAV scan gate, file handoff, quarantine, and user preferences are unchanged. Maximum remains non-selectable. CPU, memory, filesystem, and network restrictions are separate checklist tasks.

This change builds on the isolated process from opener-0306. Tests launch real subprocesses and check the exact limit, first excessive byte, continuously producing workers, full input/output pipes, deadlines, invalid inputs and fail-closed error messages. Dedicated Linux and macOS workflows run the new regressions alongside the upstream isolated-worker and existing repository checks.
