# Firefox downloaded PDF opening with macOS quarantine (opener-0823)

The existing real Firefox browser download smoke test proves that Firefox saves
the fixture's PDF attachment and octet-stream PDF bytes. It previously stopped
before PDF Magic's native safe-open path. The new macOS workflow uses those
**exact files downloaded by Firefox** in an isolated temporary browser profile
and exercises the production `scan_and_open` decision gates via a test helper.

For each PDF downloaded through a real WebDriver link click, the test:

1. Confirms the expected regular file, original PDF bytes and filename.
2. Reads the `com.apple.quarantine` attribute if Firefox supplied one. If the
   automation environment did not tag the file, it seeds a deterministic test
   attribute **and identifies it as seeded**, rather than claiming Firefox did.
3. Runs the real scanner's clean and cached-clean logic, with a stand-in ClamAV
   process. It confirms the intended `org.mozilla.firefox` destination is
   checked before the simulated safe launch of the same downloaded path.
4. Repeats with malware, a missing target app, and a scanner timeout. None may
   reach any launcher. After every case, exact file bytes and the quarantine
   attribute value must remain unchanged.

There is **no real app open** in CI: scanner subprocesses, selected target
verification, and the GUI launch are deliberately mocked. This tests that
opening *would* be authorized only after a successful gate, without introducing
an unsafe bypass or launching a file into the runner's GUI. It does not claim
Firefox's actual quarantine tagging if the test had to seed an attribute,
or prove that a real ClamAV installation or Launch Services will succeed.

This suite runs on `macos-latest` with actual Firefox and geckodriver using
loopback-only downloads; a deterministic self-test also runs in the existing
WebExtension `npm test` suite on other runners. Only disposable profiles,
mocked settings, and temporary scan caches are used. Neither the installed
scanner, quarantine behavior, real user preferences, nor browser permissions
are modified.
