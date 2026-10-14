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
cp "$script_dir/allow-and-open.sh" "$script_dir/scan-and-open.py" "$script_dir/update-malware-signatures.sh" "$install_dir/"
chmod 755 "$install_dir/allow-and-open.sh" "$install_dir/update-malware-signatures.sh"
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

app="$HOME/Applications/Open PDFs in Brave.app"
mkdir -p "$app/Contents/MacOS" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/Studio"
/usr/bin/xcrun swiftc -O "$script_dir/brave-pdf-opener.swift" -o "$app/Contents/MacOS/PDFOpener"
python3 - "$app" "$install_dir" <<'CONFIG'
import plistlib
import sys
from pathlib import Path
app, install_dir = map(Path, sys.argv[1:])
info = {
    'CFBundleExecutable': 'PDFOpener',
    'CFBundleIdentifier': 'local.studio.brave-pdf-opener',
    'CFBundleName': 'Open PDFs in Brave',
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
actions[0]['ActionParameters']['COMMAND_STRING'] = 'exec /bin/bash ' + shlex.quote(sys.argv[2]) + ' "$@"\n'
actions[0]['ActionParameters']['inputMethod'] = 1
actions[0]['ActionParameters']['shell'] = '/bin/bash'
with path.open('wb') as stream:
    plistlib.dump(workflow, stream)
PY

/usr/bin/swift "$script_dir/set-brave-pdf-default.swift" "$app"
echo "Installed local malware scanning for native PDF opening and both Allow and Open actions."
