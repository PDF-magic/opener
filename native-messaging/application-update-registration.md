# Native host registration after an application update (opener-0650)

This checklist task **tests existing opt-in registrations** after a simulated application update. It does not install or update an app, auto-register browsers, change extension permissions, launch the scanner, or migrate any user's registration.

## Tested update paths

- **In-place executable update:** Starting from a genuine per-user registration in an isolated home directory, atomically replace the host executable with a different executable at the *same absolute path*. Verify that the new bytes execute at the registered path; the browser-visible `org.pdfmagic.opener.json` retains its exact name, absolute path and approved extension allowlist; a repeat registration is a no-op, with unchanged manifest bytes/inode and unaffected unrelated user files.
- **Relocated application or changed host path:** Move the executable to a different absolute path after registration. The old manifest still points to the **missing** old path and therefore does not establish working host discovery. Chrome and Firefox registration refuse to overwrite it with a different path or extension identity. The existing manifest and unrelated settings remain intact; an explicitly reviewed migration is required instead of silently changing a user's authorization.
- **Browser coverage:** The portable Python test uses the existing macOS Chrome registrar. The Node test uses the Firefox registrar on its macOS and Linux supported paths. Browser-specific Chromium-family registration beyond Chrome is addressed by opener-0643 (PR #421); Safari registration is separately scoped. This task does not claim actual installed-browser discovery, signed app update distribution, or runtime extension communication.

## Commands / CI

```sh
python3 test-chrome-native-host-registration.py -v
cd extensions/webextension
npm run build
npm test
```

The existing required `scanner-tests` job runs both suites; no new CI permissions or credentials are necessary. The tests use disposable homes and synthetic executable files only, and never access a real browser profile or saved settings.

**Prerequisites for production:** Real application upgrades must keep an executable at the approved stable absolute path, or use a separately reviewed, explicitly authorized and conflict-safe migration to update the browser's manifest. The current registrars deliberately reject changed registrations. Successful registration does **not** authenticate browser requests, grant `nativeMessaging`, prove a clean PDF or authorize opening. The current extension remains inactive; mandatory ClamAV signature freshness, file integrity, quarantine, scan completeness, verified PDF handoff, and saved destination preferences remain unchanged.
