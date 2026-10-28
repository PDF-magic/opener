"""Explicit, ownership-checked cleanup of Maximum temporary PDF output.

A staged sanitized copy must remain available while the viewer needs its
pathname. Never delete it immediately after a successful launch. The trusted
caller releases the lease when the viewer has finished; failed handoffs must
release it promptly. No user-supplied filename, directory scan, glob or
untrusted PDF property is accepted (opener-0325).
"""
from dataclasses import dataclass
from weakref import WeakKeyDictionary, WeakSet
import os
from pathlib import Path
import stat
import tempfile
import threading

MAX_TEMP_PDF_BYTES = 32 * 1024 * 1024
BLOCK_MESSAGE = "Maximum temporary PDF cleanup failed safely; output was not released."
_DIR_PREFIX = "pdf-magic-safe-copy-"
_FILE_NAME = "safe-copy.pdf"
_LEASES = WeakKeyDictionary()
_RELEASED = WeakSet()
_LOCK = threading.RLock()


class MaximumTemporaryOutputError(RuntimeError):
    """Fixed path-free failure for staging and release errors."""


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid)


def _file_identity(info):
    # Inodes can be immediately recycled after unlink; do not mistake a
    # newly created file for the original owned output on rapid replacement.
    return (*_identity(info), info.st_ctime_ns, info.st_size)


def _is_private_directory(info):
    return stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700


def _is_private_file(info):
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600


@dataclass(frozen=True, eq=False)
class MaximumTemporaryOutput:
    """Unforgeable-in-process, explicitly released in-memory ownership lease."""

    path: Path

    @property
    def released(self) -> bool:
        with _LOCK:
            return self not in _LEASES

    def release(self) -> None:
        """Remove only the original owned file, then its now-empty directory."""
        with _LOCK:
            recorded = _LEASES.get(self)
            if recorded is None:
                # Reject forged leases, but allow a real lease to be idempotent.
                if self in _RELEASED:
                    return
                raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
            directory, file_identity, directory_identity = recorded
            if self.path != directory / _FILE_NAME:
                raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
            try:
                # Check the directory *before* opening and use a descriptor to
                # prevent symlink traversal during the file deletion.
                directory_stat = os.stat(directory, follow_symlinks=False)
                if (_identity(directory_stat) != directory_identity or
                        not _is_private_directory(directory_stat)):
                    raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
                flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                flags |= getattr(os, "O_CLOEXEC", 0)
                directory_fd = os.open(directory, flags)
                try:
                    if _identity(os.fstat(directory_fd)) != directory_identity:
                        raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
                    item = os.stat(_FILE_NAME, dir_fd=directory_fd,
                                   follow_symlinks=False)
                    if (_file_identity(item) != file_identity or
                            not _is_private_file(item)):
                        raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
                    os.unlink(_FILE_NAME, dir_fd=directory_fd)
                    # Never recursively clear unknown contents. A foreign
                    # entry makes rmdir fail instead of being deleted.
                    os.rmdir(directory)
                finally:
                    os.close(directory_fd)
            except (OSError, ValueError, MaximumTemporaryOutputError):
                raise MaximumTemporaryOutputError(BLOCK_MESSAGE) from None
            _LEASES.pop(self, None)
            _RELEASED.add(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()


# Small token registry: callers cannot clean arbitrary paths by constructing
# a lease from a user-controlled directory or by guessing its name.
def stage_maximum_temporary_pdf(contents: bytes) -> MaximumTemporaryOutput:
    """Write one exclusive private PDF and return its explicit cleanup lease.

    Intended for already validated *generated* bytes, not for PDF source paths.
    No output is accepted as a clean verdict or permission to open.
    """
    if (type(contents) is not bytes or
            not 0 < len(contents) <= MAX_TEMP_PDF_BYTES or
            not contents.startswith(b"%PDF-")):
        raise MaximumTemporaryOutputError(BLOCK_MESSAGE)

    directory = None
    file_path = None
    created_identity = None
    try:
        directory = Path(tempfile.mkdtemp(prefix=_DIR_PREFIX))
        directory_info = os.stat(directory, follow_symlinks=False)
        if (directory.name.startswith(_DIR_PREFIX) is False or
                not _is_private_directory(directory_info) or
                directory_info.st_uid != os.geteuid()):
            raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
        file_path = directory / _FILE_NAME
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        flags |= getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(file_path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            info = os.fstat(stream.fileno())
            if (not _is_private_file(info) or
                    info.st_uid != os.geteuid()):
                raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
            created_identity = _identity(info)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
            after = os.fstat(stream.fileno())
            if (_identity(after) != created_identity or
                    after.st_size != len(contents) or
                    not _is_private_file(after)):
                raise MaximumTemporaryOutputError(BLOCK_MESSAGE)
            created_identity = _file_identity(after)
        lease = MaximumTemporaryOutput(file_path)
        with _LOCK:
            _LEASES[lease] = (directory, created_identity, _identity(directory_info))
        return lease
    except Exception:
        if directory is not None:
            # Only the fixed name we created; never recurse or follow links.
            try:
                info = os.stat(directory, follow_symlinks=False)
                if (stat.S_ISDIR(info.st_mode) and
                        info.st_uid == os.geteuid() and
                        stat.S_IMODE(info.st_mode) == 0o700):
                    if file_path is not None and created_identity is not None:
                        try:
                            actual = os.stat(file_path, follow_symlinks=False)
                            if (_identity(actual) == created_identity[:3] and
                                    _is_private_file(actual)):
                                os.unlink(file_path)
                        except OSError:
                            pass
                    os.rmdir(directory)
            except OSError:
                pass
        raise MaximumTemporaryOutputError(BLOCK_MESSAGE) from None
