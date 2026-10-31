#!/bin/bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
install_dir="$HOME/Library/Application Support/Studio/allow-and-open"
workflow="$HOME/Library/Services/Allow and Open.workflow/Contents/document.wflow"

if [ ! -f "$workflow" ]; then
    echo "The existing Allow and Open Quick Action is not installed." >&2
    exit 1
fi

# Discover existing scan entry points before touching installed scripts or settings.
# This preflight never reads or runs existing user-customized script contents.
python3 "$script_dir/scripts/detect_existing_scan_scripts.py" "$install_dir"

if ! [ -x /opt/homebrew/bin/clamscan ] && ! [ -x /usr/local/bin/clamscan ] && ! [ -x /usr/local/clamav/bin/clamscan ]; then
    brew install clamav
fi

mkdir -p "$install_dir/signatures"
# Preserve the selected PDF target across reinstalls.
python3 - "$install_dir/target-app.txt" <<'TARGET_APP'
import os
import sys

try:
    fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    pass
else:
    with os.fdopen(fd, 'w', encoding='ascii') as stream:
        stream.write('com.brave.Browser\n')
TARGET_APP
cp "$script_dir/allow-and-open.sh" "$script_dir/scan-and-open.py" "$script_dir/file_launcher.py" "$script_dir/browser_registry.py" "$script_dir/scan_results.py" "$script_dir/record-scan-origin.py" "$script_dir/update-malware-signatures.sh" "$script_dir/signature_update_status.py" "$install_dir/"
# Deploy the read-only status display beside its Launch Services lookup.
cp "$script_dir/pdf-handler-status.py" "$install_dir/pdf-handler-status.py"
chmod 755 "$install_dir/allow-and-open.sh" "$install_dir/update-malware-signatures.sh"
/usr/bin/xcrun swiftc -O "$script_dir/launch-scanned-file.swift" -o "$install_dir/launch-scanned-file"
chmod 755 "$install_dir/launch-scanned-file"
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/resolve-default-browser.swift" -o "$install_dir/resolve-default-browser"
chmod 755 "$install_dir/resolve-default-browser"
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/discover-installed-browsers.swift" -o "$install_dir/discover-installed-browsers"
chmod 755 "$install_dir/discover-installed-browsers"
# Read-only installed application discovery uses the macOS Spotlight index.
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/installed-applications.swift" -o "$install_dir/installed-applications"
chmod 755 "$install_dir/installed-applications"
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/identify-pdf-handler.swift" -o "$install_dir/identify-pdf-handler"
chmod 755 "$install_dir/identify-pdf-handler"
# Read-only detector reuses the same Launch Services lookup; it never resets associations.
/usr/bin/xcrun swiftc -parse-as-library -D PDF_HANDLER_TESTING -O "$script_dir/identify-pdf-handler.swift" "$script_dir/detect-pdf-handler-change.swift" -o "$install_dir/detect-pdf-handler-change"
chmod 755 "$install_dir/detect-pdf-handler-change"
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/pdf-handler-history.swift" -o "$install_dir/pdf-handler-history"
chmod 755 "$install_dir/pdf-handler-history"
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/verify-pdf-target.swift" -o "$install_dir/verify-pdf-target"
# User-invoked custom .app chooser reuses the existing PDF verification logic.
cp "$script_dir/select-custom-pdf-application.py" "$install_dir/select-custom-pdf-application.py"
/usr/bin/xcrun swiftc -parse-as-library -D PDF_TARGET_TESTING -O \
    "$script_dir/verify-pdf-target.swift" "$script_dir/select-custom-pdf-application.swift" \
    -o "$install_dir/select-custom-pdf-application"
chmod 755 "$install_dir/select-custom-pdf-application" "$install_dir/select-custom-pdf-application.py"
# Optional read-only browser-list display; no changes to scanner or target-app.txt.
/usr/bin/xcrun swiftc -parse-as-library -O -D BROWSER_DISCOVERY_TESTING -D BROWSER_METADATA_TESTING \
    "$script_dir/browser-preference-list.swift" "$script_dir/browser-preference-live-refresh.swift" "$script_dir/discover-installed-browsers.swift" \
    "$script_dir/browser-app-metadata.swift" -o "$install_dir/browser-preference-list"
chmod 755 "$install_dir/browser-preference-list"
python3 - "$install_dir" <<'CONFIG'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
config = path / 'freshclam.conf'
# An existing file can contain working mirror/proxy customizations. Do not
# read, normalize or overwrite it during an application upgrade.
try:
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
except FileExistsError:
    if not stat.S_ISREG(config.lstat().st_mode):
        raise SystemExit('Unsafe existing FreshClam configuration; installation stopped.')
else:
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(
            'DatabaseDirectory "' + str(path / 'signatures') + '"\n'
            'DatabaseMirror database.clamav.net\n'
            'ScriptedUpdates yes\n'
        )
CONFIG
bash "$install_dir/update-malware-signatures.sh"

