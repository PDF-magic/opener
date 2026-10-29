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


# These are upper bounds for proposed non-PDF scanner limits, in MiB.
# Nothing in this module enables editing the installed Built-in scan policy.
MAX_NON_PDF_FILE_MIB = 512
MAX_NON_PDF_SCAN_MIB = 1024


def validated_file_size_options(*, is_pdf, file_limit_mib=None, scan_limit_mib=None):
    """Validate proposed ClamAV file/aggregate limits before formatting flags.

    Standalone PDFs retain the existing unlimited *configured* size options.
    For other files and app bundles, only positive integer MiB values up to
    the Built-in caps are permissible, with aggregate >= per-file. Callers
    cannot use zero, booleans, floats, negative values, or a larger setting
    to disable or relax non-PDF size enforcement.

    This validates potential values; the installed scanner still passes only
    its fixed defaults to validate_scanner_arguments, not user overrides.
    """
    if type(is_pdf) is not bool:
        raise InvalidScannerArguments()
    if is_pdf:
        for value in (file_limit_mib, scan_limit_mib):
            if value is not None and (type(value) is not int or value != 0):
                raise InvalidScannerArguments()
        return ("--max-filesize=0", "--max-scansize=0")

    file_limit = MAX_NON_PDF_FILE_MIB if file_limit_mib is None else file_limit_mib
    scan_limit = MAX_NON_PDF_SCAN_MIB if scan_limit_mib is None else scan_limit_mib
    if (type(file_limit) is not int or type(scan_limit) is not int or
            not 1 <= file_limit <= MAX_NON_PDF_FILE_MIB or
            not 1 <= scan_limit <= MAX_NON_PDF_SCAN_MIB or
            scan_limit < file_limit):
        raise InvalidScannerArguments()
    return (f"--max-filesize={file_limit}M", f"--max-scansize={scan_limit}M")


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

    size_options = validated_file_size_options(is_pdf=is_pdf)
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
