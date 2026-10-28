# Upgrading newly introduced protection settings (opener-0264)

The installed PDF scan gate supports **one** effective protection policy:
`built-in`. Standard, Enhanced and Maximum are planned and cannot be selected.
The newly introduced `selectedProtectionProfile` preference is **additive** to
the existing version-one configuration schema; no schema version bump is
necessary.

`PDFMagicPolicySettingsUpgrade.upgradeDocument(data)` is the explicit,
in-memory upgrade path for JSON configuration snapshots:

- First migrate unversioned/legacy version-zero snapshots through the
  established, validated version-one migration.
- If `selectedProtectionProfile` is **absent**, add `"built-in"`, then
  validate against the existing strict configuration schema.
- Retain every existing setting (including explicit `false` values), unknown
  fields and custom browser preferences. If the profile was already explicitly
  `"built-in"`, return the validated snapshot **byte for byte**.
- Reject malformed/unsupported profile selections, incompatible future
  schema versions, invalid existing values, and explicitly `null` policy
  values rather than resetting preferences or silently downgrading.
- Repeating the upgrade yields exactly the same bytes.

For existing per-user defaults, `InitialConfiguration.createIfNeeded` uses
`PDFMagicPolicySettingsUpgrade.seedMissingStoredPolicy(defaults:)` to add
only a missing `built-in` identifier under a validated, current schema
marker. Stored overrides or unknown identifiers are retained unchanged and
future/malformed schema versions never trigger mutation. The existing
initialization routine remains responsible for flushing saved changes; the
pure JSON upgrade never persists data.

**Safety boundary:** these operations neither select a new scan policy nor
change ClamAV execution, quarantine, clean-cache approvals, browser
destinations, user notification settings or other scanner-owned data.
Previously saved unsupported profile identifiers remain unsupported and must
not be interpreted as effective protection. Any additional policy setting
must be separately defined and validated before it is added to this upgrade
contract.
