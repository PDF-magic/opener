"""Fail-closed validation of the ClamAV argument vectors (opener-0360).

Both supported invocations use fixed options, a trusted absolute executable,
and positional argument arrays rather than a shell. Caller-controlled document
names are supplied only after "--"; descriptive protection metadata cannot
supply ClamAV options. This module never executes a scanner.
"""

import os
from pathlib import Path


class InvalidScannerArguments(RuntimeError):
    """Reject malformed scanner invocations without exposing private paths."""

    def __init__(self):
        super().__init__("Invalid scanner arguments; opening was stopped.")


def _scanner_executable(scanner):
    if (type(scanner) is not str or not os.path.isabs(scanner) or
            any(character in scanner for character in ("\0", "\r", "\n"))):
        raise InvalidScannerArguments()


def _exact_arguments(command, expected):
    if (type(command) not in (list, tuple) or
            len(command) != len(expected) or
            any(type(argument) is not str for argument in command) or
            tuple(command) != expected):
        raise InvalidScannerArguments()


def validate_scanner_arguments(command, *, scanner, database, document, is_pdf, timeout):
    """Verify every argument of the complete malware-scan command before spawn.

    Only the existing PDF and non-PDF scanning modes are accepted. In
    particular, no caller may add flags, omit mandatory checks, rearrange the
    "--" separator, or substitute an unrelated database or input document.
    """
    _scanner_executable(scanner)
    if (not isinstance(database, Path) or not database.is_absolute() or
            any(character in str(database) for character in ("\0", "\r", "\n"))):
        raise InvalidScannerArguments()
    if (not isinstance(document, Path) or not document.is_absolute() or
            "\0" in str(document)):
        raise InvalidScannerArguments()
    if type(is_pdf) is not bool:
        raise InvalidScannerArguments()
    maximum_timeout = 30 * 60 if is_pdf else 180
    if type(timeout) is not int or not 1 <= timeout <= maximum_timeout:
        raise InvalidScannerArguments()

    size_options = (
        ("--max-filesize=0", "--max-scansize=0") if is_pdf else
        ("--max-filesize=512M", "--max-scansize=1024M")
    )
    expected = (
        scanner,
        "--database=" + str(database),
        "--recursive",
        "--follow-file-symlinks=2",
        "--follow-dir-symlinks=2",
        "--alert-exceeds-max=yes",
        "--alert-encrypted=yes",
        *size_options,
        "--max-scantime=0",
        "--no-summary",
        "--",
        str(document),
    )
    _exact_arguments(command, expected)


def validate_scanner_version_arguments(command, *, scanner):
    """Allow only the harmless fixed --version probe for the same executable."""
    _scanner_executable(scanner)
    _exact_arguments(command, (scanner, "--version"))
