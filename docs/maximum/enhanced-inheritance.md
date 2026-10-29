# Maximum inherits every Enhanced protection requirement (opener-0305)

The **Maximum** planned protection tier is cumulative. In
`protection_policy_definitions.py`, its immutable required policy
is derived from the validated **Enhanced** policy, rather than copying a
second independent list of controls.

The inheritance rule is:

- Retain **every Enhanced required control**, with the same `current` or
  `planned` availability and ordering
- Promote every **Enhanced optional control** to **Maximum required**
  (without changing its availability or claiming implementation)
- Retain the four baseline ClamAV, signature freshness, file integrity
  and fail-closed handoff requirements under both tiers
- Reject omitted, duplicate, misclassified, or downgraded controls
  through the existing immutable structured-policy validation

At present this yields all Standard protections, planned PDF structure
validation, and planned isolated behavior analysis under Maximum. As Enhanced
requirements change, constructing Maximum from Enhanced avoids silently
dropping a newly declared check. The profile's stage time limits and resource
budget lookups already consume the resulting required list, so they inherit
the same set without a parallel control list.

These **policy descriptions are not executable scanning pipelines**.
Maximum, Enhanced and Standard remain non-selectable and cannot be
chosen through the effective policy resolver. No planned check is reported
as active, no result authorizes opening, and none of the scanner, ClamAV,
quarantine, cache, signature update, application launch, or saved preference
behavior changes.

`test-maximum-inherits-enhanced.py` verifies both required and
optional Enhanced checks, stable ordering and availability, fail-closed
rejection of missing/downgraded controls, inherited resource/time metadata,
immutability and deployment isolation. CI runs it in addition to the existing
structured-policy and required/optional-check tests.

This task defines **inheritance of the policy contract only**. Integrating
future Enhanced scanner stages, enforcing Maximum-specific additional
controls, and activating the Maximum tier require separately reviewed work.
