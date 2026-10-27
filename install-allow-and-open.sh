#!/bin/bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
install_dir="$HOME/Library/Application Support/Studio/allow-and-open"
workflow="$HOME/Library/Services/Allow and Open.workflow/Contents/document.wflow"

if [ ! -f "$workflow" ]; then
    echo "The existing Allow and Open Quick Action is not installed." >&2
    exit 1
fi

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
cp "$script_dir/allow-and-open.sh" "$script_dir/scan-and-open.py" "$script_dir/file_launcher.py" "$script_dir/record-scan-origin.py" "$script_dir/update-malware-signatures.sh" "$install_dir/"
chmod 755 "$install_dir/allow-and-open.sh" "$install_dir/update-malware-signatures.sh"
/usr/bin/xcrun swiftc -O "$script_dir/launch-scanned-file.swift" -o "$install_dir/launch-scanned-file"
chmod 755 "$install_dir/launch-scanned-file"
python3 - "$install_dir" <<'CONFIG'
import sys
from pathlib import Path
path = Path(sys.argv[1])
(path / 'freshclam.conf').write_text(
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
mkdir -p "$app/Contents/Resources" "$app/Contents/MacOS" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/Studio"
cp "$script_dir/twilight-reading.png" "$app/Contents/Resources/twilight-reading.png"
/usr/bin/xcrun swiftc -O "$script_dir/brave-pdf-opener.swift" -o "$app/Contents/MacOS/PDFOpener"
python3 - "$app" "$install_dir" "$app_name" <<'CONFIG'
import plistlib
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
with (Path.home() / 'Library/LaunchAgents/local.studio.pdf-malware-signatures.plist').open('wb') as stream:
    plistlib.dump(agent, stream)
CONFIG
/usr/bin/codesign --force --sign - "$app"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$app"
agent="$HOME/Library/LaunchAgents/local.studio.pdf-malware-signatures.plist"
launchctl bootout "gui/$UID" "$agent" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$agent"

python3 - "$workflow" "$install_dir/allow-and-open.sh" <<'PY'
import plistlib
import shlex
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open('rb') as stream:
    workflow = plistlib.load(stream)
actions = [entry['action'] for entry in workflow['actions']
           if entry['action'].get('BundleIdentifier') == 'com.apple.RunShellScript']
if len(actions) != 1:
    raise SystemExit('Expected exactly one Run Shell Script action; workflow left unchanged.')
backup = path.with_name('document.wflow.before-brave')
if not backup.exists():
    backup.write_bytes(path.read_bytes())
actions[0]['ActionParameters']['COMMAND_STRING'] = 'export PDF_MAGIC_REQUEST_ORIGIN=finder\nexec /bin/bash ' + shlex.quote(sys.argv[2]) + ' "$@"\n'
actions[0]['ActionParameters']['inputMethod'] = 1
actions[0]['ActionParameters']['shell'] = '/bin/bash'
with path.open('wb') as stream:
    plistlib.dump(workflow, stream)
PY

/usr/bin/swift "$script_dir/set-brave-pdf-default.swift" "$app"
echo "Installed local malware scanning for native PDF opening and both Allow and Open actions."
