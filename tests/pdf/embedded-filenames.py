#!/usr/bin/env python3
"""opener-0454: inspect embedded PDF filenames as private, inert metadata."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import builtins
import socket
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, ByteStringObject, DictionaryObject, NameObject,
    NumberObject, TextStringObject,
)

from pdf_embedded_filenames import (
    BLOCK_MESSAGE, MAX_FILENAME_CHARACTERS, EmbeddedFilenameInspection,
    EmbeddedFilenameInspectionError, inspect_embedded_filenames,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent


def document(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build(*names):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    for filename in names:
        writer.add_attachment(filename, b"harmless test payload")
    return writer


def specification(writer):
    return writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()


def no_name_tree(writer, *, annotation=False):
    root = writer._root_object
    spec = root["/Names"]["/EmbeddedFiles"]["/Names"][1]
    del root[NameObject("/Names")]
    if annotation:
        writer.pages[0][NameObject("/Annots")] = ArrayObject([
            writer._add_object(DictionaryObject({
                NameObject("/Subtype"): NameObject("/FileAttachment"),
                NameObject("/FS"): spec,
            }))
        ])
    else:
        root[NameObject("/AF")] = ArrayObject([spec])
    return writer


class EmbeddedFilenameTests(unittest.TestCase):
    def assert_blocked(self, contents):
        with self.assertRaises(EmbeddedFilenameInspectionError) as failure:
            inspect_embedded_filenames(contents)
        self.assertEqual(str(failure.exception), BLOCK_MESSAGE)
        self.assertIsNone(failure.exception.__cause__)

    def test_reference_corpus_and_plain_filenames(self):
        for item in REFERENCE_PDFS:
            with self.subTest(sample=item.identifier):
                outcome = inspect_embedded_filenames(item.content)
                self.assertEqual(outcome, EmbeddedFilenameInspection(0, 0, 0, ()))
                self.assertFalse(outcome.authorizes_open)
        outcome = inspect_embedded_filenames(document(build("report.txt", "Café_日本語.pdf")))
        self.assertEqual(outcome.specification_count, 2)
        self.assertEqual(outcome.name_tree_entry_count, 2)
        self.assertFalse(outcome.has_suspicious_filenames)
        self.assertEqual(outcome.flags, ())

    def test_executable_disguise_and_traversal_are_classified_without_execution(self):
        writer = build("financial.pdf.exe")
        spec = specification(writer)
        spec[NameObject("/UF")] = TextStringObject("../secret-folder/payroll.pdf.exe")
        with (
            patch.object(socket, "getaddrinfo") as dns,
            patch.object(subprocess, "run") as spawn,
            patch.object(Path, "open") as file_open,
        ):
            outcome = inspect_embedded_filenames(document(writer))
        self.assertEqual(outcome.specification_count, 1)
        self.assertEqual(outcome.flagged_specification_count, 1)
        self.assertTrue({"path_component", "executable_extension",
                         "disguised_extension", "name_disagreement"}.issubset(outcome.flags))
        self.assertFalse(outcome.authorizes_open)
        self.assertNotIn("payroll", repr(outcome))
        self.assertNotIn("financial", repr(outcome))
        dns.assert_not_called()
        spawn.assert_not_called()
        file_open.assert_not_called()
        with self.assertRaises(FrozenInstanceError):
            outcome.authorizes_open = True

    def test_unicode_direction_and_invisible_character_flags(self):
        for name, expected in (
            ("report\u202ecod.exe", "unicode_direction"),
            ("report\u200b.pdf", "invisible_character"),
            ("report\n.pdf", "control_character"),
            ("report.pdf.", "trailing_separator"),
        ):
            with self.subTest(expected=expected):
                record = inspect_embedded_filenames(document(build(name)))
                self.assertIn(expected, record.flags)
                self.assertFalse(record.authorizes_open)

    def test_name_tree_alias_inspection_and_disagreement(self):
        writer = build("safe.pdf")
        tree = writer._root_object["/Names"]["/EmbeddedFiles"]
        tree["/Names"][0] = TextStringObject("../private/alt.exe")
        result = inspect_embedded_filenames(document(writer))
        self.assertIn("name_disagreement", result.flags)
        self.assertIn("path_component", result.flags)
        self.assertIn("executable_extension", result.flags)

    def test_page_associated_and_file_attachment_references(self):
        for annotation in (False, True):
            with self.subTest(annotation=annotation):
                writer = no_name_tree(build("payload.sh"), annotation=annotation)
                outcome = inspect_embedded_filenames(document(writer))
                self.assertEqual(outcome.specification_count, 1)
                self.assertEqual(outcome.name_tree_entry_count, 0)
                self.assertIn("executable_extension", outcome.flags)

    def test_invalid_file_spec_names_and_missing_embedded_stream_reference_block(self):
        for key, value in (
            ("/F", NumberObject(3)),
            ("/F", TextStringObject("")),
            ("/F", TextStringObject("X" * (MAX_FILENAME_CHARACTERS + 1))),
            ("/F", ByteStringObject(b"\xfe\xff\x00")),
            ("/F", TextStringObject("private\x00hidden")),
            ("/Type", NameObject("/Unexpected")),
            ("/EF", NumberObject(7)),
        ):
            with self.subTest(key=key, value_type=type(value).__name__):
                writer = build("example.txt")
                spec = specification(writer)
                spec[NameObject(key)] = value
                self.assert_blocked(document(writer))

        writer = build("example.txt")
        spec = specification(writer)
        del spec[NameObject("/EF")]
        self.assert_blocked(document(writer))

        writer = build("example.txt")
        node = writer._root_object["/Names"]["/EmbeddedFiles"]
        node["/Names"].append(TextStringObject("dangling"))
        self.assert_blocked(document(writer))

    def test_corrupt_encrypted_and_missing_dependency_fail_closed(self):
        writer = build("secret.pdf")
        writer.encrypt("synthetic-password")
        for source in (
            None, "", b"", b"not pdf", document(writer),
            REFERENCE_PDFS[0].content[:-10],
        ):
            with self.subTest(kind=type(source).__name__):
                self.assert_blocked(source)

        orig = builtins.__import__
        def unavailable(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("private filesystem path")
            return orig(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=unavailable):
            self.assert_blocked(REFERENCE_PDFS[0].content)

    def test_bounded_limits_and_result_contract(self):
        import pdf_embedded_filenames as stage
        with patch.object(stage, "MAX_ATTACHMENTS", 1):
            self.assert_blocked(document(build("first.pdf", "second.pdf")))
        with patch.object(stage, "MAX_TOTAL_FILENAME_CHARACTERS", 4):
            self.assert_blocked(document(build("fivelong.txt")))
        for result in (
            (1, 1, 2, ("path_component",)),
            (1, 0, 0, ("path_component",)),
            (1, 0, 1, ("unknown",)),
            (True, 0, 0, ()),
            (1, 0, 1, ("path_component", "path_component")),
        ):
            with self.subTest(value=result), self.assertRaises(ValueError):
                EmbeddedFilenameInspection(*result)

    def test_ci_contract_and_installed_scanner_noninterference(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        source = (ROOT / "pdf_embedded_filenames.py").read_text(encoding="utf-8")
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("python3 test-pdf-embedded-filenames.py -v", ci)
        self.assertNotIn("pdf_embedded_filenames", gate)
        self.assertIn("if not cached_clean(cache_id):", gate)
        for forbidden in ("subprocess.run(", "get_data(", "remove_quarantine(",
                          "launch_clean_file(", "write_text(", "eval(", "exec("):
            self.assertNotIn(forbidden, source)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
