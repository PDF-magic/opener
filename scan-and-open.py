#!/usr/bin/env python3
"""Scan selected local files while retaining macOS quarantine protections."""
from contextlib import contextmanager
from scan_results import EFFECTIVE_POLICY_ID, ScanResult
from functools import wraps
from dataclasses import dataclass, field
import fcntl
import hashlib
from file_launcher import (PDF_DEFAULT_BROWSER_UNAVAILABLE_MESSAGE,
                           PDF_TARGET_UNAVAILABLE_MESSAGE,
                           PDF_TARGET_VERIFICATION_MESSAGE,
                           intended_destination, launch_clean_file,
                           pdf_fallback_application,
                           verify_launch_target, verify_local_file_available)
import os
import signal
import re
from pathlib import Path
from typing import Optional
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
SCAN_REQUEST_DB = INSTALL_DIR / 'scan-requests.sqlite3'
CACHE_TTL = 90 * 24 * 60 * 60
MAX_CONCURRENT_SCANS = 2
REQUESTING_APPLICATION_ENV = 'PDF_MAGIC_REQUESTING_APPLICATION'

PDF_LAUNCH_UNAVAILABLE_MESSAGE = (
    'The scan completed cleanly, but the selected PDF application could not open the file. '
    'Check that it is installed or choose another PDF-capable application in target-app.txt.'
)

# Only these fixed, path-free errors may appear in scan diagnostics.
# Unexpected system or scanner exceptions may contain private source paths.
SAFE_SCAN_FAILURES = frozenset((
    PDF_DEFAULT_BROWSER_UNAVAILABLE_MESSAGE,
    PDF_TARGET_UNAVAILABLE_MESSAGE,
    PDF_TARGET_VERIFICATION_MESSAGE,
    PDF_LAUNCH_UNAVAILABLE_MESSAGE,
    'Application bundle contains a link outside the bundle; opening was stopped.',
    'The file exceeds the 512 MB scan limit; opening was stopped.',
    'Only regular files and application bundles can be scanned.',
    'Select a file or application, rather than a folder.',
    'The malware scan timed out; opening was stopped.',
    'Malware was detected; opening was stopped.',
    'The scanner flagged a suspicious or unscannable item; opening was stopped.',
    'The malware scan could not finish; opening was stopped.',
    'The malware scan did not confirm a complete scan; opening was stopped.',
    'The file changed while checking it; opening was stopped. Try again.',
    'The clean scan cache could not be verified; opening was stopped.',
    'ClamAV scanner version could not be verified. Reinstall ClamAV before opening files.',
    'Unsupported ClamAV scanner version. Install ClamAV 1.4 or 1.5 before opening files.',
    'The requested PDF is not available locally; opening was stopped.',
))



@dataclass(frozen=True)
class CleanScanResult:
    """A completed, verified clean scan, independent of app launch success."""

    status: str
    from_cache: bool
    scanner_version: Optional[str] = None
    signature_database_version: Optional[str] = None
    detection_names: tuple[str, ...] = ()
    # The installed Built-in gate remains effective for every completed scan,
    # independent of caller-supplied protection_level request metadata.
    effective_policy_id: str = field(default=EFFECTIVE_POLICY_ID, init=False)



