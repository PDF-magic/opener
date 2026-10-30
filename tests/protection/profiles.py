#!/usr/bin/env python3
"""Contract for defined, non-selectable protection tiers (opener-0246)."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from protection_profiles import (
    BASELINE_SAFETY_CHECKS,
    PROTECTION_PROFILES,
    ProtectionProfileID,
    protection_profile_definition,
)


ROOT = Path(__file__).resolve().parents[2]


class ProtectionProfileDefinitionTests(unittest.TestCase):
    def test_three_stable_identifiers_and_display_names(self):
        expected = (
            (ProtectionProfileID.STANDARD, "standard", "Standard", 1),
            (ProtectionProfileID.ENHANCED, "enhanced", "Enhanced", 2),
            (ProtectionProfileID.MAXIMUM, "maximum", "Maximum", 3),
        )
        self.assertEqual(tuple(ProtectionProfileID), tuple(row[0] for row in expected))
        self.assertEqual(set(PROTECTION_PROFILES), set(ProtectionProfileID))
        for identifier, raw_value, name, precedence in expected:
            with self.subTest(profile=name):
                definition = protection_profile_definition(identifier)
                self.assertEqual(identifier.value, raw_value)
                self.assertEqual(definition.identifier, identifier)
                self.assertEqual(definition.display_name, name)
                self.assertEqual(definition.precedence, precedence)
                self.assertTrue(definition.summary)

    def test_every_tier_retains_mandatory_safety_floor_and_is_inactive(self):
        required = {
            "clamav_scan_gate",
            "signature_freshness",
            "file_integrity",
            "fail_closed_handoff",
        }
        self.assertEqual(BASELINE_SAFETY_CHECKS, frozenset(required))
        for definition in PROTECTION_PROFILES.values():
            with self.subTest(profile=definition.display_name):
                self.assertFalse(definition.selectable)
                self.assertTrue(BASELINE_SAFETY_CHECKS.issubset(definition.required_safety_checks))
                self.assertIsInstance(definition.required_safety_checks, frozenset)
        self.assertIn("not implemented", PROTECTION_PROFILES[ProtectionProfileID.ENHANCED].summary)
        self.assertIn("not implemented", PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].summary)

    def test_catalog_and_definitions_are_immutable_and_reject_unvalidated_ids(self):
        standard = protection_profile_definition(ProtectionProfileID.STANDARD)
        with self.assertRaises(FrozenInstanceError):
            standard.selectable = True
        with self.assertRaises(TypeError):
            PROTECTION_PROFILES[ProtectionProfileID.STANDARD] = standard
        with self.assertRaises(AttributeError):
            standard.required_safety_checks.add("unsafe_override")
        with self.assertRaises(ValueError):
            ProtectionProfileID("unsupported")
        for invalid in ("standard", None, 1, True):
            with self.subTest(invalid=invalid), self.assertRaises(TypeError):
                protection_profile_definition(invalid)

    def test_definitions_do_not_activate_unimplemented_policy_or_change_settings(self):
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        panel = (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8")
        settings = (ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("protection_profiles", gate)
        self.assertIn("def scanner_path():", gate)
        self.assertIn("if not cached_clean(cache_id):", gate)
        self.assertIn('static let name = "Built-in"', panel)
        self.assertIn("This page is informational and does not change scan settings.", settings)


if __name__ == "__main__":
    unittest.main()
