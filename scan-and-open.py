#!/usr/bin/env python3
"""Scan selected local files before changing quarantine or launching an app."""
from contextlib import contextmanager
import fcntl
import hashlib
from file_launcher import launch_clean_file
import os
from pathlib import Path
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
import time

INSTALL_DIR = Path.home() / 'Library/Application Support/Studio/allow-and-open'
DATABASE = INSTALL_DIR / 'signatures'
STAMP = DATABASE / 'last-successful-update'
MAX_DATABASE_AGE = 48 * 60 * 60
MAX_FILE_SIZE = 512 * 1024 * 1024
PDF_SCAN_TIMEOUT = 30 * 60
CACHE_DB = INSTALL_DIR / 'clean-scan-cache.sqlite3'
CACHE_TTL = 90 * 24 * 60 * 60
MAX_CONCURRENT_SCANS = 2


@contextmanager
def scan_slot(cancelled=None):
    """Wait for one of two cross-process slots shared by Finder and the native app.

    Advisory locks are held on open file descriptors, so an interrupted process
    automatically releases its slot. No file names, paths, or scan results are logged.
    """
    slot_dir = CACHE_DB.parent / 'scan-slots'
    slot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (slot_dir.is_symlink() or not slot_dir.is_dir()
            or slot_dir.stat().st_uid != os.getuid()):
        raise RuntimeError('The scan queue is unavailable; opening was stopped.')
    while True:
        require_live_app(cancelled)
        for index in range(MAX_CONCURRENT_SCANS):
            lock_path = slot_dir / f'slot-{index}.lock'
            flags = os.O_CREAT | os.O_RDWR | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0)
            fd = os.open(lock_path, flags, 0o600)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                    raise RuntimeError('The scan queue is unavailable; opening was stopped.')
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                try:
                    yield
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                return
            finally:
                os.close(fd)
        time.sleep(0.05)


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
    # Hash the full byte stream, including embedded PDF metadata. Never rely on
    # filename, size, modification time, or Finder metadata for cache validity.
    digest = hashlib.sha256()
    is_bundle = path.is_dir()
    digest.update(b'bundle-v1\0' if is_bundle else b'file-v1\0')
    paths = sorted(path.rglob('*')) if is_bundle else [path]
    for entry in paths:
        # Include relative bundle paths, but let renamed identical files share a cache entry.
        if is_bundle:
            digest.update(os.fsencode(str(entry.relative_to(path))) + b'\0')
        if entry.is_symlink():
            digest.update(b'link\0' + os.fsencode(os.readlink(entry)) + b'\0')
            if is_bundle and not entry.resolve().is_relative_to(path):
                raise RuntimeError('Application bundle contains a link outside the bundle; opening was stopped.')
        elif entry.is_file():
            size = entry.stat().st_size
            if size > MAX_FILE_SIZE and (is_bundle or path.suffix.lower() != '.pdf'):
                raise RuntimeError('The file exceeds the 512 MB scan limit; opening was stopped.')
            digest.update(b'bytes\0' + str(size).encode('ascii') + b'\0')
            with entry.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
        elif entry.is_dir():
            digest.update(b'directory\0')
        else:
            raise RuntimeError('Only regular files and application bundles can be scanned.')
    return digest.digest()


def cache_key(digest, is_pdf):
    # Keep the existing 90-day cache for non-PDFs, but prevent older limited
    # PDF scans and differently configured non-PDF scans from bypassing a full PDF scan.
    return hashlib.sha256(b'pdf-unlimited-v1\0' + digest).digest() if is_pdf else digest


@contextmanager
def cache_connection():
    # Cache only a digest and verified scan timestamp in a private local database.
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    CACHE_DB.touch(mode=0o600, exist_ok=True)
    CACHE_DB.chmod(0o600)
    connection = sqlite3.connect(str(CACHE_DB), timeout=5)
    try:
        connection.execute('CREATE TABLE IF NOT EXISTS clean_scans '
                           '(digest TEXT PRIMARY KEY, scanned_at REAL NOT NULL)')
        with connection:
            yield connection
    finally:
        connection.close()


@contextmanager
def active_scan_lock(digest):
    # Lock stripes are keyed by the policy-specific digest and stay bounded.
    # Never unlink a lock file: a waiting process may still hold its inode.
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    lock_path = CACHE_DB.with_name(CACHE_DB.name + '.scan-lock-' + digest.hex()[:4])
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def cached_clean(digest):
    try:
        with cache_connection() as connection:
            row = connection.execute('SELECT scanned_at FROM clean_scans WHERE digest = ?',
                                     (digest.hex(),)).fetchone()
        age = time.time() - row[0] if row else -1
        return 0 <= age < CACHE_TTL
    except (OSError, sqlite3.Error, TypeError, ValueError):
        # Bad or unavailable caches never provide a clean verdict.
        return False


