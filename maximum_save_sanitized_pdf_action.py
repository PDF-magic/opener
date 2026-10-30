"""Maximum-only Save Sanitized PDF interface action (opener-0554).

The interface offers this action only for an independently verified generated
SanitizedCopyOffer. It delegates actual saving to opener-0544's exclusive,
freshly scanned save gate. No file is opened and Maximum is not enabled.
"""
from pathlib import Path

from maximum_generated_rescan import verified_generated_pdf_bytes
from maximum_sanitized_copy import CONVERSION_CHANGE_WARNING, GENERATED_CONTENT_ORIGIN
from maximum_save_sanitized_copy import save_sanitized_copy

SAVE_SANITIZED_PDF_LABEL = "Save Sanitized PDF"
ACTION_BLOCKED_MESSAGE = "The sanitized PDF could not be saved safely."


class SaveSanitizedPDFActionError(RuntimeError):
    """Path-free error; never an opening or scanner verdict."""


def available_save_sanitized_pdf_action(offer):
    """Return only fixed, safe UI metadata for a verified generated offer."""
    if verified_generated_pdf_bytes(offer) is None:
        return None
    return {
        "label": SAVE_SANITIZED_PDF_LABEL,
        "contentOrigin": GENERATED_CONTENT_ORIGIN,
        "isUntouchedOriginal": False,
        "conversionWarning": CONVERSION_CHANGE_WARNING,
        "requiresExplicitAction": True,
        "requiresDestinationSelection": True,
        "requiresFreshScan": True,
        "authorizesOpen": False,
        "allowsOverwrite": False,
    }


def save_sanitized_pdf_action(
    offer, *, user_requested=False, choose_destination=None,
) -> Path | None:
    """Run the trusted UI's optional save flow; return None on user Cancel.

    The coordinator supplies an already verified in-memory offer and a trusted
    destination-picker callable (such as opener-0545). The picker must be
    invoked only after an explicit click and valid offer. The destination is
    not a clean verdict or permission to overwrite; opener-0544 revalidates
    the offer, enforces exclusive creation and runs the existing ClamAV gate.
    """
    if (user_requested is not True or
            not callable(choose_destination) or
            available_save_sanitized_pdf_action(offer) is None):
        raise SaveSanitizedPDFActionError(ACTION_BLOCKED_MESSAGE)
    try:
        destination = choose_destination()
    except Exception:
        raise SaveSanitizedPDFActionError(ACTION_BLOCKED_MESSAGE) from None
    if destination is None:
        # Cancel is not an error and must not stage, scan, write or open.
        return None
    try:
        # A selected pathname is untrusted. The underlying save contract
        # rejects non-PDF/relative paths, existing files and symlinks.
        return save_sanitized_copy(offer, destination, user_confirmed=True)
    except Exception:
        raise SaveSanitizedPDFActionError(ACTION_BLOCKED_MESSAGE) from None
