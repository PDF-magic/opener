# Preferences application launch-time baseline (opener-1084)

This opt-in benchmark measures **the standalone macOS SwiftUI preferences app** from
spawning the real executable until its first window content triggers SwiftUI
`.onAppear`. It is not the separate PDF handler's launch time, PDF scanning,
file opening, antivirus startup time, guaranteed first pixel or fully usable
interactivity. The ready signal is compiled only in **Debug** builds and sent
through an inherited anonymous pipe; Release builds do not emit it.

On a disposable macOS test account, build the `PDFMagicOpener` scheme in Debug,
stage its app bundle using `scripts/package_application_helpers.py`, then run:

    python3 app_launch_benchmark.py --app /path/to/staged/PDFMagicOpener.app --samples 5

Provide only the known reviewed, built app bundle; the benchmark does not
install/register the app, open PDFs, request scanning, access user documents, or
send telemetry. Each attempt runs a copy in an isolated temporary directory
with a fresh `HOME`, `TMPDIR`, and `XDG_CONFIG_HOME`, then terminates its own
process. It discards one warmup; the JSON reports only median and nearest-rank
p90 in milliseconds and the sample count. Invalid, missing or timed-out
readiness events fail the entire run without partial measurements. The home
is synthetic, but this is **not OS-account isolation**: use a disposable
runner, not a personal account with production preferences.

CI runs a three-sample real GUI launch on the macOS hosted runner following the
existing staged-app first-launch smoke test. Runner numbers are useful as
baseline diagnostics only, not a latency target. Cold vs warm caches, code
signing, hardware, load, login state, first-run onboarding and runner image
can change timings. No fixed threshold is asserted. Scanner safety, quarantine,
PDF associations and user preference defaults are unchanged.
