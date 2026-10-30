# Open PDF Magic Preferences action — opener-0577

The extension toolbar's static `preferences.html` popup provides one explicit
**Open PDF Magic Preferences** link. A click requests the fixed macOS URL
`pdfmagicopener://preferences`, which the **installed native preferences app**
registers as a URL handler. The app accepts exactly that URL and raises its
existing preferences window; it does not read URL arguments, open a PDF, start
a scanner, alter a default PDF handler, or change saved preferences.

This is a local, user-initiated application launch, **not** a PDF safety
verdict or a working browser-to-scanner integration. The popup explicitly
states browser PDF scanning and opening are inactive. When the macOS app is
missing, no application launch is guaranteed. Some browsers prompt before
opening an external application; canceling the prompt has no side effects.

No JavaScript runs in the popup. There is no background listener, tab
injection, remote URL, content script, native messaging or new browser
permissions. `scripts/build.mjs` and `scripts/build-firefox.mjs` package
only the validated local HTML; Safari embeds the identical file as a resource
of the existing sandboxed .appex.

Run `npm run build && node scripts/build-firefox.mjs && npm test` for shared
and Firefox packaging tests, and
`python3 test-browser-preferences-deep-link.py -v` for native metadata
and closed/unknown-URL handling contract. CI checks the built macOS app's
registered scheme and Safari .appex copy without launching either.
