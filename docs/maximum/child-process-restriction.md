# Maximum renderer child-process restriction (opener-0489)

The optional Maximum PDF renderer receives untrusted document bytes. The parent
intentionally starts one trusted worker per requested page, with a batch limit
of four pages. This task restricts what that worker can launch after it starts;
it does not remove the parent's bounded worker-launch capability.

## macOS

The renderer uses a fixed Seatbelt profile that retains the existing
`(deny network*)` rule and adds `(deny process-fork)`. The policy is passed
directly to `/usr/bin/sandbox-exec`; no shell, user-controlled profile, or
unsandboxed retry is introduced. If the sandbox launcher is unavailable, the
renderer fails closed.

## Linux

Before the worker reads PDF bytes or imports PyMuPDF, it installs an additional
libseccomp filter under `PR_SET_NO_NEW_PRIVS`. It denies `fork` and `vfork`,
returns `ENOSYS` for `clone3` so runtimes may safely fall back, and denies
`clone` calls whose flags do not include `CLONE_THREAD`. This blocks process
creation through the common syscall paths while preserving ordinary thread
creation. Every required syscall rule and the kernel filter must install
successfully; missing support produces a fixed, path-free failure rather than
an unconfined render.

The existing network-denial filter remains a separate, mandatory layer.
The child-process restriction applies only to the optional renderer worker and
does not alter the installed ClamAV scanner, signature updates, quarantine,
clean-cache behavior, target application, or user preferences.

## Verification

`test-maximum-child-process-restriction.py` runs actual Linux seccomp and
macOS Seatbelt probes that attempt `fork`, `subprocess.Popen`, and
`os.posix_spawn`, while also verifying thread creation remains possible.
It checks the renderer launch profile and confirms the Linux worker installs
the filter before reading PDF data or importing the rendering engine.
The dedicated `.github/workflows/maximum-child-process-restriction.yml`
workflow runs on Linux and macOS. Rendering remains optional evidence only;
it never authorizes opening, and the separate filesystem-sandbox prerequisite
is unchanged.
