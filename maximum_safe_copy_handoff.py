"""Route a required Maximum safe PDF copy through the existing scan/open gate.

Future Maximum-only handoff primitive (opener-0320), never selected by the
installed Built-in handler. The source is converted, but never a launch target.
An absent/invalid copy, scan failure or launch failure cannot fall back to it.
"""
from dataclasses import dataclass
from enum import Enum
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading

from maximum_sanitized_copy import (
    GENERATED_CONTENT_ORIGIN, MAX_OUTPUT_BYTES, MAX_SOURCE_BYTES,
    OFFER_LABEL, SanitizedCopyOffer,
    _passive_pages, offer_sanitized_pdf_copy,
)
from scan_results import EFFECTIVE_POLICY_ID
from maximum_temporary_output import (
    MaximumTemporaryOutputError, stage_maximum_temporary_pdf,
)


BLOCK_MESSAGE = "Maximum safe-copy handoff could not finish; opening was stopped."


class MaximumSafeCopyError(RuntimeError):
    """A fixed error without document paths, filenames or PDF contents."""


class MaximumCopyDisposition(Enum):
    """Trusted future Maximum policy intent; not a user profile preference."""

    REQUIRED = "required"


@dataclass(frozen=True)
class MaximumSafeCopyHandoff:
    """A separate path handed to the mandatory scanner and native launcher."""

    copy_path: Path
    scanned: bool = True
    original_opened: bool = False
    content_origin: str = GENERATED_CONTENT_ORIGIN
    display_label: str = OFFER_LABEL

    def to_public_metadata(self):
        """Display a generated-copy label without exposing its private path."""
        return {
            "contentOrigin": GENERATED_CONTENT_ORIGIN,
            "isUntouchedOriginal": False,
            "label": OFFER_LABEL,
            "freshlyScanned": True,
            "originalOpened": False,
        }

    def __post_init__(self):
        if (not isinstance(self.copy_path, Path) or not self.copy_path.is_absolute() or
                self.copy_path.suffix.lower() != ".pdf" or
                self.scanned is not True or self.original_opened is not False or
                type(self.content_origin) is not str or
                self.content_origin != GENERATED_CONTENT_ORIGIN or
                self.display_label != OFFER_LABEL):
            raise ValueError("Only a separate scanned copy can be a Maximum handoff")


def _source_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _read_source(path):
    """Read one unchanged ordinary PDF without following its final symlink."""
    if (not (type(path) is str or isinstance(path, Path)) or
            not str(path).startswith("/") or "\x00" in str(path) or
            Path(path).suffix.lower() != ".pdf"):
        raise MaximumSafeCopyError(BLOCK_MESSAGE)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or
                    not 0 < before.st_size <= MAX_SOURCE_BYTES):
                raise MaximumSafeCopyError(BLOCK_MESSAGE)
            contents = stream.read(MAX_SOURCE_BYTES + 1)
            after = os.fstat(stream.fileno())
        on_disk = os.stat(path, follow_symlinks=False)
        if (_source_identity(before) != _source_identity(after) or
                _source_identity(before) != _source_identity(on_disk) or
                len(contents) != before.st_size or
                not contents.startswith(b"%PDF-")):
            raise MaximumSafeCopyError(BLOCK_MESSAGE)
        return contents, _source_identity(before)
    except (OSError, ValueError):
        raise MaximumSafeCopyError(BLOCK_MESSAGE) from None


def _source_unchanged(path, identity):
    try:
        fresh = os.stat(path, follow_symlinks=False)
        return (stat.S_ISREG(fresh.st_mode) and
                _source_identity(fresh) == identity)
    except OSError:
        return False


# Reuse the ownership lease from opener-0325 rather than deleting a
# reconstructed pathname directly. Failed verification never follows a link.
_STAGED_LEASES = {}
_STAGED_LOCK = threading.RLock()


def _stage_private_copy(pdf_bytes):
    """Stage an exclusive owned PDF through the existing symlink-safe lease."""
    try:
        lease = stage_maximum_temporary_pdf(pdf_bytes)
    except MaximumTemporaryOutputError:
        raise MaximumSafeCopyError(BLOCK_MESSAGE) from None
    with _STAGED_LOCK:
        _STAGED_LEASES[lease.path] = lease
    return lease.path


