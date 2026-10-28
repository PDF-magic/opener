#!/usr/bin/env python3
"""Real pipe-streaming limits for Maximum isolated PDF analysis."""
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import maximum_output_limits as bounded


def worker(code, contents=b"hello", cap=4096, timeout=5):
    return bounded.run_bounded_worker(
        [sys.executable, "-I", "-B", "-c", code],
        input_bytes=contents, output_limit=cap, timeout=timeout,
        cwd="/", env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"},
    )


class MaximumOutputTests(unittest.TestCase):
    def test_exact_boundary(self):
        outcome = worker("import os;os.read(0,5);os.write(1,b'X'*4096)")
        self.assertEqual(outcome.stdout, b"X" * 4096)
        self.assertEqual(outcome.returncode, 0)

    def test_one_byte_over_and_unbounded_stream(self):
        for program in (
            "import os;os.read(0,5);os.write(1,b'X'*4097)",
            "import os\nwhile True:\n os.write(1,b'X'*65536)",
        ):
            with self.subTest(program=program[:25]):
                before = time.monotonic()
                with self.assertRaises(bounded.MaximumOutputLimitError) as caught:
                    worker(program, timeout=5)
                self.assertEqual(str(caught.exception), bounded.BLOCK_MESSAGE)
                self.assertLess(time.monotonic() - before, 5)

    def test_large_stdin_and_early_stdout_cannot_deadlock(self):
        amount = 2 * 1024 * 1024
        program = (
            "import os\nos.write(1,b'head')\nremaining=" + str(amount) + "\n"
            "while remaining:\n"
            " data=os.read(0,min(65536,remaining))\n"
            " if not data:raise SystemExit(2)\n"
            " remaining-=len(data)\nos.write(1,b'tail')"
        )
        result = worker(program, b"A" * amount, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"headtail")

    def test_timeout_and_nonzero_return(self):
        with self.assertRaises(bounded.MaximumOutputLimitError):
            worker("import time;time.sleep(2)", timeout=0.2)
        self.assertEqual(worker("raise SystemExit(7)").returncode, 7)

    def test_reject_before_process_creation(self):
        normal = {"input_bytes": b"x", "output_limit": 4096, "timeout": 5,
                  "cwd": "/", "env": {"PATH": "/usr/bin"}}
        with patch.object(bounded.subprocess, "Popen") as spawned:
            for changed in (
                {"input_bytes": "text"},
                {"input_bytes": b"x" * (bounded.MAX_INPUT_BYTES + 1)},
                {"output_limit": 4097}, {"output_limit": 0},
                {"timeout": 0}, {"cwd": "/tmp"},
            ):
                with self.subTest(changed=tuple(changed)), self.assertRaises(
                    bounded.MaximumOutputLimitError
                ):
                    bounded.run_bounded_worker([sys.executable], **{**normal, **changed})
            spawned.assert_not_called()

    def test_error_does_not_echo_sensitive_path(self):
        with patch.object(bounded.subprocess, "Popen",
                          side_effect=OSError("/private/file.pdf secret")):
            with self.assertRaises(bounded.MaximumOutputLimitError) as failure:
                worker("pass")
            self.assertEqual(str(failure.exception), bounded.BLOCK_MESSAGE)

    def test_stream_bounded_before_parsing(self):
        code = Path(bounded.__file__).read_text()
        self.assertIn("output_limit - len(output) + 1", code)
        self.assertIn("os.killpg", code)
        self.assertNotIn("subprocess.run(", code)
        import maximum_isolated_analysis as upstream
        self.assertIs(upstream.run_bounded_worker, bounded.run_bounded_worker)
        self.assertEqual(upstream.MAX_RESPONSE_BYTES, 4096)
        gate = (Path(__file__).resolve().parent / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_output_limits", gate)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
