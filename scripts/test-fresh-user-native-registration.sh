#!/usr/bin/env bash
# Exercise Firefox's real per-user registrar as a freshly created Linux user.
# This operates solely inside an ephemeral CI/container account, never in the
# runner's or developer's Firefox profile. It never connects to or runs a scanner.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" || "$(id -u)" -ne 0 ]]; then
  echo "Fresh-user integration test requires root on a disposable Linux runner" >&2
  exit 2
fi
for command in useradd userdel runuser node python3; do
  if ! command -v "$command" >/dev/null; then
    echo "Missing fresh-account test prerequisite: $command" >&2
    exit 2
  fi
done

repo_root="$(cd "$(dirname "$0")/.." && pwd -P)"
node_bin="$(command -v node)"
python_bin="$(command -v python3)"
scratch="$(mktemp -d /tmp/pdfmagic-fresh-user-XXXXXXXX)"
user="pdfm$RANDOM$RANDOM"
home="$scratch/home"
registered=false
cleanup() {
  if [[ "$registered" == true ]]; then
    userdel -r "$user" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
chmod 0755 "$scratch"  # Only the new user can access its separate 0700 home.
useradd --create-home --home-dir "$home" --shell /bin/sh "$user"
registered=true

if [[ ! -d "$home" || -e "$home/.mozilla" ]]; then
  echo "Expected a newly created, unconfigured account" >&2
  exit 1
fi
install -d -o "$user" -g "$user" -m 0700 "$home/bin"
host="$home/bin/pdf-magic-native-host"
printf '#!/bin/sh\nexit 0\n' > "$host"
chown "$user:$user" "$host"
chmod 0700 "$host"
registrar="$repo_root/native-messaging/firefox/register.mjs"
registration="$home/.mozilla/native-messaging-hosts/org.pdfmagic.opener.json"

# No opt-in means no manifest or even a Firefox configuration directory.
if runuser -u "$user" -- env -i HOME="$home" "$node_bin" "$registrar" \
  --host "$host" >"$scratch/denied.log" 2>&1; then
  echo "Unapproved registration unexpectedly succeeded" >&2
  exit 1
fi
if [[ -e "$home/.mozilla" ]]; then
  echo "The rejected registration modified the fresh account" >&2
  exit 1
fi

# Invoke the public CLI (not a test-only function) with this new OS identity.
runuser -u "$user" -- env -i HOME="$home" "$node_bin" "$registrar" \
  --host "$host" --development

# Inspect the actual file *as that account*. The expected Firefox location and
# allowlist must be exact; no other browser, profile, or preference is touched.
runuser -u "$user" -- env -i HOME="$home" "$python_bin" - "$home" "$host" "$user" <<'PY'
import json
import os
from pathlib import Path
import pwd
import stat
import sys

home, host, username = (Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
assert os.environ["HOME"] == str(home)
assert os.getuid() == pwd.getpwnam(username).pw_uid
folder = home / ".mozilla" / "native-messaging-hosts"
target = folder / "org.pdfmagic.opener.json"
assert target.is_file() and not target.is_symlink()
metadata = target.stat()
assert stat.S_IMODE(metadata.st_mode) == 0o600
assert metadata.st_uid == os.getuid()
assert list(folder.iterdir()) == [target]
assert json.loads(target.read_text(encoding="utf-8")) == {
  "name": "org.pdfmagic.opener",
  "description": "PDF Magic Opener Firefox native messaging host (development only)",
  "path": str(host),
  "type": "stdio",
  "allowed_extensions": ["pdf-magic-opener@example.invalid"],
}
assert host.stat().st_uid == os.getuid()
assert not (home / "Library").exists(), "Must not write macOS/Chrome registration"
assert not (home / ".config" / "google-chrome").exists(), "Must not create Chrome profiles"
assert not (home / ".config" / "chromium").exists(), "Must not create Chromium profiles"
assert not (home / ".mozilla" / "firefox").exists(), "Must not create Firefox profiles"
assert not (home / ".config" / "BraveSoftware").exists(), "Must not create Brave profiles"
PY

before="$(sha256sum "$registration")"
runuser -u "$user" -- env -i HOME="$home" "$node_bin" "$registrar" \
  --host "$host" --development
[[ "$(sha256sum "$registration")" == "$before" ]] || {
  echo "Idempotent registration unexpectedly changed the manifest" >&2
  exit 1
}

echo "Fresh Linux user native-host registration: PASS"
