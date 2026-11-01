#!/usr/bin/env python3
"""opener-1016: exercise legitimate AcroForms against planned Enhanced inspections.

These are real, in-memory PDF fixtures, not mocked scanner outcomes. Enhanced
remains unavailable; inspection evidence never replaces the ClamAV open gate.
"""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, BooleanObject, DictionaryObject, NameObject, NumberObject,
    TextStringObject,
)

from effective_protection_policy import (
    ACTIVE_PROFILE_ID, SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from pdf_form_actions import inspect_pdf_form_actions
from pdf_structure_parser import parse_pdf_structure
from pdf_xfa_forms import inspect_pdf_xfa_forms
from protection_policy_definitions import PROTECTION_POLICIES
from protection_profiles import BASELINE_SAFETY_CHECKS, ProtectionProfileID


ROOT = Path(__file__).resolve().parents[2]


def legitimate_form_pdf(*, submit_action=False):
    """Construct a genuine AcroForm with ordinary text and checkbox widgets."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    def widget(label, field_type, value, rect):
        item = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject(field_type),
            NameObject("/T"): TextStringObject(label),
            NameObject("/V"): (
                TextStringObject(value) if field_type == "/Tx" else NameObject(value)
            ),
            NameObject("/Rect"): ArrayObject([NumberObject(n) for n in rect]),
            NameObject("/F"): NumberObject(4),
        })
        if field_type == "/Tx":
            item[NameObject("/DA")] = TextStringObject("/Helv 12 Tf 0 g")
        else:
            item[NameObject("/AS")] = NameObject("/Off")
        return item

    text_field = widget("contact", "/Tx", "Fixture only", (50, 600, 300, 630))
    if submit_action:
        text_field[NameObject("/AA")] = DictionaryObject({
            NameObject("/Fo"): DictionaryObject({
                NameObject("/S"): NameObject("/SubmitForm"),
                NameObject("/F"): TextStringObject("https://example.invalid/collect"),
            }),
        })

    references = [
        writer._add_object(text_field),
        writer._add_object(widget("approved", "/Btn", "/Off", (50, 550, 70, 570))),
    ]
    page[NameObject("/Annots")] = ArrayObject(references)
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject({
            NameObject("/Fields"): ArrayObject(references),
            NameObject("/NeedAppearances"): BooleanObject(False),
            NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
        })
    )

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class EnhancedLegitimateFormTests(unittest.TestCase):
    def test_real_text_and_checkbox_fields_are_well_formed_and_inspectable(self):
        document = legitimate_form_pdf()
        reader = PdfReader(BytesIO(document), strict=True)
        self.assertEqual(len(reader.pages), 1)
        self.assertEqual(
            {key: field["/FT"] for key, field in reader.get_fields().items()},
            {"contact": "/Tx", "approved": "/Btn"},
        )
        self.assertEqual(reader.get_fields()["contact"]["/V"], "Fixture only")

        structure = parse_pdf_structure(document)
        self.assertEqual(structure.page_count, 1)
        self.assertIs(structure.to_dict()["authorizesOpen"], False)

        actions = inspect_pdf_form_actions(document)
        self.assertEqual(actions.action_count, 0)
        self.assertFalse(actions.has_submission_target)
        self.assertFalse(actions.permits_open)

        xfa = inspect_pdf_xfa_forms(document)
        self.assertFalse(xfa.contains_xfa)
        self.assertFalse(xfa.permits_open)

    def test_submit_action_on_same_form_is_not_silently_treated_as_inert(self):
        document = legitimate_form_pdf(submit_action=True)
        self.assertEqual(len(PdfReader(BytesIO(document), strict=True).get_fields()), 2)
        self.assertEqual(parse_pdf_structure(document).page_count, 1)

        # No action in the PDF is executed or its destination returned.
        with patch("subprocess.run") as process, patch("os.system") as shell:
            actions = inspect_pdf_form_actions(document)
        process.assert_not_called()
        shell.assert_not_called()
        self.assertEqual(actions.action_count, 1)
        self.assertEqual(actions.action_kinds, ("submit",))
        self.assertTrue(actions.has_submission_target)
        self.assertFalse(actions.permits_open)
        self.assertNotIn("example.invalid", repr(actions))

    def test_successful_form_inspection_does_not_activate_enhanced_or_bypass_scan(self):
        policy = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        self.assertFalse(policy.selectable)
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(
            frozenset(item.value for item in resolve_effective_policy().required_checks),
            BASELINE_SAFETY_CHECKS,
        )
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy({SELECTED_PROFILE_KEY: "enhanced"})

        # Neither passive inspection module is part of the deployed open gate.
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("pdf_form_actions", gate)
        self.assertNotIn("pdf_xfa_forms", gate)
        self.assertIn("if not cached_clean(cache_id):", gate)
        self.assertIn("remove_quarantine(path)", gate)


if __name__ == "__main__":
    unittest.main()