@dataclass(frozen=True)
class ScanSecurityPolicySnapshot:
    """Request-scoped Built-in limits, not a selectable protection profile.

    Mandatory ClamAV flags, integrity checks, freshness, fail-closed verdicts
    and verified handoff remain unconditional. Only tighter timeouts are valid.
    """
    pdf_timeout_seconds: int = PDF_SCAN_TIMEOUT
    other_timeout_seconds: int = 180

    def __post_init__(self):
        for value, maximum in ((self.pdf_timeout_seconds, PDF_SCAN_TIMEOUT),
                               (self.other_timeout_seconds, 180)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('Scan limits must be positive integers within Built-in bounds.')


class ActiveScanPolicy:
    """Atomically publish immutable Built-in limits for subsequent requests."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current = ScanSecurityPolicySnapshot()

    def snapshot(self):
        with self._lock:
            return self._current

    def activate(self, policy):
        if type(policy) is not ScanSecurityPolicySnapshot:
            raise TypeError('Only validated Built-in policy snapshots can be activated.')
        with self._lock:
            self._current = policy


ACTIVE_SCAN_POLICY = ActiveScanPolicy()
DEFAULT_SCAN_POLICY = ScanSecurityPolicySnapshot()


def policy_cache_key(digest, is_pdf, policy):
    """Prevent reuse of a clean verdict under different effective limits."""
    if type(policy) is not ScanSecurityPolicySnapshot:
        raise TypeError('A validated scan security policy is required.')
    legacy = cache_key(digest, is_pdf)
    if policy == DEFAULT_SCAN_POLICY:
        return legacy  # Preserve existing cache behavior for unchanged Built-in.
    identity = (f'{policy.pdf_timeout_seconds}:{policy.other_timeout_seconds}').encode('ascii')
    return hashlib.sha256(b'bounded-scan-policy-v1\\0' + identity + b'\\0' + legacy).digest()


class LaunchFailedError(RuntimeError):
    """An app launch failed after verification; the clean scan result survives."""

    def __init__(self, scan_result, *, is_pdf=False):
        self.scan_result = scan_result
        super().__init__(
            PDF_LAUNCH_UNAVAILABLE_MESSAGE if is_pdf else
            'The scan completed cleanly, but the destination application could not open the file.'
        )



@contextmanager
def scan_slot():
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


@dataclass(frozen=True)
class ScanRequest:
    # A filename extension is a declared type, not proof of the file's contents.
    file_type: str
    # Optional origin metadata supplied by a caller; never a fetch or scan target.
    source_url: Optional[str] = None
    # Request metadata only; cancellation execution is a separate concern.
    cancellation_requested: bool = False
    # Capture caller selection as metadata; it never changes scan enforcement.
    protection_level: Optional[str] = None
    browser_download_identifier: Optional[str] = None

    @classmethod
    def from_path(cls, path, source_url=None, protection_level=None,
                  browser_download_identifier=None):
        return cls(file_type=path.suffix.lower().lstrip('.') or 'unknown',
                   source_url=source_url, protection_level=protection_level,
                   browser_download_identifier=browser_download_identifier)


@dataclass(frozen=True)
class BrowserDownloadRequest:
    """Optional browser correlation attached to a single requested path."""
    path: str
    browser_download_identifier: Optional[str] = None


def parse_scan_requests(args):
    """Keep ordinary file arguments compatible with optional browser metadata."""
    if args and args[0] == '--browser-download-id':
        if len(args) != 3:
            raise ValueError('A browser download ID requires one identifier and one file path.')
        identifier = args[1]
        if (not identifier or len(identifier) > 256 or
                any(ord(character) < 32 or ord(character) == 127
                    for character in identifier)):
            raise ValueError('The browser download ID must be a nonempty printable identifier.')
        return [BrowserDownloadRequest(args[2], identifier)]
    return [BrowserDownloadRequest(path) for path in args]


def validate_scan_request(item):
    """Fail closed on invalid selections before hashing, scanning, or opening."""
    try:
        requested = os.fspath(item)
    except TypeError as error:
        raise RuntimeError('Scan request requires a file path.') from error
    if not isinstance(requested, str) or not requested or '\0' in requested:
        raise RuntimeError('Scan request requires a valid, nonempty file path.')
    if requested.lower().endswith('.pdf.icloud'):
        raise RuntimeError('The requested PDF is not available locally; opening was stopped.')
    path = Path(requested).expanduser().resolve(strict=True)
    if not path.is_file() and not (path.is_dir() and path.suffix.lower() == '.app'):
        raise RuntimeError('Select a file or application, rather than a folder.')
    return path


NATIVE_CANCELLATION = 'PDF_MAGIC_NATIVE_CANCEL'


class ScanCancelled(RuntimeError):
    """A cancelled request must never permit an open or process the next file."""


def watch_parent_lifetime():
    """Abort a native-owned scan when its application closes its stdin pipe."""
    if os.environ.get('PDF_MAGIC_PARENT_LIFETIME') != '1':
        return
    def watch():
        try:
            os.read(sys.stdin.fileno(), 1)
        except (OSError, ValueError):
            pass
        # Existing native cancellation handlers stop ClamAV's process group.
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=watch, name='parent-lifetime', daemon=True).start()


def native_cancellation_enabled():
    return os.environ.get(NATIVE_CANCELLATION) == '1'


def _cancel_signal(signum, frame):
    raise ScanCancelled('The scan was cancelled; opening was stopped.')


@contextmanager
def cancellation_signals():
    if not native_cancellation_enabled():
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('Native cancellation requires the main thread.')
    tracked = (signal.SIGINT, signal.SIGTERM)
    previous = {sig: signal.getsignal(sig) for sig in tracked}
    try:
        for sig in tracked:
            signal.signal(sig, _cancel_signal)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def terminate_scanner_children(process):
    # An isolated session lets us stop a scanner and its descendants without
    # signalling the PDF opener or other concurrent scan processes.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
    else:
        # A direct scanner may exit while its child processes remain alive.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_scan_command(command, timeout):
    if not native_cancellation_enabled():
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        # Includes cancellation and timeouts: never leave scanner children alive.
        terminate_scanner_children(process)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def cancellable_scan(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with cancellation_signals():
            return function(*args, **kwargs)
    return wrapper


def read_signature_database_version():
    """Read the ClamAV database revisions used for this scan, not the engine version.

    Missing or ambiguous metadata must never be represented as a known version.
    Signature checks and actual scanner verdicts remain authoritative.
    """
    versions = []
    for name in ('main', 'daily', 'bytecode'):
        candidates = [DATABASE / (name + suffix) for suffix in ('.cld', '.cvd')
                      if (DATABASE / (name + suffix)).is_file()]
        if len(candidates) > 1 or (name != 'bytecode' and not candidates):
            return None
        if not candidates:
            continue
        try:
            with candidates[0].open('rb') as source:
                header = source.read(512)
        except OSError:
            return None
        parts = header.split(b':', 3)
        if len(parts) < 3 or parts[0] != b'ClamAV-VDB' or not (
                1 <= len(parts[2]) <= 10 and parts[2].isascii() and parts[2].isdigit()):
            return None
        versions.append(f'{name}={int(parts[2])}')
    return ','.join(versions)



def scanner_path():
    for candidate in ('/opt/homebrew/bin/clamscan', '/usr/local/bin/clamscan', '/usr/local/clamav/bin/clamscan'):
        if os.access(candidate, os.X_OK):
            # Fail before any scanner, cache or launch path can run. A newer
            # executable later on PATH must not mask an unsupported selection.
            require_supported_scanner_version(candidate)
            return candidate
    raise RuntimeError('ClamAV is unavailable. Run the Allow and Open installer again.')


def check_database():
    try:
        age = time.time() - float(STAMP.read_text().strip())
    except (OSError, ValueError):
        raise RuntimeError('Malware signatures are unavailable. Run update-malware-signatures.sh.')
    # Only a real timestamp in the inclusive 48-hour window is acceptable.
    # In particular, float("nan") passes both < and > checks and must fail closed.
    if not 0 <= age <= MAX_DATABASE_AGE:
        raise RuntimeError('Malware signatures have not been checked in 48 hours. Run update-malware-signatures.sh.')
    # Filename matches alone are insufficient: empty placeholders and
    # directories masquerading as main.cvd / daily.cvd are not databases.
    # Do not follow symlinks outside the installed signature directory.
    def has_signature_file(name):
        for suffix in ('.cld', '.cvd'):
            candidate = DATABASE / (name + suffix)
            try:
                if (not candidate.is_symlink() and candidate.is_file() and
                        candidate.stat().st_size > 0):
                    return True
            except OSError:
                # An inaccessible or missing database cannot authorize opening.
                continue
        return False

    if not has_signature_file('daily') or not has_signature_file('main'):
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


def file_identity(path, include_ctime=True):
    """Capture filesystem identity for a file and every app-bundle entry.

    This complements content hashing: replacing a path with identical bytes
    must not silently substitute a different object for the one checked.
    Snapshots are transient and never enter the persistent clean-scan cache.
    """
    entries = [path] + sorted(path.rglob('*')) if path.is_dir() else [path]
    identity = []
    for entry in entries:
        info = entry.lstat()
        name = str(entry.relative_to(path)) if entry != path else ''
        details = (name, info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode),
                   info.st_size, info.st_mtime_ns)
        if include_ctime:
            details += (info.st_ctime_ns,)
        identity.append(details)
    return tuple(identity)


def verify_file_integrity(path, original_digest, original_identity,
                          allow_ctime_change=False):
    """Revalidate bytes and filesystem identity before any launch."""
    expected = (tuple(entry[:-1] for entry in original_identity)
                if allow_ctime_change else original_identity)
    def current_identity():
        return file_identity(path, include_ctime=not allow_ctime_change)
    if (current_identity() != expected or fingerprint(path) != original_digest
            or current_identity() != expected):
        raise RuntimeError('The file changed while checking it; opening was stopped. Try again.')


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
                           '(digest TEXT PRIMARY KEY, scanned_at REAL NOT NULL, '
                           'scanner_version TEXT, signature_database_version TEXT)')
        if 'scanner_version' not in {
                column[1] for column in connection.execute('PRAGMA table_info(clean_scans)')}:
            connection.execute('ALTER TABLE clean_scans ADD COLUMN scanner_version TEXT')
        if 'signature_database_version' not in {
                row[1] for row in connection.execute('PRAGMA table_info(clean_scans)')}:
            connection.execute('ALTER TABLE clean_scans ADD COLUMN signature_database_version TEXT')
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


def cached_scan(digest):
    try:
        with cache_connection() as connection:
            row = connection.execute(
                'SELECT scanned_at, scanner_version, signature_database_version FROM clean_scans WHERE digest = ?',
                (digest.hex(),)).fetchone()
        age = time.time() - row[0] if row else -1
        if 0 <= age < CACHE_TTL:
            return CleanScanResult(status="clean", from_cache=True, scanner_version=row[1],
                                   signature_database_version=row[2])
    except (OSError, sqlite3.Error, TypeError, ValueError):
        # Bad or unavailable caches never provide a clean verdict.
        pass
    return None


def cached_clean(digest):
    return cached_scan(digest) is not None


def remember_clean(digest, scanner_version=None, signature_database_version=None):
    try:
        with cache_connection() as connection:
            now = time.time()
            connection.execute('DELETE FROM clean_scans WHERE scanned_at < ?',
                               (now - CACHE_TTL,))
            connection.execute(
                'INSERT OR REPLACE INTO clean_scans '
                '(digest, scanned_at, scanner_version, signature_database_version) '
                'VALUES (?, ?, ?, ?)',
                (digest.hex(), now, scanner_version, signature_database_version))
    except (OSError, sqlite3.Error):
        # Failure to save the cache does not invalidate a successful scan.
        pass


def scan_engine_version(scanner):
    """Return ClamAV's engine version, not its signature database revision."""
    try:
        output = subprocess.check_output(
            [scanner, '--version'], text=True, timeout=5, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    match = re.match(
        r'^ClamAV ([0-9]+(?:\.[0-9]+){1,3}(?:[-+][A-Za-z0-9._-]+)?)(?:/|\s|$)',
        output.strip())
    return match.group(1) if match else None


def require_supported_scanner_version(scanner):
    """Require a supported ClamAV engine branch before accepting a scanner.

    ClamAV 1.4 LTS and 1.5 are the supported feature branches as of 2026.
    Unknown output, EOL versions, future unreviewed releases and development
    builds cannot authorize a scan or a previously cached clean handoff.
    """
    version = scan_engine_version(scanner)
    if version is None:
        raise RuntimeError(
            'ClamAV scanner version could not be verified. Reinstall ClamAV before opening files.')
    if re.fullmatch(r'1\.(?:4|5)\.[0-9]+', version) is None:
        raise RuntimeError(
            'Unsupported ClamAV scanner version. Install ClamAV 1.4 or 1.5 before opening files.')
    return version


def record_scan_destination(destination):
    """Record the intended launch target separately from clean-scan verdicts."""
    try:
        SCAN_REQUEST_DB.parent.mkdir(parents=True, exist_ok=True)
        # Never follow a user-supplied symlink when preparing the audit database.
        if SCAN_REQUEST_DB.is_symlink() or (
                SCAN_REQUEST_DB.exists() and not SCAN_REQUEST_DB.is_file()):
            raise OSError('The scan request database must be a regular file.')
        SCAN_REQUEST_DB.touch(mode=0o600, exist_ok=True)
        SCAN_REQUEST_DB.chmod(0o600)
        with sqlite3.connect(str(SCAN_REQUEST_DB), timeout=5) as connection:
            connection.execute(
                'CREATE TABLE IF NOT EXISTS scan_requests ('
                'id INTEGER PRIMARY KEY, requested_at REAL NOT NULL, '
                'intended_destination_application TEXT NOT NULL)')
            connection.execute(
                'INSERT INTO scan_requests (requested_at, intended_destination_application) '
                'VALUES (?, ?)', (time.time(), destination))
    except (OSError, sqlite3.Error) as error:
        # A request must not be opened if its intended destination was not recorded.
        raise RuntimeError('Unable to record the scan destination; opening was stopped.') from error


def record_scan_request(application):
    """Record the requesting entry point separately from intended destinations."""
    if not application or len(application) > 128 or any(char in application for char in '\r\n\0'):
        raise ValueError('Invalid requesting application name.')
    SCAN_REQUEST_DB.parent.mkdir(parents=True, exist_ok=True)
    if SCAN_REQUEST_DB.is_symlink() or (SCAN_REQUEST_DB.exists() and not SCAN_REQUEST_DB.is_file()):
        raise RuntimeError('The scan-request database must be a regular file, not a symbolic link.')
    SCAN_REQUEST_DB.touch(mode=0o600, exist_ok=True)
    SCAN_REQUEST_DB.chmod(0o600)
    connection = sqlite3.connect(str(SCAN_REQUEST_DB), timeout=5)
    try:
        with connection:
            connection.execute('CREATE TABLE IF NOT EXISTS scan_request_applications '
                               '(id INTEGER PRIMARY KEY, requested_at REAL NOT NULL, '
                               'requesting_application TEXT NOT NULL)')
            connection.execute('INSERT INTO scan_request_applications '
                               '(requested_at, requesting_application) VALUES (?, ?)',
                               (time.time(), application))
    finally:
        connection.close()



def record_opened_document_origin(document_origin):
    """Best-effort, path-free audit of the document that actually opened.

    The trusted scanner entry point determines "original" versus
    "generated-copy"; a protection label, filename or PDF cannot supply it.
    This is an observation recorded only *after* successful launch, not an
    opening permission or a change to the malware gate. Audit failures never
    make an already-opened document appear to have failed its clean scan.
    """
    if document_origin not in ("original", "generated-copy"):
        return False
    try:
        SCAN_REQUEST_DB.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if SCAN_REQUEST_DB.parent.is_symlink():
            return False
        flags = (os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW |
                 getattr(os, "O_CLOEXEC", 0))
        descriptor = os.open(SCAN_REQUEST_DB, flags, 0o600)
        try:
            details = os.fstat(descriptor)
            if (not stat.S_ISREG(details.st_mode) or
                    details.st_uid != os.getuid() or
                    details.st_nlink != 1 or details.st_mode & 0o077):
                return False
        finally:
            os.close(descriptor)
        with sqlite3.connect(str(SCAN_REQUEST_DB), timeout=5) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS opened_document_origins ("
                "id INTEGER PRIMARY KEY, opened_at REAL NOT NULL, "
                "document_origin TEXT NOT NULL "
                "CHECK (document_origin IN ('original', 'generated-copy')))"
            )
            connection.execute(
                "INSERT INTO opened_document_origins (opened_at, document_origin) "
                "VALUES (?, ?)",
                (time.time(), document_origin),
            )
        return True
    except (OSError, sqlite3.Error, ValueError):
        return False


def remove_quarantine(path):
    """Legacy post-scan hook: retain, never strip, macOS quarantine metadata.

    Keep the existing call site and integration hook for compatibility.
    A clean malware verdict does not cancel macOS Gatekeeper or other
    operating-system protections. This hook deliberately makes no changes.
    """
    return None


@dataclass(frozen=True)
class ScanDetection:
    """ClamAV evidence only; never a decision to open."""
    exit_code: int
    stdout: str
    stderr: str
    detection_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpeningDecision:
    """Scanner policy judgment before independent file-integrity/open checks."""
    allowed: bool
    reason: str = ''
    detection_names: tuple[str, ...] = ()


def capture_detection(completed_process):
    """Record what ClamAV reported, without conferring opening permission."""
    names = ScanResult.from_clamav_output(completed_process.stdout).detection_names
    return ScanDetection(completed_process.returncode, completed_process.stdout,
                         completed_process.stderr, names)


def decide_opening(detection):
    """Apply the existing fail-closed policy; never mutate the detection record.

    A positive decision means only that the result passed the ClamAV gate.
    The file must still pass an independent before/after content check before
    quarantine metadata is retained and an application can be launched.
    """
    # Exit code 1 may also describe heuristic/unscannable items. Never
    # present scanner errors, incomplete results, or heuristics as malware.
    # Retain the exact fail-closed opening decision for all nonzero codes.
    if detection.exit_code == 1 and not detection.stderr.strip():
        if any(not name.startswith('Heuristics.') for name in detection.detection_names):
            return OpeningDecision(
                False, 'Malware was detected; opening was stopped.',
                detection_names=detection.detection_names)
        if detection.detection_names:
            return OpeningDecision(
                False, 'The scanner flagged a suspicious or unscannable item; opening was stopped.',
                detection_names=detection.detection_names)
    if detection.exit_code != 0:
        return OpeningDecision(
            False, 'The malware scan could not finish; opening was stopped.',
            detection_names=detection.detection_names)
    # ClamAV can emit warnings for unreadable or skipped inputs without a
    # detection. An explicit OK with no unexpected output is still required.
    lines = detection.stdout.splitlines()
    if (not any(line.endswith(': OK') for line in lines) or
            any(not line.endswith((': OK', ': Empty file')) for line in lines) or
            detection.stderr.strip()):
        return OpeningDecision(
            False, 'The malware scan did not confirm a complete scan; opening was stopped.',
            detection_names=detection.detection_names)
    return OpeningDecision(True, detection_names=detection.detection_names)


def supported_request_path(item):
    """Reject unsupported path representations and filesystem entry types."""
    if not isinstance(item, (str, os.PathLike)):
        raise RuntimeError('Unsupported scan request type: expected a local filesystem path.')
    try:
        raw_path = os.fspath(item)
    except TypeError:
        raise RuntimeError('Unsupported scan request type: expected a local filesystem path.')
    # The gate handles local paths only, not URL schemes or remote resources.
    if not isinstance(raw_path, str) or not raw_path or '\0' in raw_path:
        raise RuntimeError('Unsupported scan request type: expected a valid local path.')
    if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:(?://|/)', raw_path):
        raise RuntimeError('Unsupported scan request type: URL requests are not supported.')
    if raw_path.lower().endswith('.pdf.icloud'):
        raise RuntimeError('The requested PDF is not available locally; opening was stopped.')
    path = Path(raw_path).expanduser().resolve(strict=True)
    if not path.is_file() and not (path.is_dir() and path.suffix.lower() == '.app'):
        raise RuntimeError('Unsupported scan request type: select a file or application bundle.')
    return path


def _scan_and_open(item, scanner, *, source_url=None, protection_level=None,
                   browser_download_identifier=None, policy_snapshot=None,
                   force_rescan=False, expected_fingerprint=None):
    # The admission-time snapshot persists across queue waits and handoff.
    if policy_snapshot is None:
        policy_snapshot = ACTIVE_SCAN_POLICY.snapshot()
    if type(policy_snapshot) is not ScanSecurityPolicySnapshot:
        raise TypeError('Invalid scan security policy snapshot.')
    path = validate_scan_request(item)
    request_kwargs = {'source_url': source_url}
    if protection_level is not None:
        request_kwargs['protection_level'] = protection_level
    if browser_download_identifier is not None:
        request_kwargs['browser_download_identifier'] = browser_download_identifier
    request = ScanRequest.from_path(path, **request_kwargs)
    is_pdf = path.is_file() and request.file_type == 'pdf'
    if is_pdf:
        verify_local_file_available(path)
    destination = intended_destination(path)
    # The optional fallback is an explicit PDF-only preference. Validate it
    # before scanning or handoff, and never derive it from the
    # default PDF handler (which may recursively invoke this opener).
    fallback = pdf_fallback_application(primary=destination) if is_pdf else None
    record_scan_destination(destination)
    identity = file_identity(path)
    before = fingerprint(path)
    if expected_fingerprint is not None and before != expected_fingerprint:
        raise RuntimeError(GENERATED_OUTPUT_CHANGED_MESSAGE)
    if file_identity(path) != identity:
        raise RuntimeError('The file changed while checking it; opening was stopped. Try again.')
    cache_id = policy_cache_key(before, is_pdf, policy_snapshot)
    performed_scan = False
    scanner_version = None
    signature_version = None
    # Preserve the ordinary scanner's cache-miss check; generated copies must
    # run a fresh scan even if another request cached their identical content.
    def requires_scan():
        if force_rescan:
            return True
        if not cached_clean(cache_id):
            return True
        return False

    # Do not serialize an already cached clean hit. For a miss, a cross-process
    # lock prevents another identical-content request from racing its scan.
    if requires_scan():
        with active_scan_lock(cache_id):
            # Recheck after waiting: the selected file may have changed.
            verify_file_integrity(path, before, identity)
            # Only a completed clean result under this exact policy is reusable.
            if requires_scan():
                signature_version_before = read_signature_database_version()
                if is_pdf:
                    # The engine still alerts on its internal file-size limit (~2 GB).
                    size_options = ('--max-filesize=0', '--max-scansize=0')
                else:
                    size_options = ('--max-filesize=512M', '--max-scansize=1024M')
                try:
                    scan = run_scan_command([
                        scanner, '--database=' + str(DATABASE), '--recursive',
                        '--follow-file-symlinks=2', '--follow-dir-symlinks=2',
                        '--alert-exceeds-max=yes', '--alert-encrypted=yes',
                        *size_options,
                        '--max-scantime=0', '--no-summary', '--', str(path)
                    ], timeout=(policy_snapshot.pdf_timeout_seconds if is_pdf
                                else policy_snapshot.other_timeout_seconds))
                except subprocess.TimeoutExpired:
                    raise RuntimeError('The malware scan timed out; opening was stopped.')
                detection = capture_detection(scan)
                decision = decide_opening(detection)
                if not decision.allowed:
                    failure = RuntimeError(decision.reason)
                    failure.scan_result = ScanResult(decision.detection_names)
                    raise failure
                signature_version_after = read_signature_database_version()
                signature_version = (signature_version_before
                                     if signature_version_before == signature_version_after else None)
                verify_file_integrity(path, before, identity)
                performed_scan = True
                scanner_version = scan_engine_version(scanner)
                remember_clean(cache_id, scanner_version, signature_version)
    verify_file_integrity(path, before, identity)
    if force_rescan and not performed_scan:
        raise RuntimeError('The malware scan did not confirm a complete scan; opening was stopped.')
    # Preserve the completed scan outcome before attempting to launch the file.
    scan_result = (CleanScanResult(status='clean', from_cache=False,
                                   scanner_version=scanner_version,
                                   signature_database_version=signature_version)
                   if performed_scan else cached_scan(cache_id))
    if scan_result is None:
        raise RuntimeError('The clean scan cache could not be verified; opening was stopped.')
    # Cache hits are not proof the file remains downloaded locally.
    if is_pdf:
        verify_local_file_available(path)
    # Verify a destination before opening; keep OS quarantine in place.
    # Fallback never overrides a failed scan, missing local bytes or a changed file.
    verified_fallback = None
    try:
        verify_launch_target(path, target_app=destination if is_pdf else None)
    except RuntimeError:
        if not is_pdf or fallback is None:
            raise
        verify_launch_target(path, target_app=fallback)
        destination = fallback
        # Preserve the initial requested destination and additionally record
        # the fallback handoff; audit failures must block opening.
        record_scan_destination(destination)
    else:
        if is_pdf and fallback is not None:
            try:
                verify_launch_target(path, target_app=fallback)
            except RuntimeError:
                # A failed optional fallback must not block a verified primary.
                pass
            else:
                verified_fallback = fallback
    # Stable legacy hook: leave com.apple.quarantine and Gatekeeper protections intact.
    remove_quarantine(path)
    # Quarantine is no longer stripped; reject unexpected metadata/ctime changes.
    verify_file_integrity(path, before, identity)
    if is_pdf:
        verify_local_file_available(path)
    # The scan engine does not select an application or browser.
    try:
        launch_clean_file(path, target_app=destination if is_pdf else None)
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        if verified_fallback is None:
            raise LaunchFailedError(scan_result, is_pdf=is_pdf) from error
        # Recheck the unchanged, locally available PDF before another launch.
        verify_file_integrity(path, before, identity)
        verify_local_file_available(path)
        record_scan_destination(verified_fallback)
        try:
            launch_clean_file(path, target_app=verified_fallback)
        except (OSError, subprocess.SubprocessError, RuntimeError) as fallback_error:
            raise LaunchFailedError(scan_result, is_pdf=is_pdf) from fallback_error
    # Capture what actually opened, never merely what was requested or scanned.
    # A generated-copy origin is established solely by the validated, forced
    # re-scan entry point, not by user-controlled path or protection metadata.
    record_opened_document_origin(
        'generated-copy' if force_rescan and expected_fingerprint is not None
        else 'original'
    )
    return scan_result


GENERATED_OUTPUT_CHANGED_MESSAGE = (
    'The generated PDF differs from the sanitized copy; opening was stopped.'
)

def _fingerprint_generated_pdf_bytes(contents):
    """Reproduce the existing single-file fingerprint without trusting a path."""
    if type(contents) is not bytes or not contents:
        raise ValueError('Generated PDF contents must be immutable nonempty bytes.')
    digest = hashlib.sha256()
    digest.update(b'file-v1\0')
    digest.update(b'bytes\0' + str(len(contents)).encode('ascii') + b'\0')
    digest.update(contents)
    return digest.digest()


@cancellable_scan
def scan_and_open_generated_copy(item, offer):
    """Re-scan a user-saved sanitized copy before any existing PDF handoff.

    This optional Maximum-only entrypoint never uses a cached clean result.
    Validate the offer again, bind the exact saved PDF bytes to its original
    conversion result, and reuse the complete existing signature freshness,
    ClamAV, file-integrity, destination, quarantine and launch gates.
    """
    # Optional Maximum dependencies are imported only after a generated
    # copy is explicitly requested, never on ordinary Built-in scans.
    from maximum_generated_rescan import verified_generated_pdf_bytes
    generated_bytes = verified_generated_pdf_bytes(offer)
    if generated_bytes is None:
        raise RuntimeError('The sanitized PDF copy could not be verified; opening was stopped.')

    # The output path is supplied by the saving UI, not the untrusted PDF.
    path = supported_request_path(item)
    if path.suffix.lower() != '.pdf' or not path.is_file():
        raise RuntimeError('A saved PDF is required for re-scanning; opening was stopped.')
    expected = _fingerprint_generated_pdf_bytes(generated_bytes)

    # The existing normal scanner may trust a content-addressed cache. A
    # generated output must be freshly scanned regardless of earlier scans,
    # including those of an identical file or of its original source.
    scanner = scanner_path()
    policy_snapshot = ACTIVE_SCAN_POLICY.snapshot()
    with scan_slot():
        check_database()
        return _scan_and_open(
            path, scanner, policy_snapshot=policy_snapshot,
            force_rescan=True, expected_fingerprint=expected,
        )


@cancellable_scan
def scan_and_open(item, scanner, *, source_url=None, protection_level=None, browser_download_identifier=None):
    # Reject unsupported requests before allocating shared scanner queue slots.
    path = supported_request_path(item)
    # Freeze policy before waiting for a slot, not after starting the scanner.
    # Changes are visible to new requests only.
    policy_snapshot = ACTIVE_SCAN_POLICY.snapshot()
    # Both Finder and the native PDF opener must respect the same process-wide cap.
    with scan_slot():
        if source_url is None and protection_level is None and browser_download_identifier is None:
            return _scan_and_open(path, scanner, policy_snapshot=policy_snapshot)
        return _scan_and_open(path, scanner, source_url=source_url,
                              protection_level=protection_level,
                              browser_download_identifier=browser_download_identifier,
                              policy_snapshot=policy_snapshot)


def safe_scan_failure(error):
    # Whitelist only messages controlled by this scanner. In particular,
    # OSError and CalledProcessError can include absolute selected paths.
    if type(error) in (RuntimeError, LaunchFailedError) and str(error) in SAFE_SCAN_FAILURES:
        return str(error)
    return 'The request could not be processed; opening was stopped.'


def main(items):
    watch_parent_lifetime()
    if not items:
        print('No files were selected for scanning.', file=sys.stderr)
        return 1

    valid_items = []
    result = 0
    for index, item in enumerate(items, start=1):
        try:
            validate_scan_request(item.path if isinstance(item, BrowserDownloadRequest) else item)
        except (OSError, RuntimeError) as error:
            print(f'Scan request {index}: {safe_scan_failure(error)}', file=sys.stderr)
            result = 1
        else:
            valid_items.append((index, item))
    if not valid_items:
        return 1

    try:
        scanner = scanner_path()
        check_database()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    for index, item in valid_items:
        try:
            record_scan_request(os.environ.get(REQUESTING_APPLICATION_ENV, 'Command Line'))
            if isinstance(item, BrowserDownloadRequest):
                if item.browser_download_identifier is None:
                    scan_and_open(item.path, scanner)
                else:
                    scan_and_open(item.path, scanner,
                                  browser_download_identifier=item.browser_download_identifier)
            else:
                scan_and_open(item, scanner)
        except ScanCancelled:
            print('The scan was cancelled; opening was stopped.', file=sys.stderr)
            return 1
        except (OSError, RuntimeError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
            print(f'Scan request {index}: {safe_scan_failure(error)}', file=sys.stderr)
            result = 1
    return result


if __name__ == '__main__':
    try:
        requests = parse_scan_requests(sys.argv[1:])
    except ValueError:
        print('Invalid browser download identifier; opening was stopped.', file=sys.stderr)
        sys.exit(2)
    sys.exit(main(requests))