def remember_clean(digest):
    try:
        with cache_connection() as connection:
            now = time.time()
            connection.execute('DELETE FROM clean_scans WHERE scanned_at < ?',
                               (now - CACHE_TTL,))
            connection.execute('INSERT OR REPLACE INTO clean_scans (digest, scanned_at) VALUES (?, ?)',
                               (digest.hex(), now))
    except (OSError, sqlite3.Error):
        # Failure to save the cache does not invalidate a successful scan.
        pass

def remove_quarantine(path):
    if path.is_dir():
        subprocess.run(['/usr/bin/xattr', '-dr', 'com.apple.quarantine', str(path)], check=True)
    else:
        attributes = subprocess.run(['/usr/bin/xattr', str(path)], check=True, capture_output=True, text=True)
        if 'com.apple.quarantine' in attributes.stdout.splitlines():
            subprocess.run(['/usr/bin/xattr', '-d', 'com.apple.quarantine', str(path)], check=True)


def watch_parent_lifetime():
    """Detect EOF on the pipe retained by the native PDF app."""
    if os.environ.get('PDF_MAGIC_PARENT_LIFETIME') != '1':
        return None
    cancelled = threading.Event()

    def watch():
        try:
            sys.stdin.buffer.read(1)
        except (OSError, ValueError):
            pass
        cancelled.set()

    threading.Thread(target=watch, name='app-lifetime', daemon=True).start()
    return cancelled


def require_live_app(cancelled):
    if cancelled is not None and cancelled.is_set():
        raise RuntimeError('PDF Magic Opener exited during the scan; opening was stopped.')


def run_scan(command, timeout, cancelled):
    """Only native-owned scans need a cancellable, process-group-owned child."""
    if cancelled is None:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)

    require_live_app(cancelled)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        deadline = time.monotonic() + timeout
        while True:
            require_live_app(cancelled)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                stdout, stderr = process.communicate(timeout=min(remaining, 0.1))
                require_live_app(cancelled)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()


def _scan_and_open(item, scanner, cancelled=None):
    require_live_app(cancelled)
    path = Path(item).expanduser().resolve(strict=True)
    if not path.is_file() and not (path.is_dir() and path.suffix.lower() == '.app'):
        raise RuntimeError('Select a file or application, rather than a folder.')
    is_pdf = path.is_file() and path.suffix.lower() == '.pdf'
    before = fingerprint(path)
    cache_id = cache_key(before, is_pdf)
    # Do not serialize an already cached clean hit. For a miss, a cross-process
    # lock prevents another identical-content request from racing its scan.
    if not cached_clean(cache_id):
        with active_scan_lock(cache_id):
            # Recheck after waiting: the selected file may have changed.
            if before != fingerprint(path):
                raise RuntimeError('The file changed while checking it; opening was stopped. Try again.')
            # Only a completed clean result under this exact policy is reusable.
            if not cached_clean(cache_id):
                if is_pdf:
                    # The engine still alerts on its internal file-size limit (~2 GB).
                    size_options = ('--max-filesize=0', '--max-scansize=0')
                else:
                    size_options = ('--max-filesize=512M', '--max-scansize=1024M')
                try:
                    scan = run_scan([
                        scanner, '--database=' + str(DATABASE), '--recursive',
                        '--follow-file-symlinks=2', '--follow-dir-symlinks=2',
                        '--alert-exceeds-max=yes', '--alert-encrypted=yes',
                        *size_options,
                        '--max-scantime=0', '--no-summary', '--', str(path)
                    ], timeout=PDF_SCAN_TIMEOUT if is_pdf else 180, cancelled=cancelled)
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
                    raise RuntimeError('The file changed while checking it; opening was stopped. Try again.')
                require_live_app(cancelled)
                remember_clean(cache_id)
    require_live_app(cancelled)
    if before != fingerprint(path):
        raise RuntimeError('The file changed while checking it; opening was stopped. Try again.')
    require_live_app(cancelled)
    remove_quarantine(path)
    # The scan engine does not select an application or browser.
    require_live_app(cancelled)
    launch_clean_file(path)


def scan_and_open(item, scanner, cancelled=None):
    # Both Finder and the native PDF opener must respect the same process-wide cap.
    with scan_slot(cancelled=cancelled):
        return _scan_and_open(item, scanner, cancelled=cancelled)


def main(items):
    cancelled = watch_parent_lifetime()
    try:
        scanner = scanner_path()
        check_database()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    result = 0
    for item in items:
        try:
            scan_and_open(item, scanner, cancelled=cancelled)
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            print(f'{Path(item).name}: {error}', file=sys.stderr)
            result = 1
    return result


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
