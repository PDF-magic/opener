# Duplicate scan notification suppression (opener-0897)

Optional macOS scan notifications are deduplicated by the canonical document
path and the **verified result category** (success, blocked, failed scan or
confirmed malware). The native handler uses an opaque SHA-256 identifier rather
than a filename, path, diagnostic, browser choice, or random notification ID.
A second attempt for the same document/outcome within 30 seconds is suppressed
if a matching notice was recently delivered, remains pending in Notification
Center, or is already reserved by this helper process. Different documents and
different outcomes keep distinct identifiers; a later deliberate scan can
notify again after the window. The in-process reservation is transient.

This affects **only optional notification delivery**. It neither stores paths
in preferences nor changes the opt-in settings, macOS permission handling,
scan scheduling, cancellation, native fail-closed scan gate, mandatory blocking
alerts, signature checks, quarantine, or chosen document application.
Notification delivery remains best effort, never a clean-scan attestation.

The scanner CI contract checks native wiring, path privacy and gating.
A compiled Swift regression checks pending/recent/expired notices, distinct
documents and outcomes, in-process reservations, and cancellation behavior.
Both run in the required CI workflows.
