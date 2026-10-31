"""Private storage of canonical terminal scan metadata (never an opening gate).

This optional API does not enable history collection or apply user-selected
protection tiers. History preference/record-format owners integrate separately.
"""
import math
import os
from pathlib import Path
import re
import sqlite3
import stat

from scan_results import EFFECTIVE_POLICY_ID, ScanResultStatus

HISTORY_DATABASE = (Path.home() / "Library/Application Support/Studio/allow-and-open"
                    / "scan-history" / "scan-history.sqlite3")
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
            actual_columns = tuple(
                (row[1], row[2].upper(), row[3], row[5], row[6])
                for row in connection.execute("PRAGMA table_xinfo(scan_history)")
            )
            if actual_columns != _HISTORY_COLUMN_CONTRACT:
                raise sqlite3.DatabaseError("Unexpected scan history table schema.")
            connection.execute(
                "INSERT INTO scan_history "
                "(scanned_at, final_status, scanner_version, protection_profile_id) "
                "VALUES (?, ?, ?, ?)",
                (scanned_at, final_status.value, scanner_version, protection_profile_id),
            )
    except (OSError, sqlite3.Error) as error:
        raise ScanHistoryStorageError(
            "Optional scan history metadata could not be stored."
        ) from error
