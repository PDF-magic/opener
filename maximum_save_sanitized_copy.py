"""Optional, explicit Save Sanitized Copy action for future Maximum.

Never opens a viewer or alters the source. A verified generated offer is
freshly scanned in a private owned temporary file before an exclusive save.
The installed Built-in profile remains unchanged and Maximum is not enabled.
"""
import importlib.util
import os
from pathlib import Path
import stat
import sys
import threading

from maximum_generated_rescan import verified_generated_pdf_bytes
from maximum_temporary_output import (
    MaximumTemporaryOutputError, stage_maximum_temporary_pdf,
)
from scan_results import EFFECTIVE_POLICY_ID

SAVE_BLOCKED_MESSAGE = "The sanitized PDF copy could not be saved safely."
_SCAN_GATE = None
_SCAN_LOCK = threading.Lock()


class SanitizedCopySaveError(RuntimeError):
    """Fixed, path-free user-facing failure; never a clean or open verdict."""


def _scan_staged_without_open(path, offer):
    """Reuse the exact installed fresh-scan gate, without launching a viewer."""
    global _SCAN_GATE
    with _SCAN_LOCK:
        if _SCAN_GATE is None:
            gate = Path(__file__).resolve().with_name("scan-and-open.py")
            spec = importlib.util.spec_from_file_location(
                "_maximum_save_only_scan_gate", gate
            )
            if spec is None or spec.loader is None:
                raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(spec.name, None)
                raise
            _SCAN_GATE = module
        module = _SCAN_GATE
    return module.scan_generated_copy_without_open(str(path), offer)


def _destination_path(destination):
    if (not isinstance(destination, (str, Path)) or
            "\x00" in str(destination)):
        raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)
    path = Path(destination)
    if (not path.is_absolute() or path.suffix.lower() != ".pdf" or
            ".." in path.parts or not path.name):
        raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)
    return path


def _save_exclusive(path, data):
    """Pin the destination directory and never overwrite an existing entry."""
    directory_fd = None
    created_identity = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory_fd = os.open(path.parent, flags)
        parent = os.fstat(directory_fd)
        selected_parent = os.stat(path.parent, follow_symlinks=False)
        if (not stat.S_ISDIR(parent.st_mode) or
                (parent.st_dev, parent.st_ino) !=
                (selected_parent.st_dev, selected_parent.st_ino)):
            raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path.name, flags, 0o600, dir_fd=directory_fd)
        with os.fdopen(descriptor, "wb") as output:
            first = os.fstat(output.fileno())
            created_identity = (first.st_dev, first.st_ino)
            if (not stat.S_ISREG(first.st_mode) or
                    stat.S_IMODE(first.st_mode) != 0o600 or
                    first.st_nlink != 1):
                raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            last = os.fstat(output.fileno())

        saved = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        parent_now = os.stat(path.parent, follow_symlinks=False)
        if (not stat.S_ISREG(saved.st_mode) or saved.st_nlink != 1 or
                (saved.st_dev, saved.st_ino) != created_identity or
                (last.st_dev, last.st_ino, last.st_size) !=
                (saved.st_dev, saved.st_ino, len(data)) or
                (parent_now.st_dev, parent_now.st_ino) !=
                (parent.st_dev, parent.st_ino)):
            raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)
        return path
    except Exception:
        # Do not remove a replaced entry or follow an attacker-supplied link.
        if directory_fd is not None and created_identity is not None:
            try:
                saved = os.stat(path.name, dir_fd=directory_fd,
                                follow_symlinks=False)
                if ((saved.st_dev, saved.st_ino) == created_identity and
                        stat.S_ISREG(saved.st_mode) and saved.st_nlink == 1):
                    os.unlink(path.name, dir_fd=directory_fd)
            except OSError:
                pass
        raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE) from None
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def save_sanitized_copy(offer, destination, *, user_confirmed=False) -> Path:
    """Persist a generated PDF only after explicit choice and a fresh clean scan.

    Return the newly created path. Nothing here authorizes opening it; a later
    open is independently subject to the installed scanner and app policy.
    """
    if user_confirmed is not True:
        raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)
    path = _destination_path(destination)
    generated = verified_generated_pdf_bytes(offer)
    if generated is None:
        raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)

    lease = None
    try:
        lease = stage_maximum_temporary_pdf(generated)
        lease.verify()
        scan = _scan_staged_without_open(lease.path, offer)
        lease.verify()
        if (getattr(scan, "status", None) != "clean" or
                getattr(scan, "effective_policy_id", None) != EFFECTIVE_POLICY_ID or
                getattr(scan, "from_cache", None) is not False):
            raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE)
        return _save_exclusive(path, generated)
    except Exception:
        raise SanitizedCopySaveError(SAVE_BLOCKED_MESSAGE) from None
    finally:
        if lease is not None:
            try:
                lease.release()
            except MaximumTemporaryOutputError:
                # Ownership mismatch: never delete a substituted temp entry.
                pass
