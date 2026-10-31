#!/usr/bin/env python3
"""opener-0825: prove macOS Gatekeeper still rejects an untrusted app.

Only a synthetic, disposable app bundle is assessed, never executed. This
test never enables/disables Gatekeeper or changes the user's launch settings.
"""
import importlib.util
import plistlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
AUDIT_SPEC = importlib.util.spec_from_file_location(
    "gatekeeper_quarantine_audit", ROOT / "tools" / "audit_quarantine_removal.py")
audit = importlib.util.module_from_spec(AUDIT_SPEC)
AUDIT_SPEC.loader.exec_module(audit)

ATTRIBUTE = "com.apple.quarantine"
MARKER = b"0081;00000000;PDFMagicOpener;00000000-0000-0000-0000-000000000000"
SPCTL = "/usr/sbin/spctl"
DANGEROUS_SPCTL = re.compile(
    r"\b(?:/usr/sbin/)?spctl\b.{0,180}?--(?:master-|global-)?disable\b",
    re.IGNORECASE | re.DOTALL,
)


def require_gatekeeper_enabled(result):
    """An unavailable or disabled assessment service must not pass the test."""
    lines = (result.stdout + "\n" + result.stderr).strip().splitlines()
    if result.returncode != 0 or "assessments enabled" not in [
        line.strip().lower() for line in lines
    ]:
        raise AssertionError("Gatekeeper assessments are not confirmed enabled")


def require_rejected_unsigned_app(result):
    """An accepted result, spctl usage error, or unavailable service is not proof."""
    output = result.stdout + "\n" + result.stderr
    # macOS can report either a plain denial or a specific invalid-signature
    # diagnosis, such as a broken resource seal, for this unsigned fixture.
    # An unknown error or spctl usage failure is never treated as a denial.
    rejected = re.search(
        r"\b(rejected|denied)\b"
        r"|code (?:object is not signed|has no resources but signature indicates)",
        output, re.I,
    )
    if result.returncode != 1 or not rejected:
        raise AssertionError(
            f"Gatekeeper did not explicitly reject unsigned app "
            f"(status={result.returncode}, output={output[:800]!r})")


def create_unsigned_app(root):
    """Build harmless native app code for assessment; never run it."""
    app = root / "UntrustedFixture.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleExecutable": "UntrustedFixture",
        "CFBundleIdentifier": "test.pdfmagic.gatekeeper.unsigned",
        "CFBundleName": "UntrustedFixture",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": "1",
    }))
    executable = macos / "UntrustedFixture"
    subprocess.run(
        ["/usr/bin/clang", "-x", "c", "-", "-o", str(executable)],
        input="int main(void) { return 0; }\n", text=True,
        capture_output=True, check=True, timeout=30,
    )
    # Apple Silicon linkers may apply ad-hoc signing. Strip any signature from
    # only this disposable fixture, never from installed or user applications.
    signed = subprocess.run(
        ["/usr/bin/codesign", "--verify", str(executable)],
        capture_output=True, text=True, timeout=15,
    )
    if signed.returncode == 0:
        subprocess.run(
            ["/usr/bin/codesign", "--remove-signature", str(executable)],
            capture_output=True, text=True, check=True, timeout=15,
        )
    unsigned = subprocess.run(
        ["/usr/bin/codesign", "--verify", str(executable)],
        capture_output=True, text=True, timeout=15,
    )
    if unsigned.returncode == 0:
        raise AssertionError("Disposable negative-control executable is still signed")
    return app


def read_quarantine(path):
    result = subprocess.run(
        ["/usr/bin/xattr", "-px", ATTRIBUTE, str(path)],
        capture_output=True, check=True, timeout=10,
    )
    return bytes.fromhex(result.stdout.decode("ascii"))


class GatekeeperProtectionTests(unittest.TestCase):
    def test_gatekeeper_disabled_or_unavailable_is_not_a_false_pass(self):
        for code, output in ((0, "assessments disabled\n"),
                             (1, "assessments enabled\n"),
                             (0, ""),
                             (0, "assessments enabled, assessments disabled")):
            with self.subTest(code=code, output=output):
                with self.assertRaises(AssertionError):
                    require_gatekeeper_enabled(
                        subprocess.CompletedProcess([], code, output, ""))
        require_gatekeeper_enabled(subprocess.CompletedProcess(
            [], 0, "assessments enabled\n", ""))

    def test_spctl_must_explicitly_reject_untrusted_code(self):
        for code, output in ((0, "accepted"), (2, "usage: spctl"), (1, "")):
            with self.subTest(code=code, output=output):
                with self.assertRaises(AssertionError):
                    require_rejected_unsigned_app(
                        subprocess.CompletedProcess([], code, "", output))
        require_rejected_unsigned_app(subprocess.CompletedProcess(
            [], 1, "", "UntrustedFixture.app: rejected\nsource=no usable signature"))
        require_rejected_unsigned_app(subprocess.CompletedProcess(
            [], 1, "", "code has no resources but signature indicates they must be present"))
        with self.assertRaises(AssertionError):
            require_rejected_unsigned_app(subprocess.CompletedProcess(
                [], 1, "", "could not contact assessment service"))

    def test_runtime_must_not_add_gatekeeper_disable_calls(self):
        # Reuse the quarantine auditor's tracked-runtime/secret-path filtering.
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--cached"], cwd=ROOT,
            check=True, capture_output=True, timeout=20,
        )
        candidates = []
        for raw in listing.stdout.split(b"\0"):
            if not raw:
                continue
            name = raw.decode("utf-8")
            if not audit.runtime_path(name):
                continue
            if DANGEROUS_SPCTL.search((ROOT / name).read_text(
                    encoding="utf-8", errors="replace")):
                candidates.append(name)
        self.assertEqual(candidates, [], "Runtime must not disable Gatekeeper")
        self.assertIsNotNone(DANGEROUS_SPCTL.search(
            "subprocess.run(['/usr/sbin/spctl', '--master-disable'])"))
        self.assertIsNotNone(DANGEROUS_SPCTL.search(
            "spctl --global-disable"))
        self.assertIsNone(DANGEROUS_SPCTL.search(
            "spctl --status"))

    @unittest.skipUnless(sys.platform == "darwin", "Requires actual macOS spctl")
    def test_macos_rejects_quarantined_unsigned_app_without_changing_policy(self):
        # Fail, rather than silently skipping, if a runner disables Gatekeeper.
        status = subprocess.run([SPCTL, "--status"], capture_output=True,
                                text=True, timeout=15)
        require_gatekeeper_enabled(status)
        with tempfile.TemporaryDirectory(prefix="opener-gatekeeper-") as tmp:
            app = create_unsigned_app(Path(tmp))
            # Only the disposable bundle gets a quarantine marker.
            subprocess.run(
                ["/usr/bin/xattr", "-wx", ATTRIBUTE, MARKER.hex(), str(app)],
                check=True, capture_output=True, timeout=10,
            )
            self.assertEqual(read_quarantine(app), MARKER)
            result = subprocess.run(
                [SPCTL, "--assess", "--type", "execute", "--verbose=2",
                 "--no-cache", str(app)],
                capture_output=True, text=True, timeout=45,
            )
            require_rejected_unsigned_app(result)
            self.assertEqual(read_quarantine(app), MARKER)
        # Assessment must not change the global policy, even on a test runner.
        require_gatekeeper_enabled(subprocess.run(
            [SPCTL, "--status"], capture_output=True, text=True, timeout=15))


if __name__ == "__main__":
    unittest.main()