app_name="PDF Magic Opener"
app="$HOME/Applications/$app_name.app"
legacy_app="$HOME/Applications/Open PDFs in Brave.app"
# Keep the established bundle ID and runtime paths while renaming the user-facing app.
# Only move an existing installation after verifying that it belongs to this project.
python3 - "$legacy_app" "$app" <<'MIGRATE'
import plistlib
import sys
from pathlib import Path

legacy, destination = map(Path, sys.argv[1:])
expected_id = 'local.studio.brave-pdf-opener'

def check_bundle(path):
    if path.is_symlink() or not path.is_dir():
        raise SystemExit(f'Unsafe or invalid application bundle: {path}')
    try:
        with (path / 'Contents/Info.plist').open('rb') as stream:
            identifier = plistlib.load(stream).get('CFBundleIdentifier')
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        raise SystemExit(f'Cannot verify application bundle {path}: {error}')
    if identifier != expected_id:
        raise SystemExit(f'Unexpected bundle identifier at {path}; refusing to overwrite or move it.')

if legacy.exists() or legacy.is_symlink():
    check_bundle(legacy)
    if destination.exists() or destination.is_symlink():
        raise SystemExit('Both old and new PDF opener bundles exist; resolve the duplicate before installing.')
    legacy.rename(destination)
elif destination.exists() or destination.is_symlink():
    check_bundle(destination)
MIGRATE
# Build away from the installed app so an incomplete or nonexecutable bundle
# never replaces the working PDF scan handler. Keep staging on the same volume.
installed_app="$app"
mkdir -p "$HOME/Applications" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/Studio"
bundle_stage_dir="$(mktemp -d "$HOME/Applications/.pdf-magic-opener-build.XXXXXXXX")"
cleanup_bundle_stage() {
    # Restore the prior handler if the installation rename did not complete.
    if [ -d "$bundle_stage_dir/previous.app" ] && [ ! -e "$installed_app" ] && [ ! -L "$installed_app" ]; then
        mv "$bundle_stage_dir/previous.app" "$installed_app" || true
    fi
    rm -rf "$bundle_stage_dir"
}
trap cleanup_bundle_stage EXIT
app="$bundle_stage_dir/$app_name.app"
mkdir -p "$app/Contents/Resources" "$app/Contents/MacOS"
cp "$script_dir/twilight-reading.png" "$app/Contents/Resources/twilight-reading.png"
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/brave-pdf-opener.swift" \
    "$script_dir/scan-progress-view.swift" \
    "$script_dir/PDFMagicOpenerApp/ScanProgressPreference.swift" \
    -o "$app/Contents/MacOS/PDFOpener"
/usr/bin/xcrun swiftc -parse-as-library -O "$script_dir/make-pdf-magic-default.swift" -o "$app/Contents/MacOS/MakePDFMagicDefault"
python3 - "$app" "$install_dir" "$app_name" <<'CONFIG'
import os
import plistlib
import stat
import sys
from pathlib import Path
app, install_dir = map(Path, sys.argv[1:3])
app_name = sys.argv[3]
info = {
    'CFBundleExecutable': 'PDFOpener',
    'CFBundleIdentifier': 'local.studio.brave-pdf-opener',
    'CFBundleName': app_name,
    'CFBundleDisplayName': app_name,
    'CFBundlePackageType': 'APPL',
    'CFBundleVersion': '1',
    'CFBundleShortVersionString': '1.0',
    'LSMinimumSystemVersion': '13.0',
    'LSUIElement': True,
    'CFBundleDocumentTypes': [{
        'CFBundleTypeName': 'PDF document', 'CFBundleTypeRole': 'Viewer',
        'LSHandlerRank': 'Owner', 'LSItemContentTypes': ['com.adobe.pdf'],
    }],
}
with (app / 'Contents/Info.plist').open('wb') as stream:
    plistlib.dump(info, stream)
