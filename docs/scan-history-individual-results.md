# Inspect an individual scan result (opener-0913)

After explicitly clicking **Show recent scan results** in **Privacy and Logs**,
users may select any validated result to inspect that single entry. The
keyboard/VoiceOver-accessible detail sheet presents only the scan time,
canonical final status, scanner engine version (or Unknown), and effective
protection profile. **File opening: Not verified** is always shown because
the metadata store contains no verified opening outcome.

The detail sheet receives the already validated, in-memory record from the
opener-0912 list. No additional SQLite query, PDF read, network request,
scanner action, file launch, logging or preference change occurs during
inspection. Refreshing the list discards the previous selection; Done closes
the sheet. A historical clean status never bypasses current malware,
integrity, signature freshness, quarantine, or opening gates.

No PDF contents, extracted text, embedded attachments, browsing history,
source URLs, document names, or raw scanner diagnostics are exposed.
Automatic history collection remains off; opt-in, retention, exporting and
deleting history are not introduced by this task. Required CI covers the
explicit selection, validated data flow, privacy boundaries and native Xcode
target, whose macOS build compiles the new view.
