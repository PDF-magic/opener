"""Deterministic, inert deeply nested indirect-reference PDF security fixture.

This is separate from the six shared profile-baseline reference documents.
No scanner or policy decision depends on these synthetic bytes.
"""

from reference_pdf_collection import ReferencePDF


DEEP_OBJECT_REFERENCE_DEPTH = 96


def _deeply_nested_object_references_pdf():
    """Build a valid one-page PDF with a 96-hop, acyclic indirect-object chain.

    The chain is linked from a nonstandard, inert catalog key; it does not
    alter the page tree or carry actions, scripts, attachments, or executables.
    Each object has its own cross-reference entry and a deterministic index.
    """
    stream = b"BT /F1 12 Tf 72 720 Td (Nested references fixture) Tj ET\n"
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R /DeepReference 6 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"),
        4: (b"<< /Length " + str(len(stream)).encode("ascii")
            + b" >>\nstream\n" + stream + b"endstream"),
        5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for index in range(DEEP_OBJECT_REFERENCE_DEPTH):
        number = index + 6
        following = (f"{number + 1} 0 R" if index + 1 < DEEP_OBJECT_REFERENCE_DEPTH
                     else "null")
        objects[number] = (
            f"<< /Index {index} /Next {following} >>".encode("ascii")
        )

    document = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number, value in sorted(objects.items()):
        offsets[number] = len(document)
        document.extend(f"{number} 0 obj\n".encode("ascii") + value + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for number in range(1, len(objects) + 1):
        document.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
    document.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


# Keep the six shared profile-baseline samples unchanged. Security corpus
# cases are separate because they exercise specialized parser boundaries.
SECURITY_REFERENCE_PDFS = (
    ReferencePDF(
        "deeply-nested-object-references",
        _deeply_nested_object_references_pdf(),
        "clean",
    ),
)