agent = {
    'Label': 'local.studio.pdf-malware-signatures',
    'ProgramArguments': ['/bin/bash', str(install_dir / 'update-malware-signatures.sh')],
    'StartInterval': 14400,
    'RunAtLoad': True,
    'ProcessType': 'Background',
    'StandardOutPath': str(Path.home() / 'Library/Logs/Studio/pdf-malware-signatures.log'),
    'StandardErrorPath': str(Path.home() / 'Library/Logs/Studio/pdf-malware-signatures.error.log'),
}
# Preserve any existing per-user schedule, including custom update intervals.
# Only provision the default for a fresh installation; reject unsafe entries.
agent_path = Path.home() / 'Library/LaunchAgents/local.studio.pdf-malware-signatures.plist'
try:
    fd = os.open(agent_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
except FileExistsError:
    if not stat.S_ISREG(agent_path.lstat().st_mode):
        raise SystemExit('Unsafe existing signature update schedule; installation stopped.')
else:
    with os.fdopen(fd, 'wb') as stream:
        plistlib.dump(agent, stream)
CONFIG
/usr/bin/codesign --force --sign - "$app"
# No installed app is replaced or registered until staged contents, PDF identity,
# executable permissions, and the ad hoc signature have been checked.
/usr/bin/codesign --verify "$app"
python3 "$script_dir/scripts/verify_pdf_opener_bundle.py" "$app"
if [ -e "$installed_app" ] || [ -L "$installed_app" ]; then
    mv "$installed_app" "$bundle_stage_dir/previous.app"
fi
mv "$app" "$installed_app"
app="$installed_app"
# Offer an opt-in Finder action without overwriting user-managed scripts.
action="$HOME/Applications/Make PDF Magic Opener Default.command"
if [ ! -e "$action" ] && [ ! -L "$action" ]; then
    cp "$script_dir/make-pdf-magic-default.command" "$action"
    chmod 755 "$action"
fi
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app"
agent="$HOME/Library/LaunchAgents/local.studio.pdf-malware-signatures.plist"
launchctl bootout "gui/$UID" "$agent" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$agent"

python3 - "$workflow" <<'PY'
import os
import plistlib
import stat
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
backup = path.with_name('document.wflow.before-brave')
fixed_command = (
    'export PDF_MAGIC_REQUEST_ORIGIN=finder\n'
    'exec /bin/bash "$HOME/Library/Application Support/Studio/'
    'allow-and-open/allow-and-open.sh" "$@"\n'
)
# Recognize only the product's previously installed command strings, not
# arbitrary user-maintained Finder scripts.
legacy_commands = {
    fixed_command,
    'exec /bin/bash "$HOME/Library/Application Support/Studio/'
    'allow-and-open/allow-and-open.sh" "$@"\n',
    '/bin/bash "$HOME/Library/Application Support/Studio/'
    'allow-and-open/allow-and-open.sh" "$@"\n',
}

# Refuse symlinks/other file kinds before reading or writing Quick Action data.
metadata = path.lstat()
if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
    raise SystemExit('Unsafe Finder Quick Action file; migration refused.')
if backup.is_symlink() or (backup.exists() and not backup.is_file()):
    raise SystemExit('Unsafe Finder Quick Action backup; migration refused.')

original = path.read_bytes()
workflow = plistlib.loads(original)
if not isinstance(workflow, dict) or not isinstance(workflow.get('actions'), list):
    raise SystemExit('Invalid Finder Quick Action; workflow left unchanged.')
actions = [
    entry['action'] for entry in workflow['actions']
    if isinstance(entry, dict) and isinstance(entry.get('action'), dict)
    and entry['action'].get('BundleIdentifier') == 'com.apple.RunShellScript'
]
if len(actions) != 1:
    raise SystemExit('Expected exactly one Run Shell Script action; workflow left unchanged.')
parameters = actions[0].get('ActionParameters')
if not isinstance(parameters, dict):
    raise SystemExit('Invalid Finder shell parameters; workflow left unchanged.')
command = parameters.get('COMMAND_STRING')
if command not in legacy_commands:
    # The user may have installed an unrelated/custom workflow with this name.
    # Neither its shell source nor its saved backup belongs to this migration.
    print('Preserving customized Finder Quick Action; no migration performed.')
    raise SystemExit(0)

if (command == fixed_command and parameters.get('inputMethod') == 1
        and parameters.get('shell') == '/bin/bash'):
    print('Finder Quick Action already migrated.')
    raise SystemExit(0)

parameters['COMMAND_STRING'] = fixed_command
parameters['inputMethod'] = 1  # Pass Finder input as argv, never shell interpolation.
parameters['shell'] = '/bin/bash'
fmt = plistlib.FMT_BINARY if original.startswith(b'bplist00') else plistlib.FMT_XML
updated = plistlib.dumps(workflow, fmt=fmt)

# Preserve the first pre-migration copy. Never follow or overwrite an existing
# backup, including a dangling symlink. This also leaves unrelated actions intact.
if not backup.exists():
    with backup.open('xb') as stream:
        stream.write(original)

# Stage in the same directory; a failed serialization or write must not leave
# a truncated Quick Action. Preserve the workflow's original permission bits.
staged = None
try:
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.document.wflow.',
                                     delete=False) as stream:
        staged = Path(stream.name)
        stream.write(updated)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(staged, stat.S_IMODE(metadata.st_mode))
    # Do not replace a link swapped into place while staging.
    current = path.lstat()
    if (not stat.S_ISREG(current.st_mode) or current.st_ino != metadata.st_ino
            or current.st_dev != metadata.st_dev):
        raise RuntimeError('Finder Quick Action changed during migration.')
    os.replace(staged, path)
finally:
    if staged is not None:
        staged.unlink(missing_ok=True)
print('Migrated existing Finder Quick Action to the scan-gated PDF Magic opener.')

PY

# Only after explicit consent, preserve the user's previous PDF handler before
# running the verified setter; refusal never changes the association.
python3 "$script_dir/offer-restore-pdf-handler.py" \
    "$install_dir/identify-pdf-handler" "$script_dir/set-pdf-default-handler.swift" "$app" \
    "$install_dir/pdf-handler-history" "$install_dir/previous-pdf-handler.txt"
# Display the effective association whether restoration was accepted or not.
python3 "$install_dir/pdf-handler-status.py"
echo "Installed local malware scanning for native PDF opening and both Allow and Open actions."
