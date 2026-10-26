#!/usr/bin/env python3
"""Scan selected local files before changing quarantine or launching an app."""
import os
from pathlib import Path
import subprocess
import sys
import time

INSTALL_DIR = Path.home() / 'Library/Application Support/Studio/allow-and-open'
DATABASE = INSTALL_DIR / 'signatures'
STAMP = DATABASE / 'last-successful-update'
MAX_DATABASE_AGE = 48 * 60 * 60
MAX_FILE_SIZE = 512 * 1024 * 1024
PDF_SCAN_TIMEOUT = 30 * 60


def scanner_path():
    for candidate in ('/opt/homebrew/bin/clamscan', '/usr/local/bin/clamscan', '/usr/local/clamav/bin/clamscan'):
        if os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError('ClamAV is unavailable. Run the Allow and Open installer again.')


def check_database():
    try:
        age = time.time() - float(STAMP.read_text().strip())
    except (OSError, ValueError):
        raise RuntimeError('Malware signatures are unavailable. Run update-malware-signatures.sh.')
    if age < 0 or age > MAX_DATABASE_AGE:
        raise RuntimeError('Malware signatures have not been checked in 48 hours. Run update-malware-signatures.sh.')
    if not any(DATABASE.glob('daily.c[vl]d')) or not any(DATABASE.glob('main.c[vl]d')):
        raise RuntimeError('The malware signature database is incomplete. Run update-malware-signatures.sh.')


def fingerprint(path):
    # Detect replacement or modification while a scan is running, including bundle contents.
    import hashlib
    digest = hashlib.sha256()
    paths = sorted(path.rglob('*')) if path.is_dir() else [path]
    for entry in paths:
        digest.update(os.fsencode(str(entry)))
        if entry.is_symlink():
            digest.update(os.fsencode(os.readlink(entry)))
            if path.is_dir() and not entry.resolve().is_relative_to(path):
                raise RuntimeError('Application bundle contains a link outside the bundle; opening was stopped.')
        elif entry.is_file():
            if entry.stat().st_size > MAX_FILE_SIZE and (
                    path.is_dir() or path.suffix.lower() != '.pdf'):
                raise RuntimeError('The file exceeds the 512 MB scan limit; opening was stopped.')
            with entry.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
        elif not entry.is_dir():
            raise RuntimeError('Only regular files and application bundles can be scanned.')
    return digest.digest()


def remove_quarantine(path):
    if path.is_dir():
        subprocess.run(['/usr/bin/xattr', '-dr', 'com.apple.quarantine', str(path)], check=True)
    else:
        attributes = subprocess.run(['/usr/bin/xattr', str(path)], check=True, capture_output=True, text=True)
        if 'com.apple.quarantine' in attributes.stdout.splitlines():
            subprocess.run(['/usr/bin/xattr', '-d', 'com.apple.quarantine', str(path)], check=True)


def scan_and_open(item, scanner):
    path = Path(item).expanduser().resolve(strict=True)
    if not path.is_file() and not (path.is_dir() and path.suffix.lower() == '.app'):
        raise RuntimeError('Select a file or application, rather than a folder.')
    before = fingerprint(path)
    is_pdf = path.is_file() and path.suffix.lower() == '.pdf'
    if is_pdf:
        # Avoid arbitrary opener/ClamAV configuration caps for large PDFs.
        # ClamAV still has an internal per-file limit (~2 GB); keep alerting on it.
        size_options = ('--max-filesize=0', '--max-scansize=0')
    else:
        size_options = ('--max-filesize=512M', '--max-scansize=1024M')
    try:
        scan = subprocess.run([
            scanner, '--database=' + str(DATABASE), '--recursive',
            '--follow-file-symlinks=2', '--follow-dir-symlinks=2',
            '--alert-exceeds-max=yes', '--alert-encrypted=yes',
            *size_options,
            '--max-scantime=0', '--no-summary', '--', str(path)
        ], capture_output=True, text=True,
            timeout=PDF_SCAN_TIMEOUT if is_pdf else 180)
    except subprocess.TimeoutExpired:
        raise RuntimeError('The malware scan timed out; opening was stopped.')
    if scan.returncode == 1:
        raise RuntimeError('Malware or an unscannable item was detected; opening was stopped.\n' + scan.stdout.strip())
    if scan.returncode != 0:
        raise RuntimeError('The malware scan could not finish; opening was stopped.\n' + (scan.stderr or scan.stdout).strip())
    # ClamAV can emit warnings for unreadable or skipped inputs without a detection.
    lines = scan.stdout.splitlines()
    if not any(line.endswith(': OK') for line in lines) or any(
            not line.endswith((': OK', ': Empty file')) for line in lines) or scan.stderr.strip():
        raise RuntimeError('The malware scan did not confirm a complete scan; opening was stopped.\n' + (scan.stderr or scan.stdout).strip())
    if before != fingerprint(path):
        raise RuntimeError('The file changed during its scan; opening was stopped. Try again.')
    remove_quarantine(path)
    command = ['/usr/bin/open']
    if path.suffix.lower() == '.pdf':
        command += ['-b', 'com.brave.Browser']
    subprocess.run(command + [str(path)], check=True)


def main(items):
    try:
        scanner = scanner_path()
        check_database()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    result = 0
    for item in items:
        try:
            scan_and_open(item, scanner)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            print(f'{Path(item).name}: {error}', file=sys.stderr)
            result = 1
    return result


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
