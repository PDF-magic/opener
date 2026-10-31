"""Kernel-enforced filesystem confinement for the optional PDF parser worker.

The PDF arrives through stdin; no document path is granted. Refuse parsing if
the OS cannot install a read-only runtime allowlist. This is not an opening
authorization and is never used by the installed Built-in scanner.
"""

import ctypes
import os
from pathlib import Path
import sys


BLOCK_MESSAGE = "PDF parser filesystem isolation is unavailable; opening was stopped."
# These are the only repository files the worker imports after confinement.
_PARSER_MODULES = ("pdf_structure_parser.py", "pdf_stream_lengths.py")
_MACOS_PROFILE = """(version 1)
(deny default)
(allow sysctl-read)
(allow file-read-metadata (subpath "/"))
(allow file-read*
    (literal "/")
    (literal (param "WORKER"))
    (literal (param "PARSER"))
    (literal (param "STREAMS"))
    (subpath (param "PYTHON_PREFIX"))
    (subpath (param "BASE_PREFIX"))
    (subpath "/System")
    (subpath "/usr/bin")
    (subpath "/usr/lib")
    (subpath "/usr/share")
    (subpath "/bin")
    (subpath "/sbin")
    (subpath "/Library/Developer/CommandLineTools")
    (subpath "/Library/Frameworks")
    (literal "/dev/null")
    (literal "/dev/urandom"))
(allow file-map-executable
    (subpath (param "PYTHON_PREFIX"))
    (subpath (param "BASE_PREFIX"))
    (subpath "/System")
    (subpath "/usr/lib")
    (subpath "/Library/Frameworks"))
(deny file-write*)
(deny process-fork)
(deny network*)
"""
# Landlock syscall numbers on supported Linux architectures.
_LANDLOCK_CREATE_RULESET = 444
_LANDLOCK_ADD_RULE = 445
_LANDLOCK_RESTRICT_SELF = 446
_LANDLOCK_RULE_PATH_BENEATH = 1
_LANDLOCK_VERSION = 1
_PR_SET_NO_NEW_PRIVS = 38
_FS_READ_FILE = 1 << 2
_FS_READ_DIR = 1 << 3
_FS_ABI1_RIGHTS = (1 << 13) - 1  # execute, read, write, remove, create
_FS_REFER = 1 << 13
_FS_TRUNCATE = 1 << 14
_FS_IOCTL_DEV = 1 << 15


class ParserFilesystemConfinementError(RuntimeError):
  """A fixed, path-free failure to establish the mandatory parser sandbox."""


class _RulesetAttr(ctypes.Structure):
  _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
  _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]


def _trusted_paths():
  """Resolve the fixed worker and module files plus interpreter runtime roots."""
  root = Path(__file__).resolve(strict=True).parent
  paths = (
    Path(root / "timed_pdf_structure_worker.py").resolve(strict=True),
    *(Path(root / name).resolve(strict=True) for name in _PARSER_MODULES),
  )
  if any(path.parent != root or not path.is_file() for path in paths):
    raise ValueError("Unexpected parser support path")
  prefixes = tuple(dict.fromkeys(
    str(Path(prefix).resolve(strict=True))
    for prefix in (sys.prefix, sys.base_prefix)
  ))
  if any(prefix == "/" or not Path(prefix).is_dir() for prefix in prefixes):
    raise ValueError("Unsafe Python runtime root")
  return tuple(str(path) for path in paths), prefixes


def _sbpl_literal(path):
  # A quoted, canonical sandbox literal cannot contain SBPL escape syntax.
  if (not path.startswith("/") or
      any(character in path for character in ('"', "\\", "\x00")) or
      any(ord(character) < 32 for character in path)):
    raise ValueError("Invalid sandbox path")
  return '"' + path + '"'


def _apply_macos(paths, prefixes):
  worker, parser, streams = paths
  profile = _MACOS_PROFILE
  for name, path in (
      ("WORKER", worker), ("PARSER", parser), ("STREAMS", streams),
      ("PYTHON_PREFIX", prefixes[0]), ("BASE_PREFIX", prefixes[-1]),
  ):
    profile = profile.replace('(param "' + name + '")', _sbpl_literal(path))
  if '(param "' in profile:
    raise ValueError("Unresolved sandbox parameter")
  library = ctypes.CDLL("/usr/lib/libsandbox.dylib", use_errno=True)
  initialize = library.sandbox_init
  initialize.argtypes = [ctypes.c_char_p, ctypes.c_uint64,
                         ctypes.POINTER(ctypes.c_char_p)]
  initialize.restype = ctypes.c_int
  error = ctypes.c_char_p()
  try:
    if initialize(profile.encode("utf-8"), 0, ctypes.byref(error)) != 0:
      raise RuntimeError("Sandbox installation failed")
  finally:
    if error.value:
      library.sandbox_free_error.argtypes = [ctypes.c_char_p]
      library.sandbox_free_error(error)


def _apply_linux(paths, prefixes):
  # Landlock restricts the running thread and its descendants. Both file
  # reads and all available write/create/remove operations are handled.
  if os.uname().machine not in ("x86_64", "aarch64"):
    raise RuntimeError("Unsupported Landlock syscall architecture")
  libc = ctypes.CDLL(None, use_errno=True)
  libc.syscall.restype = ctypes.c_long

  def syscall(number, *args):
    result = libc.syscall(number, *args)
    if result < 0:
      raise OSError(ctypes.get_errno(), "Landlock operation failed")
    return result

  abi = syscall(_LANDLOCK_CREATE_RULESET, 0, 0, _LANDLOCK_VERSION)
  handled = _FS_ABI1_RIGHTS
  if abi >= 2:
    handled |= _FS_REFER
  if abi >= 3:
    handled |= _FS_TRUNCATE
  if abi >= 5:
    handled |= _FS_IOCTL_DEV
  ruleset_attr = _RulesetAttr(handled)
  ruleset = syscall(_LANDLOCK_CREATE_RULESET, ctypes.byref(ruleset_attr),
                    ctypes.sizeof(ruleset_attr), 0)
  try:
    for path, rights in (
        *((prefix, _FS_READ_FILE | _FS_READ_DIR) for prefix in prefixes),
        *((path, _FS_READ_FILE) for path in paths),
        *((library, _FS_READ_FILE | _FS_READ_DIR)
          for library in ("/usr/lib", "/usr/lib64", "/lib", "/lib64")
          if os.path.isdir(library)),
        ("/dev/null", _FS_READ_FILE),
        ("/dev/urandom", _FS_READ_FILE),
    ):
      fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
      try:
        rule = _PathBeneathAttr(rights, fd)
        syscall(_LANDLOCK_ADD_RULE, ruleset, _LANDLOCK_RULE_PATH_BENEATH,
                ctypes.byref(rule), 0)
      finally:
        os.close(fd)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                          ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
      raise RuntimeError("Privilege restriction failed")
    syscall(_LANDLOCK_RESTRICT_SELF, ruleset, 0)
  finally:
    os.close(ruleset)


def confine_parser_filesystem():
  """Apply kernel filesystem restrictions before importing the PDF parser.

  No non-macOS/non-Linux fallback, broad home/tmp access, writable path,
  source-PDF pathname, or user-provided sandbox rule is permitted.
  """
  try:
    paths, prefixes = _trusted_paths()
    if sys.platform == "darwin":
      _apply_macos(paths, prefixes)
    elif sys.platform == "linux":
      _apply_linux(paths, prefixes)
    else:
      raise RuntimeError("Unsupported parser sandbox platform")
  except Exception:
    raise ParserFilesystemConfinementError(BLOCK_MESSAGE) from None
