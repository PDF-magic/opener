"""Fixed Linux pre-exec launcher for the optional PDF sanitizer memory ceiling."""
import os
import resource
import sys

MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE = 125
EXEC_FAILED_EXIT_CODE = 126


def tighten_address_space_limit(memory_limit_bytes: int) -> bool:
    """Apply and verify a non-increasing hard RLIMIT_AS before exec."""
    if (
        sys.platform != "linux"
        or type(memory_limit_bytes) is not int
        or memory_limit_bytes <= 0
        or not hasattr(resource, "RLIMIT_AS")
    ):
        return False
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = memory_limit_bytes
        for existing in (soft, hard):
            if existing != resource.RLIM_INFINITY:
                ceiling = min(ceiling, existing)
        if ceiling <= 0:
            return False
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        now_soft, now_hard = resource.getrlimit(resource.RLIMIT_AS)
        return now_soft <= ceiling and now_hard <= ceiling
    except (OSError, ValueError, OverflowError, AttributeError):
        return False


def main() -> int:
    if sys.platform != "linux" or len(sys.argv) < 3 or sys.argv[1] != "--":
        return MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE
    command = sys.argv[2:]
    if not command or any(type(arg) is not str or not arg for arg in command):
        return MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE

    # Python -I deliberately omits the script directory; add only this trusted
    # source directory so the immutable memory budget comes from the same module.
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    try:
        from maximum_sanitizer_process import MAX_SANITIZER_MEMORY_BYTES
    except BaseException:
        return MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE
    if not tighten_address_space_limit(MAX_SANITIZER_MEMORY_BYTES):
        return MEMORY_LIMIT_SETUP_FAILED_EXIT_CODE
    try:
        os.execvpe(command[0], command, os.environ)
    except OSError:
        return EXEC_FAILED_EXIT_CODE
    return EXEC_FAILED_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
