"""Protect the reader-facing Maximum sanitization limitations contract."""

from pathlib import Path
import ast
import unittest

from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/maximum/limitations.md"
INDEX = ROOT / "docs/README.md"
SOURCE = ROOT / "maximum_sanitized_copy.py"


def constant_integer(expression):
  """Evaluate only integer literals and multiplication from a Python AST."""
  if isinstance(expression, ast.Constant) and type(expression.value) is int:
    return expression.value
  if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Mult):
    left = constant_integer(expression.left)
    right = constant_integer(expression.right)
    if left is not None and right is not None:
      return left * right
  return None


def integer_constants(source):
  """Read numeric source bounds without importing optional PDF dependencies."""
  values = {}
  for node in ast.parse(source).body:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
      continue
    target = node.targets[0]
    if not isinstance(target, ast.Name) or not target.id.startswith("MAX_"):
      continue
    value = constant_integer(node.value)
    if value is not None:
      values[target.id] = value
  return values


class SanitizationDocumentationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = " ".join(GUIDE.read_text(encoding="utf-8").split())
    cls.index = INDEX.read_text(encoding="utf-8")

  def test_guide_is_discoverable_and_maximum_remains_unavailable(self):
    self.assertIn("[sanitization limits](maximum/limitations.md)", self.index)
    self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
    for phrase in ("Maximum is not selectable", "planned", "Built-in",
                   "not an active, automatic PDF"):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.guide.lower())

  def test_no_clean_verdict_or_opening_permission_claim(self):
    for phrase in ("not an antivirus scan", "malware-free",
                   "permits_open=False", "needs_separate_scan=True",
                   "own fresh", "ClamAV scan", "quarantine",
                   "file-integrity", "cache entry", "no copy offer",
                   "not a partially sanitized"):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.guide.lower())

  def test_loss_and_unsupported_cases_are_disclosed(self):
    for phrase in ("searchable", "OCR", "accessibility", "forms",
                   "annotations", "attachments", "links", "signatures",
                   "visual fidelity", "phishing", "password-protected",
                   "XFA", "portfolios", "optional-content layers",
                   "malformed", "timeout", "blocks instead of falling back"):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.guide.lower())

  def test_documented_limits_match_source(self):
    constants = integer_constants(SOURCE.read_text(encoding="utf-8"))
    expected = {
      "MAX_SOURCE_BYTES": 16 * 1024 * 1024,
      "MAX_OUTPUT_BYTES": 32 * 1024 * 1024,
      "MAX_PAGES": 16,
    }
    for name, value in expected.items():
      with self.subTest(name=name):
        self.assertEqual(constants.get(name), value)
    for value in ("16 MiB", "32 MiB", "16 pages", "2,048 pixels",
                  "24 million", "45-second"):
      self.assertIn(value, self.guide)


if __name__ == "__main__":
  unittest.main()
