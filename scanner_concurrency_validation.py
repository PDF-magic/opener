"""Fail-closed validation of the installed scanner's bounded concurrency.

The native PDF owner and cross-process gate currently use two fixed slots.
This internal safety check is not an editable scanner configuration setting.
"""

MAX_PERMITTED_CONCURRENT_SCANS = 2


def validate_scanner_concurrency_limit(value):
    """Accept only integer capacities of one or two; never coerce values."""
    if type(value) is not int or not 1 <= value <= MAX_PERMITTED_CONCURRENT_SCANS:
        raise ValueError("Unsupported scanner concurrency limit; opening was stopped.")
    return value
