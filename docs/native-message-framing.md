# Native messaging byte framing (opener-0617)

The pure Python transport helper `native_message_framing.py` exposes
`read_native_frame(binary_input)` and `write_native_frame(binary_output, body)`
for browser native messaging. Each message is:

```text
[4-byte unsigned little-endian body length][exactly that many body bytes]
```

The body must contain **1–16,384 bytes**. A clean EOF before the first prefix
byte returns `None`; a partial prefix, truncated body, zero or oversized
length, invalid binary stream, or stalled write raises `InvalidNativeFrame`
with a generic, path-free message. Short reads and short writes are retried
without assuming that one I/O operation processes the requested byte count.
Frames are consumed one at a time so multiple messages can share a stream.

**No JSON validation or privileges are implied by transport success.** The
future versioned JSON envelope validator (opener-0616, PR #404) must explicitly
validate the returned bytes. Frame bodies can contain arbitrary bytes; they do
not carry scan verdicts or PDF-opening authorization. This helper does not
access PDF files, run ClamAV, change quarantine or preferences, request browser
permissions, or install or register a native messaging host.

The separately proposed Swift host process (opener-0615, PR #406) already
provides its own Swift-specific frame loop. This Python transport supports
independent Python-based codecs and test clients; it **does not replace or
activate** the Swift host. Connecting either transport to the scanner requires
separate sender verification, permission review, and mandatory existing
scanner-integrity and user-selected application safeguards.

Run `python3 test-native-message-framing.py -v` to exercise the portable
framing regression suite. The existing `scanner-tests` CI job runs this
suite on every PR.