def _validate_staged_copy(path):
    """Reject replaced files, hard links, or swapped directories before use."""
    with _STAGED_LOCK:
        lease = _STAGED_LEASES.get(Path(path))
        if lease is None:
            raise MaximumSafeCopyError(BLOCK_MESSAGE)
        try:
            lease.verify()
        except MaximumTemporaryOutputError:
            raise MaximumSafeCopyError(BLOCK_MESSAGE) from None


def _discard_private_copy(path):
    """Clean only our recorded inode, never an attacker-supplied path."""
    with _STAGED_LOCK:
        key = Path(path)
        lease = _STAGED_LEASES.get(key)
        if lease is None:
            return
        try:
            lease.release()
        except MaximumTemporaryOutputError:
            # A replacement must be left untouched, not unlinked by name.
            return
        _STAGED_LEASES.pop(key, None)


_SCAN_GATE = None
_SCAN_GATE_LOCK = threading.Lock()


def _scan_staged_copy(path, offer):
    """Use the shared mandatory fresh-generated-copy scan and launch gate."""
    global _SCAN_GATE
    with _SCAN_GATE_LOCK:
        if _SCAN_GATE is None:
            gate = Path(__file__).resolve().with_name("scan-and-open.py")
            spec = importlib.util.spec_from_file_location(
                "_maximum_safe_copy_scan_gate", gate)
            if spec is None or spec.loader is None:
                raise MaximumSafeCopyError(BLOCK_MESSAGE)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(spec.name, None)
                raise
            _SCAN_GATE = module
        module = _SCAN_GATE
    return module.scan_and_open_generated_copy(str(path), offer)


def open_required_maximum_safe_copy(source_path, *, disposition):
    """Open only a newly reconstructed copy after its own mandatory scan.

    The future Maximum policy coordinator must first finish the source's
    mandatory checks and select REQUIRED. The generated file is freshly
    scanned even if a matching clean-cache entry already exists. This building block does not
    activate an unavailable profile or infer policy from request metadata.
    Neither scan failure nor converter failure can open the original file.
    """
    if disposition is not MaximumCopyDisposition.REQUIRED:
        raise MaximumSafeCopyError(BLOCK_MESSAGE)
    path = None
    success = False
    try:
        source, source_identity = _read_source(source_path)
        offer = offer_sanitized_pdf_copy(source)
        if (type(offer) is not SanitizedCopyOffer or
                offer.permits_open is not False or
                offer.needs_separate_scan is not True or
                offer.rasterized is not True or
                offer.content_origin != GENERATED_CONTENT_ORIGIN or
                type(offer.pdf_bytes) is not bytes or
                not 0 < len(offer.pdf_bytes) <= MAX_OUTPUT_BYTES or
                offer.pdf_bytes == source or
                not _passive_pages(offer.pdf_bytes, offer.page_count) or
                not _source_unchanged(source_path, source_identity)):
            raise MaximumSafeCopyError(BLOCK_MESSAGE)
        path = _stage_private_copy(offer.pdf_bytes)
        _validate_staged_copy(path)
        if Path(source_path).samefile(path):
            raise MaximumSafeCopyError(BLOCK_MESSAGE)
        result = _scan_staged_copy(path, offer)
        _validate_staged_copy(path)
        if (getattr(result, "status", None) != "clean" or
                getattr(result, "effective_policy_id", None) != EFFECTIVE_POLICY_ID or
                getattr(result, "from_cache", None) is not False):
            raise MaximumSafeCopyError(BLOCK_MESSAGE)
        success = True
        # Leave only the copy available to the launched viewer. The parent
        # private temp directory is eligible for normal OS temp cleanup.
        return MaximumSafeCopyHandoff(path)
    except Exception:
        raise MaximumSafeCopyError(BLOCK_MESSAGE) from None
    finally:
        if not success and path is not None:
            _discard_private_copy(path)
