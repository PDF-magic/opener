"""Pure validation for versioned PDF Magic Opener configuration values.

The file loader and schema belong to separate checklist tasks. This module
never reads or writes files.
"""
from copy import deepcopy


class UnsupportedSettingValue(ValueError):
  """A saved setting conflicts with its supported configuration contract."""


# The installed Python and native scan gates both provide exactly two slots.
# A future optional setting may select one or two, never allocate extra slots.
# Merely validating the value does not activate a configurable scan queue.
MAX_PERMITTED_CONCURRENT_SCANS = 2
SCANNER_CONCURRENCY_KEY = "maxConcurrentScans"


def validate_scanner_concurrency_limit(value):
  """Reject invalid or unsafe requested scanner capacity without coercion."""
  if type(value) is not int or not 1 <= value <= MAX_PERMITTED_CONCURRENT_SCANS:
    raise UnsupportedSettingValue("Unsupported scanner concurrency limit")
  return value


def validate_configuration(settings, *, defaults, allowed_values=None):
  """Validate existing values and fill only missing supported settings.

  Defaults define supported keys and safe values. Optional allowed_values
  restricts enumerated settings. Unknown keys are retained for compatibility.
  """
  if not isinstance(settings, dict) or not isinstance(defaults, dict):
    raise TypeError("Settings and defaults must be mappings")
  if any(not isinstance(key, str) for key in (*settings, *defaults)):
    raise TypeError("Configuration keys must be strings")
  allowed_values = {} if allowed_values is None else allowed_values
  if not isinstance(allowed_values, dict) or not set(allowed_values).issubset(defaults):
    raise ValueError("Value restrictions must describe supported settings")
  # Validate any declared default as well as explicit saved settings. Reserve
  # this key even before the optional configuration UI is implemented so that
  # unsupported values cannot pass through as unvalidated extension metadata.
  if SCANNER_CONCURRENCY_KEY in defaults:
    validate_scanner_concurrency_limit(defaults[SCANNER_CONCURRENCY_KEY])
  result = deepcopy(defaults)
  for key, value in settings.items():
    if key == SCANNER_CONCURRENCY_KEY:
      validate_scanner_concurrency_limit(value)
    if key in defaults:
      expected = defaults[key]
      if type(value) is not type(expected):
        raise UnsupportedSettingValue(f"Unsupported value type for {key}")
      if key in allowed_values:
        choices = allowed_values[key]
        if not any(type(value) is type(choice) and value == choice for choice in choices):
          raise UnsupportedSettingValue(f"Unsupported value for {key}")
    result[key] = deepcopy(value)
  return result
