# Uninstall PDF Magic Opener (opener-0985)

This is the **interactive, user-directed macOS uninstall procedure** for the
per-user PDF Magic Opener installation. It is deliberately **not** a recursive
delete command: the installer can coexist with user-selected PDF applications,
a modified Finder Quick Action, FreshClam schedules and credentials, and
optional browser integrations. A shell script cannot safely assume ownership of
those settings. Perform the steps **in order**, from a complete, trusted source
checkout, while signed in to the macOS account that installed the application.
If any verification fails, **stop and preserve the installation** until the
unrecognized state is resolved. Do not run these steps with `sudo` or as root.

The separate ClamAV package, malware definitions, update logs, user preferences
and browser profiles are **not automatically uninstalled**. Keep your original
PDF application, source checkout and recovery information available until
verification is complete. The commands below are opt-in steps, not automatic
actions triggered by opening the preferences app.

## 1. Inspect and back up before changing anything

1. Stop opening new PDFs with the native handler, and finish or cancel any
   in-flight scans. Keep Preferences available through step 2, then quit the
   app before moving its bundle or retiring its helpers.
2. Back up only the data **you choose** to retain, including your PDF browser
   preference and FreshClam mirror/proxy configuration. The installed support
   directory is `~/Library/Application Support/Studio/allow-and-open`.
   It may contain user-customized configuration, historical scan metadata,
   signatures or unrelated files; **do not delete the directory wholesale**.
   Do not share private paths, PDF names, logs or proxy credentials.
3. **Detect the current macOS PDF handler before any removal or restoration.**
   While the installed support helpers are still present, run this established
   read-only status command in Terminal (it uses the PDF-specific Launch
   Services lookup, not your default web browser or post-scan viewer):

   ```sh
   python3 "$HOME/Library/Application Support/Studio/allow-and-open/pdf-handler-status.py"
   ```

   Read the **Current macOS PDF handler** line and record the detected bundle
   identifier. The tool distinguishes **PDF Magic Opener is the default PDF
   handler** from **PDF Magic Opener is not the default PDF handler** and names
   the other application when present. Both known outcomes exit successfully.
   An unavailable helper, malformed/unreadable association, or failed lookup
   exits nonzero: **stop uninstallation** rather than guessing, erasing an
   application, or changing an association. Check
   **PDF Magic Opener > Preferences > General > Default PDF handler** for a
   second read-only view if needed, but do not interpret a missing or unknown
   answer as permission to remove the current PDF handler. Confirm you know
   which viewer should receive PDFs after removal.
4. From the trusted source checkout, check whether the managed signature-update
   LaunchAgent is recognized (read-only, does not start or stop anything):

   ```sh
   python3 signature_update_launchagent.py
   ```

   `existing` means the identity and updater command match; `absent` means
   there is no matching agent. An error means the file is unrecognized, unsafe
   or inaccessible: **stop**, do not move or unload it by guessing. An
   unrecognized or unsafe component is never permission for a guessed delete.

## 2. Restore a non-PDF-Magic default before removing its handler

Use the **detected result from step 1** to decide whether restoration is
needed. If **another application is already the default**, preserve that
choice without running any restoration action. If **PDF Magic Opener is the
default**, go to **Preferences > General > Default PDF application** and select
**Restore Previous Default** only if the saved previous handler is still
valid. That action uses the already installed `pdf-handler-history` utility,
which verifies the current PDF handler and saved previous application before
changing Launch Services. If there is no restorable history, deliberately
choose another PDF viewer using Finder **Get Info > Open with > Change All…**.

After any restoration or user-selected change, **re-detect the current handler
before proceeding to removal** while the installed helper is still present:

```sh
python3 "$HOME/Library/Application Support/Studio/allow-and-open/pdf-handler-status.py"
```

**Proceed only when this fresh check names a known non-PDF-Magic default.**
If it still reports PDF Magic Opener, or the association cannot be determined,
**stop before removing the app or its helpers**. Do not force a restoration or
reset all Launch Services associations. If another program was already the
default, leave the current user choice untouched. Without the PDF Magic
Opener handler as the default, automatic scan-before-open for Finder PDF
double-clicks no longer applies. The replacement PDF viewer may open files
without a malware scan.

## 3. Restore or disconnect the Finder Quick Action

A previously migrated `Allow and Open` Finder Quick Action may still invoke
the installed scanner script. Inspect it with the reviewed read-only tool:

```sh
python3 restore_finder_quick_action.py
```

If this confirms the original saved action can safely be restored and you
want that original action, opt in explicitly:

```sh
python3 restore_finder_quick_action.py --restore
```

The existing restoration tool refuses to overwrite a modified action or
unrecognized backup and retains the backup. The original Finder action **may not perform PDF Magic's malware scans**. If no verified restoration is possible,
use Finder/Automator to **disable or remove only the PDF Magic-managed action
after reviewing its identity**, or retain it until you can resolve the
customization. Do not delete unrelated Services workflows or backups. Do not
remove the supporting scanner scripts while a Finder action still invokes them.

