# Lower protection preview warnings (opener-0352)

When a user chooses a lower planned tier in Preferences → Protection, a warning
now appears **before** its preview preference is written. The warning names
the current and proposed tiers and explains the reduced *planned* checks. The
user may **Keep current preview** (no write) or **Save lower preview**.
Successful acknowledgement uses the existing validated and error-reporting
preview-save path. Initial, equal-tier, and higher-tier selections retain the
previous immediate-save behavior.

Reset Protection Settings already required confirmation. Its message now
explicitly warns that resetting Enhanced or Maximum to Standard lowers the
planned preview; the same confirmation preserves unrelated preferences.

**Security boundary:** Standard, Enhanced and Maximum remain unavailable as
active scanner policies. The warning is not authorization to weaken the
installed ClamAV gate or to bypass a scan. Signature freshness, file integrity,
quarantine and fail-closed opening remain mandatory. Exceptions and "open
anyway" actions remain unsupported under
[PR #229](https://github.com/PDF-magic/opener/pull/229).
No scanner, cache, handoff, browser choice or user customization is changed.

The dedicated CI workflow runs the downgrade-order, action/confirmation,
persist/cancel and scanner-policy regression. Existing macOS CI compiles the
real SwiftUI application.
