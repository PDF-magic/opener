"""Optional generated-copy validation before a mandatory fresh scanner handoff.

Separates the not-yet-selectable Maximum sanitizer dependency from the
installed Built-in scan module. Nothing here can grant permission to open.
"""


def verified_generated_pdf_bytes(offer) -> bytes | None:
    """Return only a strictly validated rasterized offer's immutable bytes."""
    try:
        from maximum_sanitized_copy import (
            GENERATED_CONTENT_ORIGIN, SanitizedCopyOffer, _passive_pages,
            MAX_OUTPUT_BYTES,
        )
        if (type(offer) is not SanitizedCopyOffer or
                offer.permits_open is not False or
                offer.needs_separate_scan is not True or
                offer.rasterized is not True or
                offer.content_origin != GENERATED_CONTENT_ORIGIN or
                not 0 < len(offer.pdf_bytes) <= MAX_OUTPUT_BYTES or
                not _passive_pages(offer.pdf_bytes, offer.page_count)):
            return None
        return offer.pdf_bytes
    except Exception:
        # Optional dependencies may be absent on the active Built-in path.
        return None
