"""Resolve the *currently deployed* protection policy from saved preferences.

This is a pure, read-only resolution contract. Only the installed Built-in
ClamAV policy is currently active. Planned Standard, Enhanced and Maximum
descriptors are not selectable and may not be used as an alternative scan gate.
Resolving a policy never approves a file, starts a scan or changes settings.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from protection_policy_definitions import (
    BASELINE_CONTROLS,
    FailureDisposition,
    PolicyControl,
)
from protection_profiles import BASELINE_SAFETY_CHECKS


SELECTED_PROFILE_KEY = "selectedProtectionProfile"
ACTIVE_PROFILE_ID = "built-in"


class UnsupportedEffectivePolicy(ValueError):
    """The saved profile cannot be safely resolved to an active policy."""


@dataclass(frozen=True)
class EffectiveProtectionPolicy:
    """Immutable description of the active baseline, NOT a clean verdict."""

    profile_id: str
    required_checks: frozenset[PolicyControl]
    failure_disposition: FailureDisposition
    optional_checks: frozenset[PolicyControl] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.profile_id) is not str or self.profile_id != ACTIVE_PROFILE_ID:
            raise UnsupportedEffectivePolicy("Only the deployed Built-in policy is active")
        if not isinstance(self.required_checks, frozenset) or (
            self.required_checks != frozenset(BASELINE_CONTROLS)
        ):
            raise UnsupportedEffectivePolicy("The mandatory scan checks cannot be weakened")
        if self.failure_disposition is not FailureDisposition.DENY:
            raise UnsupportedEffectivePolicy("The scanner must remain fail-closed")
        if not isinstance(self.optional_checks, frozenset) or self.optional_checks:
            raise UnsupportedEffectivePolicy("Unimplemented checks cannot be activated")


# No alternate policy can be selected or activated by this mapping.
_BUILT_IN_POLICY = EffectiveProtectionPolicy(
    profile_id=ACTIVE_PROFILE_ID,
    required_checks=frozenset(BASELINE_CONTROLS),
    failure_disposition=FailureDisposition.DENY,
)

if frozenset(control.value for control in _BUILT_IN_POLICY.required_checks) != (
    BASELINE_SAFETY_CHECKS
):
    raise UnsupportedEffectivePolicy("Active policy differs from the mandatory safety floor")


def resolve_effective_policy(
    saved_preferences: Mapping[str, object] | None = None,
) -> EffectiveProtectionPolicy:
    """Resolve a trusted snapshot without reading/writing persistence.

    A *missing* selection uses the sole supported Built-in policy. An explicitly
    invalid, unrecognized or planned selection raises rather than silently
    downgrading it to Built-in. Other saved preferences are not inspected,
    changed or allowed to disable any mandatory check.

    Callers must continue to use the existing scanner, quarantine and file
    integrity gates; the returned metadata is never permission to open a file.
    """
    if saved_preferences is None:
        return _BUILT_IN_POLICY
    if not isinstance(saved_preferences, Mapping):
        raise TypeError("Saved preferences must be a mapping")
    if SELECTED_PROFILE_KEY in saved_preferences:
        selection = saved_preferences[SELECTED_PROFILE_KEY]
        if type(selection) is not str or selection != ACTIVE_PROFILE_ID:
            raise UnsupportedEffectivePolicy(
                "The selected protection profile is unsupported; opening is not authorized"
            )
    return _BUILT_IN_POLICY
