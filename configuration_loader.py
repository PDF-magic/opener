"""Read versioned PDF Magic Opener settings without modifying user data.

The schema, defaults and storage path belong to separate checklist tasks.
Callers supply those decisions rather than introducing competing ones here.
A missing file returns a private copy of the supplied defaults; corrupt,
unsafe or unsupported files fail closed with ConfigurationLoadError.
"""

import copy
import json
import os
import stat
from pathlib import Path

MAX_CONFIGURATION_BYTES = 65536


class ConfigurationLoadError(ValueError):
  """The existing configuration cannot be safely loaded."""


def _no_duplicate_keys(pairs):
  result = {}
  for key, value in pairs:
    if key in result:
      raise ConfigurationLoadError("Duplicate configuration key: " + key)
    result[key] = value
  return result


def load_configuration(path, *, defaults, version):
  """Load a versioned JSON object without writes or implicit migrations.

  The supplied defaults and version are owned by the configuration schema.
  Only missing top-level keys inherit defaults. Explicit user values and
  unknown keys remain intact for the schema layer to validate or migrate.
  """
  if not isinstance(defaults, dict) or type(version) is not int or version < 1:
    raise ValueError("A defaults mapping and positive integer version are required")
  if defaults.get("version") != version:
    raise ValueError("Default configuration version does not match schema version")

  path = Path(path)
  try:
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
  except FileNotFoundError:
    return copy.deepcopy(defaults)
  except OSError as exc:
    raise ConfigurationLoadError("Cannot safely open configuration directory") from exc

  try:
    try:
      fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    except FileNotFoundError:
      return copy.deepcopy(defaults)
    except OSError as exc:
      raise ConfigurationLoadError("Cannot safely open configuration file") from exc
    try:
      details = os.fstat(fd)
      if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_CONFIGURATION_BYTES:
        raise ConfigurationLoadError("Configuration must be a bounded regular file")
      with os.fdopen(fd, "rb", closefd=False) as handle:
        data = handle.read(MAX_CONFIGURATION_BYTES + 1)
      if len(data) > MAX_CONFIGURATION_BYTES:
        raise ConfigurationLoadError("Configuration is too large")
    except OSError as exc:
      raise ConfigurationLoadError("Cannot read configuration file") from exc
    finally:
      os.close(fd)
  finally:
    os.close(parent_fd)

  try:
    parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                          ConfigurationLoadError("Non-finite number in configuration")))
  except (ValueError, UnicodeError) as exc:
    raise ConfigurationLoadError("Invalid configuration JSON") from exc

  if not isinstance(parsed, dict):
    raise ConfigurationLoadError("Configuration root must be an object")
  if type(parsed.get("version")) is not int or parsed["version"] != version:
    raise ConfigurationLoadError("Unsupported configuration schema version")

  result = copy.deepcopy(defaults)
  result.update(parsed)
  return result
