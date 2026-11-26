"""Pure validation for versioned PDF Magic Opener configuration values.

The file loader and schema belong to separate checklist tasks. This module
never reads or writes files.
"""
from copy import deepcopy


class UnsupportedSettingValue(ValueError):
  """A saved setting conflicts with its supported configuration contract."""


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
  result = deepcopy(defaults)
  for key, value in settings.items():
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
