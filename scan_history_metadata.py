"""Private storage of canonical terminal scan metadata (never an opening gate).

This optional API does not enable history collection or apply user-selected
protection tiers. History preference/record-format owners integrate separately.
"""
import json
import math
import os
import time
from pathlib import Path
import re
import sqlite3
import stat

from scan_results import EFFECTIVE_POLICY_ID, ScanResultStatus

HISTORY_DATABASE = (Path.home() / "Library/Application Support/Studio/allow-and-open"
                    / "scan-history" / "scan-history.sqlite3")
RETENTION_DEFAULT_DAYS = 30
RETENTION_ALLOWED_DAYS = (7, 30, 90, 365)
_RETENTION_FILENAME = "retention.json"
_ENGINE_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}(?:[-+][A-Za-z0-9._-]+)?\Z")

# The only on-disk history columns. Reject unreviewed schema extensions,
# including hidden/generated columns, rather than silently accepting a table
# that could retain document content, attachments, URLs, or browsing history.
_HISTORY_COLUMN_CONTRACT = (
    ("id", "INTEGER", 0, 1, 0),
    ("scanned_at", "REAL", 1, 0, 0),
    ("final_status", "TEXT", 1, 0, 0),
    ("scanner_version", "TEXT", 0, 0, 0),
    ("protection_profile_id", "TEXT", 1, 0, 0),
)


class ScanHistoryStorageError(RuntimeError):
    """The optional history store is unavailable; this is not a scan verdict."""



def _retention_days(folder):
    """Read the shared native/Swift JSON preference; absent means 30 days.

    Reject malformed or untrusted preferences rather than silently extending
    retention. Only user-owned regular files inside a private history folder
    may change the policy. This does not enable automatic history collection.
    """
    path = folder / _RETENTION_FILENAME
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return RETENTION_DEFAULT_DAYS
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077 or metadata.st_size > 128):
            raise OSError("Untrusted retention preference.")
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise OSError("Retention preference changed during verification.")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            value = json.load(stream)
        if (type(value) is not dict or set(value) != {"retention_days"}
                or type(value["retention_days"]) is not int
                or value["retention_days"] not in RETENTION_ALLOWED_DAYS):
            raise ValueError("Invalid scan history retention setting.")
        return value["retention_days"]
    finally:
        os.close(descriptor)


def _verify_history_schema(connection):
    columns = tuple(
        (row[1], row[2].upper(), row[3], row[5], row[6])
        for row in connection.execute("PRAGMA table_xinfo(scan_history)")
    )
    if columns != _HISTORY_COLUMN_CONTRACT:
        raise sqlite3.DatabaseError("Unexpected scan history table schema.")


def _delete_expired(connection, *, days, now):
    # Only the canonical optional metadata table, and no operational cache,
    # diagnostics, PDF, or unrelated document data may be deleted.
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise ValueError("Expected a finite UTC epoch-second cleanup time.")
    cutoff = now - (days * 86400)
    cursor = connection.execute(
        "DELETE FROM scan_history WHERE scanned_at < ?", (cutoff,)
    )
    return cursor.rowcount


def prune_expired_history(*, database_path=None, now=None):
    """Delete expired optional history rows on demand without creating a DB.

    Future caller integrations can run this when history is enabled. The
    append API always cleans up automatically in its own transaction.
    Returns deleted row count; storage errors cannot authorize opening.
    """
    path = Path(database_path) if database_path is not None else HISTORY_DATABASE
    if now is None:
        now = time.time()
    if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
        raise ValueError("Expected a finite UTC epoch-second cleanup time.")
    try:
        if not path.parent.exists() and not path.is_symlink():
            return 0
        parent = path.parent.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid()
                or stat.S_IMODE(parent.st_mode) & 0o077):
            raise OSError("Untrusted optional history directory.")
        days = _retention_days(path.parent)
        try:
            descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return 0
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or stat.S_IMODE(metadata.st_mode) & 0o077):
                raise OSError("Untrusted optional history database.")
            current = path.lstat()
            if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise OSError("Optional history changed during cleanup.")
        finally:
            os.close(descriptor)
        with sqlite3.connect(str(path), timeout=5) as connection:
            connection.execute("PRAGMA trusted_schema = OFF")
            _verify_history_schema(connection)
            return _delete_expired(connection, days=days, now=now)
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
        raise ScanHistoryStorageError(
            "Optional scan history could not be expired safely."
        ) from error


def _validate_metadata(scanned_at, final_status, scanner_version, protection_profile_id):
    if type(scanned_at) not in (int, float) or (
            not math.isfinite(scanned_at) or scanned_at < 0):
        raise ValueError("Expected a finite UTC epoch-second scan timestamp.")
    if not isinstance(final_status, ScanResultStatus):
        raise ValueError("Expected a canonical terminal scan status.")
    if scanner_version is not None and (
            type(scanner_version) is not str or len(scanner_version) > 64
            or _ENGINE_VERSION.fullmatch(scanner_version) is None):
        raise ValueError("Expected a verified scanner version or None.")
    # The other named tiers exist only as inactive policy definitions today.
    if protection_profile_id != EFFECTIVE_POLICY_ID:
        raise ValueError("History must identify the actually enforced Built-in profile.")


def _prepare_private_database(path):
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = parent.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
            or stat.S_IMODE(directory.st_mode) & 0o077):
        raise OSError("The scan history directory is not private.")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise OSError("The scan history database is not an owned regular file.")
        os.fchmod(descriptor, 0o600)
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise OSError("The scan history database changed during verification.")
    finally:
        os.close(descriptor)


def store_scan_metadata(*, scanned_at, final_status, scanner_version=None,
                        protection_profile_id=EFFECTIVE_POLICY_ID, database_path=None):
    """Append timestamp, final status, engine version, effective profile only.

    Callers supply independently established terminal data. Unknown versions
    remain NULL. No file names, paths, raw scanner output, or PDF bytes are
    stored. This function does not authorize a scan or file launch.
    """
    _validate_metadata(scanned_at, final_status, scanner_version, protection_profile_id)
    path = Path(database_path) if database_path is not None else HISTORY_DATABASE
    try:
        days = _retention_days(path.parent)
        _prepare_private_database(path)
        with sqlite3.connect(str(path), timeout=5) as connection:
            connection.execute("PRAGMA trusted_schema = OFF")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS scan_history ("
                "id INTEGER PRIMARY KEY, scanned_at REAL NOT NULL, "
                "final_status TEXT NOT NULL, scanner_version TEXT, "
                "protection_profile_id TEXT NOT NULL)"
            )
            # CREATE TABLE IF NOT EXISTS does not validate an existing table.
            # Fail closed if it contains even one unexpected persisted column.
            _verify_history_schema(connection)
            connection.execute(
                "INSERT INTO scan_history "
                "(scanned_at, final_status, scanner_version, protection_profile_id) "
                "VALUES (?, ?, ?, ?)",
                (scanned_at, final_status.value, scanner_version, protection_profile_id),
            )
            # Retention enforcement runs automatically with every append,
            # including removal of a backdated result in the same transaction.
            _delete_expired(connection, days=days, now=time.time())
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as error:
        raise ScanHistoryStorageError(
            "Optional scan history metadata could not be stored."
        ) from error
