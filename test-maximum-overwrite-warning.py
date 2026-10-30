#!/usr/bin/env python3
"""opener-0546: never overwrite a selected user destination silently."""
import os
from pathlib import Path
import tempfile
import unittest

import maximum_overwrite_warning as warning


class OverwriteWarningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / "sanitized.pdf"

    def test_new_destination_needs_no_warning_but_must_remain_absent(self):
        review = warning.review_sanitized_copy_destination(self.destination)
        self.assertFalse(review.requires_confirmation)
        self.assertIsNone(review.warning)
        warning.require_sanitized_copy_destination_confirmation(review)
        self.destination.write_bytes(b"new file from another process")
        with self.assertRaisesRegex(warning.SaveDestinationError,
                                    warning.DESTINATION_CHANGED):
            warning.require_sanitized_copy_destination_confirmation(review)

    def test_existing_destination_warns_and_requires_explicit_consent(self):
        original = b"untouched user PDF"
        self.destination.write_bytes(original)
        review = warning.review_sanitized_copy_destination(self.destination)
        self.assertTrue(review.requires_confirmation)
        self.assertEqual(review.warning, warning.OVERWRITE_WARNING)
        for value in (False, None, 1, "yes", [], object()):
            with self.subTest(value=repr(value)):
                with self.assertRaises(warning.SaveDestinationError) as caught:
                    warning.require_sanitized_copy_destination_confirmation(
                        review, confirmed=value)
                self.assertEqual(str(caught.exception), warning.OVERWRITE_WARNING)
                self.assertEqual(self.destination.read_bytes(), original)
        warning.require_sanitized_copy_destination_confirmation(
            review, confirmed=True)
        self.assertEqual(self.destination.read_bytes(), original)

    def test_modified_or_replaced_file_invalidates_previous_confirmation(self):
        self.destination.write_bytes(b"first")
        review = warning.review_sanitized_copy_destination(self.destination)
        self.destination.write_bytes(b"a different length")
        with self.assertRaisesRegex(warning.SaveDestinationError,
                                    warning.DESTINATION_CHANGED):
            warning.require_sanitized_copy_destination_confirmation(
                review, confirmed=True)
        review = warning.review_sanitized_copy_destination(self.destination)
        self.destination.unlink()
        self.destination.write_bytes(b"replacement")
        with self.assertRaisesRegex(warning.SaveDestinationError,
                                    warning.DESTINATION_CHANGED):
            warning.require_sanitized_copy_destination_confirmation(
                review, confirmed=True)

    def test_disappearing_file_needs_new_review(self):
        self.destination.write_bytes(b"existing")
        review = warning.review_sanitized_copy_destination(self.destination)
        self.destination.unlink()
        with self.assertRaisesRegex(warning.SaveDestinationError,
                                    warning.DESTINATION_CHANGED):
            warning.require_sanitized_copy_destination_confirmation(
                review, confirmed=True)

    def test_symlink_and_dangling_symlink_are_never_silently_replaced(self):
        victim = Path(self.temp.name) / "original.pdf"
        victim.write_bytes(b"leave alone")
        for target in (victim, Path(self.temp.name) / "missing.pdf"):
            self.destination.symlink_to(target)
            with self.assertRaises(warning.SaveDestinationError) as caught:
                warning.review_sanitized_copy_destination(self.destination)
            self.assertEqual(str(caught.exception), warning.DESTINATION_ERROR)
            self.destination.unlink()
        self.assertEqual(victim.read_bytes(), b"leave alone")

    def test_hardlinked_and_nonregular_targets_are_not_overwrite_candidates(self):
        victim = Path(self.temp.name) / "protected.pdf"
        victim.write_bytes(b"keep")
        os.link(victim, self.destination)
        with self.assertRaises(warning.SaveDestinationError):
            warning.review_sanitized_copy_destination(self.destination)
        self.destination.unlink()
        self.destination.mkdir()
        with self.assertRaises(warning.SaveDestinationError):
            warning.review_sanitized_copy_destination(self.destination)
        self.assertEqual(victim.read_bytes(), b"keep")

    def test_invalid_destinations_are_blocked_without_exposing_user_paths(self):
        for value in (None, 123, "relative.pdf", "/tmp/not-a-pdf.txt",
                      str(self.destination) + "\x00", Path(self.temp.name) / "no" / "x.pdf"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(warning.SaveDestinationError) as caught:
                    warning.review_sanitized_copy_destination(value)
                self.assertEqual(str(caught.exception), warning.DESTINATION_ERROR)
        with self.assertRaises(warning.SaveDestinationError):
            warning.require_sanitized_copy_destination_confirmation("forged", confirmed=True)


if __name__ == "__main__":
    unittest.main()
