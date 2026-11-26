"""Fail-closed overwrite warning for a future Maximum sanitized-copy save UI.

This component never writes, deletes, scans, opens or authorizes a PDF. It
provides the two-stage decision required before a save action can replace
an existing user-selected file (opener-0546).
"""
from dataclasses import dataclass, field
from pathlib import Path
import stat


OVERWRITE_WARNING = (
    "A PDF already exists at this destination. Saving the sanitized copy "
    "would replace the existing file. Choose Replace to continue or Cancel "
    "to keep the existing file."
)
DESTINATION_ERROR = "The PDF save destination cannot be used safely."
DESTINATION_CHANGED = "The PDF save destination changed; review it again."


class SaveDestinationError(RuntimeError):
    """A fixed, path-free error, never containing user-selected filenames."""


def _existing_identity(path):
    """Do not follow a final symlink or mistake a dangling link for absence."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise SaveDestinationError(DESTINATION_ERROR) from None
    # Replacing a directory, device, symlink or hardlinked file is not an
    # ordinary user-confirmable PDF overwrite.
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise SaveDestinationError(DESTINATION_ERROR)
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns,
    )


@dataclass(frozen=True)
class SaveDestinationReview:
    """Snapshot for presenting an explicit overwrite warning, not write access."""

    destination: Path
    _identity: tuple | None = field(repr=False)

    @property
    def requires_confirmation(self):
        return self._identity is not None

    @property
    def warning(self):
        return OVERWRITE_WARNING if self.requires_confirmation else None


def review_sanitized_copy_destination(destination):
    """Inspect a chosen destination before the save UI offers Replace/Cancel."""
    if (not isinstance(destination, (str, Path)) or
            not str(destination).startswith("/") or
            "\x00" in str(destination) or
            Path(destination).suffix.lower() != ".pdf"):
        raise SaveDestinationError(DESTINATION_ERROR)
    path = Path(destination)
    try:
        if not path.parent.is_dir():
            raise SaveDestinationError(DESTINATION_ERROR)
    except (OSError, ValueError):
        raise SaveDestinationError(DESTINATION_ERROR) from None
    return SaveDestinationReview(path, _existing_identity(path))


def require_sanitized_copy_destination_confirmation(review, *, confirmed=False):
    """Refuse an overwrite without an explicit affirmative action.

    Recheck the destination after the warning; a newly created, replaced,
    edited or removed destination invalidates this review. The eventual save
    implementation must ALSO use no-replace creation or an identity-checked
    atomic replacement at the actual write/commit boundary: this preflight
    alone cannot close races between approval and filesystem mutation.
    """
    if type(review) is not SaveDestinationReview:
        raise SaveDestinationError(DESTINATION_ERROR)
    current = _existing_identity(review.destination)
    if current != review._identity:
        raise SaveDestinationError(DESTINATION_CHANGED)
    if review.requires_confirmation and confirmed is not True:
        raise SaveDestinationError(OVERWRITE_WARNING)
