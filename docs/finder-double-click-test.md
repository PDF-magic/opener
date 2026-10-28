# Test Finder double-click PDF opening

This checklist covers the real Finder gesture on a macOS desktop. The automated
CI companion (\`test-finder-double-click.py\`) tests the corresponding
Launch Services **open-documents** delivery using a temporary app and
\`open -a\`. CI deliberately **does not** change the system's default PDF
handler or simulate clicks through Accessibility permissions. It is not a
substitute for the literal manual double-click check.

## Manual verification on an installed macOS system

1. Note the current default PDF handler with
   \`swift identify-pdf-handler.swift\`, and note the default web browser in
   System Settings. Do not change either setting just to run the automated test.
2. If PDF Magic Opener is not already the default PDF handler, explicitly
   configure it through Finder **Get Info → Open with → PDF Magic Opener →
   Change All** only if you wish to change your own default. Record the
   previous handler so you can restore it afterward.
3. Create or use a harmless local PDF with spaces or Unicode in its filename.
   Double-click that file **in Finder**. Confirm macOS hands it to PDF Magic
   Opener, the scanning window displays the requested filename, and the
   destination browser does not open before the scan gate permits it.
4. Confirm a clean approved file opens in the user's chosen post-scan
   application; repeating the double-click during a scan must not dispatch
   a duplicate scan. Test the **Cancel** control and a blocked scan on a
   safe synthetic fixture: neither should release quarantine or open a browser.
5. Confirm the macOS default **web browser** was not changed. If you
   explicitly changed the default PDF handler for this manual test, restore
   the previously recorded handler using Finder Get Info.
6. Record the macOS version, selected PDF handler, expected target app,
   observed scan/launch behavior, and PASS/FAIL result. Do not include
   document contents, private paths, logs containing secrets, or credentials.

The automated test uses a disposable signed app whose only scan subprocess
is a local receipt-writing stub. The real application's scan-gate logic,
file-integrity checks, quarantine policy, and user preferences are unmodified.