## 4. Remove only previously approved native messaging registrations

The packaged browser extensions are inactive. If you never explicitly
registered a native messaging host, skip this step. Otherwise run the already
reviewed, narrowly scoped cleanup from the trusted checkout, supplying the
**actual original absolute host path and approved browser/extension IDs**.
For example, for an explicitly registered Firefox **development** add-on:

```sh
python3 native-messaging/unregister-hosts.py \
  --host-path "$HOME/Library/Application Support/Studio/allow-and-open/pdf-magic-native-host" \
  --browser firefox --development
```

If you explicitly registered Chrome, use `--browser chrome --extension-id`
with each **originally approved 32-character ID**, in its original order;
do not invent or substitute an ID. See
[`native-messaging/uninstall-registration.md`](../native-messaging/uninstall-registration.md)
for the exact Chrome invocation and supported platforms. The cleanup requires
a byte-for-byte known manifest and rejects symlinks, modified registrations,
other browsers and unrecognized profiles. Resolve a refusal manually; **do
not** erase a manifest with an unknown owner.

## 5. Retire the managed signature updater, if desired

Only if step 1 reported `existing` and you intend to remove PDF Magic's
**dedicated** signature updater, stop its exact user service:

```sh
launchctl bootout "gui/$(id -u)/local.studio.pdf-malware-signatures"
```

If the service was not loaded, verify that condition instead of treating a
failed `bootout` as successful. Do not use a wildcard or unload other agents.
Only after confirming the service is inactive should you move
`~/Library/LaunchAgents/local.studio.pdf-malware-signatures.plist` to Trash
**through Finder**, and only if its inspected identity still matches.
Preserve any customized schedule, user-owned configuration and logs for
recovery. An unrecognized or changed plist is a stop condition.

Removing this agent stops PDF Magic's scheduled FreshClam updates; another
tool may still depend on ClamAV or its definitions. Do not run
`brew uninstall clamav` as part of this procedure. Shared scanner packages,
definitions and update configuration are separate user-managed resources.

## 6. Remove the verified application and retire its entry points

Only after **the fresh step 2 PDF-handler check has reported a known
non-PDF-Magic default**, and after confirming steps 2–5 have disconnected
the PDF handler, Finder action and any opted-in browser registrations,
move **only**
`~/Applications/PDF Magic Opener.app` to Trash **using Finder**. Before moving
it, verify in Finder's Get Info that it is the intended app in your own home
Applications folder; if the bundle is renamed, symlinked, substituted or
customized, stop rather than guessing another path. Do not remove
`Open PDFs in Brave.app` or other app bundles by similarity of name.

If you wish to retire the remaining per-user scripts, **review their contents
and ownership individually** within
`~/Library/Application Support/Studio/allow-and-open`. They can include
`allow-and-open.sh`, `scan-and-open.py`, `launch-scanned-file` and other
managed helpers. Move only verified, unchanged PDF Magic-installed entry points
to Trash after confirming no integration still references them. **Keep**
`target-app.txt`, `freshclam.conf`, `signatures/`, backup files, scan history,
logs and any customized scripts unless you separately authorize their
removal. Never recursively erase the shared Studio or support directory.
Never run a script in that directory simply to identify it.

## 7. Verify and retain a recovery path

1. Confirm macOS opens PDFs with your **chosen other** application, not the
   removed handler. This does **not** prove that viewer scans documents.
2. Confirm the Finder **Allow and Open** action is restored, intentionally
   disabled, or retained with its required helper; verify the action does
   not point to a removed executable.
3. Confirm opted-in native messaging registrations are gone using the
   reviewed registration tools, not by modifying browser profiles.
4. If retired, confirm `launchctl` no longer lists the exact PDF Magic
   signature-update agent. Confirm no unexpected update processes remain.
5. Keep retained application data and backups until you no longer need
   rollback. If any step fails, leave remaining components intact; use the
   trusted [repair procedure](repair-installation.md) to recover a verified
   scan-handler installation if necessary.

**Security boundary:** Uninstallation never grants permission to bypass the
native scanner while PDF Magic Opener remains the selected PDF handler.
Missing scanner components must fail closed; uninstalling the handler simply
means **its scan gate no longer protects PDFs opened by the replacement app**.
No guaranteed malware safety or data-erasure claim is made.

## CI and ownership boundaries

`tests/general/uninstall-procedure.py` checks this procedure against the
real existing default-handler restoration, Finder Quick Action restoration,
native messaging cleanup, and signature-agent ownership verification paths.
It also guards the order and repeatability of the installed read-only PDF
handler status lookup (including unknown-result refusal), and rules out
destructive recursive cleanup, silent association changes and automatic
deletion of user data.
The required `scanner-tests` CI job executes the check.
No uninstall commands or OS mutations run during CI.
