#!/usr/bin/env python3
"""Read-only checks for the dependency delivery evaluation (opener-0958)."""

import ast
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "docs/dependency-delivery-evaluation.md"


class DependencyDeliveryDecisionTests(unittest.TestCase):
    def test_decision_explicitly_compares_delivery_models_for_all_dependencies(self):
        content = DECISION.read_text(encoding="utf-8")
        for heading in ("External / system-managed", "App-managed installation and updates",
                        "Bundled in app", "Current decision"):
            with self.subTest(heading=heading):
                self.assertIn(heading, content)
        for dependency in ("ClamAV `clamscan` engine", "ClamAV definitions and FreshClam",
                           "Reviewed Swift helper executables",
                           "Optional Enhanced PDF parser"):
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, content)
        self.assertIn("Release decision gate for reconsideration", content)
        self.assertIn("redistribution/license review", content)
        self.assertIn("arm64/x86_64", content)
        self.assertIn("signing and", content)
        self.assertIn("rollback", content)
        self.assertIn("cannot", content)

    def test_runtime_clamav_remains_external_and_version_gated(self):
        source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assignment = next(node for node in tree.body
                          if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name)
                                  and target.id == "CLAMAV_CANDIDATES"
                                  for target in node.targets))
        self.assertEqual(ast.literal_eval(assignment.value), (
            "/opt/homebrew/bin/clamscan",
            "/usr/local/bin/clamscan",
            "/usr/local/clamav/bin/clamscan",
        ))
        self.assertIn("require_executable_path(candidate, allow_symlink=True)", source)
        self.assertIn("require_supported_scanner_version(scanner)", source)
        self.assertIn("check_database()", source)
        self.assertIn("verify_file_integrity(", source)
        self.assertNotIn("import pypdf", source)
        self.assertNotIn("from pypdf import", source)

    def test_packaged_helpers_exclude_scanner_engine_and_parser(self):
        package = ROOT / "scripts/package_application_helpers.py"
        spec = importlib.util.spec_from_file_location("reviewed_helpers", package)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        names = module.HELPER_NAMES
        self.assertIn("verify-pdf-target", names)
        self.assertIn("pdf-magic-native-host", names)
        for excluded in ("PDFOpener", "MakePDFMagicDefault", "clamscan",
                         "freshclam", "pypdf", "python3"):
            self.assertNotIn(excluded, names)
        for name, _definitions, sources in module.HELPERS:
            self.assertTrue(name in names)
            self.assertTrue(all(path.endswith(".swift") for path in sources))

    def test_updater_retains_independent_staged_freshclam(self):
        updater = (ROOT / "update-malware-signatures.sh").read_text(encoding="utf-8")
        self.assertIn("for candidate in /opt/homebrew/bin/freshclam", updater)
        self.assertIn('run_freshclam_with_network_recovery "$updater"', updater)
        self.assertIn('"$scanner" --database="$stage_dir"', updater)
        self.assertIn('"$stage_dir" "$signature_dir"', updater)
        self.assertIn('Another signature update is running', updater)

    def test_optional_parser_stays_out_of_active_installation(self):
        requirements = (ROOT / "requirements-enhanced-pdf.txt").read_text(encoding="utf-8")
        versions = [line.strip() for line in requirements.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(len(versions), 1)
        self.assertRegex(versions[0], r"^pypdf==[0-9]+\\.[0-9]+\\.[0-9]+$")
        installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
        self.assertNotIn("pip install", installer)
        self.assertNotIn("requirements-enhanced-pdf", installer)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("pip install --disable-pip-version-check -r requirements-enhanced-pdf.txt", ci)
        self.assertIn("python3 tests/dependencies/delivery-evaluation.py -v", ci)


if __name__ == "__main__":
    unittest.main()
