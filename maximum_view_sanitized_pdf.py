"""Explicit View Sanitized PDF action for the optional future Maximum UI.

This is never wired into the deployed Built-in handler. Only a verified,
in-memory rasterized copy can be viewed, and the *existing* generated-copy
scan-and-open gate must complete a fresh scan before launching the viewer.
"""
from dataclasses import dataclass, field

from maximum_generated_rescan import verified_generated_pdf_bytes
from maximum_safe_copy_handoff import _scan_staged_copy
from maximum_sanitized_copy import CONVERSION_CHANGE_WARNING, GENERATED_CONTENT_ORIGIN
from maximum_temporary_output import (
    MaximumTemporaryOutput, MaximumTemporaryOutputError, stage_maximum_temporary_pdf,
)
from scan_results import EFFECTIVE_POLICY_ID


VIEW_SANITIZED_PDF_LABEL = "View Sanitized PDF"
VIEW_BLOCKED_MESSAGE = "The sanitized PDF could not be viewed safely."


class SanitizedPDFViewError(RuntimeError):
    """Fixed path-free error; never a malware result or opening permission."""


def available_view_sanitized_pdf_action(offer):
    """Display a view action only for a verified, generated, passive copy.

    This is a presentation contract for a future Maximum UI, not a scanner
    verdict; checking availability cannot stage, scan, save or open a file.
    """
    if verified_generated_pdf_bytes(offer) is None:
        return None
    return {
        "label": VIEW_SANITIZED_PDF_LABEL,
        "contentOrigin": GENERATED_CONTENT_ORIGIN,
        "isUntouchedOriginal": False,
        "conversionWarning": CONVERSION_CHANGE_WARNING,
        "requiresExplicitAction": True,
        "requiresFreshScan": True,
        "authorizesOpen": False,
    }


@dataclass(frozen=True, eq=False)
class SanitizedPDFViewSession:
    """Own the temporary copy until the trusted caller knows the viewer is done.

    A successful launch is not evidence that the viewer has stopped reading
    the file. The caller must release this lease *after* the viewer finishes,
    not immediately after the scan-and-open function returns.
    """
    _lease: MaximumTemporaryOutput = field(repr=False)

    @property
    def copy_path(self):
        """Trusted coordination only; never include this path in public UI."""
        return self._lease.path

    def to_public_metadata(self):
        return {
            "label": VIEW_SANITIZED_PDF_LABEL,
            "contentOrigin": GENERATED_CONTENT_ORIGIN,
            "isUntouchedOriginal": False,
            "freshlyScanned": True,
            "originalOpened": False,
            "conversionWarning": CONVERSION_CHANGE_WARNING,
        }

    def release_after_viewer_closes(self):
        """Ownership-checked, idempotent cleanup; never unlink other files."""
        self._lease.release()


def view_sanitized_pdf(offer, *, user_requested=False) -> SanitizedPDFViewSession:
    """Explicitly view only a verified generated copy via the installed scan gate.

    This launches nothing unless the caller affirmatively requests viewing.
    It never opens the original on failure. The existing gate owns ClamAV,
    signature freshness, integrity, destination selection and launch policy.
    """
    if user_requested is not True:
        raise SanitizedPDFViewError(VIEW_BLOCKED_MESSAGE)
    generated = verified_generated_pdf_bytes(offer)
    if generated is None:
        raise SanitizedPDFViewError(VIEW_BLOCKED_MESSAGE)

    lease = None
    try:
        lease = stage_maximum_temporary_pdf(generated)
        lease.verify()
        # The shared gate rejects the cached-clean shortcut and validates the
        # exact bytes against the offer before using the configured PDF viewer.
        scan = _scan_staged_copy(lease.path, offer)
        lease.verify()
        if (getattr(scan, "status", None) != "clean" or
                getattr(scan, "effective_policy_id", None) != EFFECTIVE_POLICY_ID or
                getattr(scan, "from_cache", None) is not False):
            raise SanitizedPDFViewError(VIEW_BLOCKED_MESSAGE)
        return SanitizedPDFViewSession(lease)
    except Exception:
        if lease is not None:
            try:
                lease.release()
            except MaximumTemporaryOutputError:
                # Leave a substituted inode untouched instead of unlinking it.
                pass
        raise SanitizedPDFViewError(VIEW_BLOCKED_MESSAGE) from None
