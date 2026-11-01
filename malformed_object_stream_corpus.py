"""Harmless, deterministic malformed PDF 1.5 object-stream security fixtures.

Every sample has a correctly positioned cross-reference stream and a compressed
page object with no uncompressed fallback. Only the object stream is damaged.
Fixtures are generated in memory; none execute PDF actions or grant scan approval.
"""

from dataclasses import dataclass
import zlib


@dataclass(frozen=True)
class ObjectStreamFixture:
    identifier: str
    content: bytes


def _object_stream_pdf(defect=None, *, compressed=False):
    document = bytearray(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n")
    offsets = {}

    def add_object(number, body):
        offsets[number] = len(document)
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")

    add_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    add_object(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")

    member_header = b"3 0 "
    member_body = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
    if defect == "nonnumeric-member-id":
        member_header = b"X 0 "
    elif defect == "member-offset-past-object":
        member_header = b"3 9 "
    elif defect == "broken-object-dictionary":
        member_body = b"<X /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"

    encoded = member_header + member_body
    first = 0 if defect == "first-points-into-header" else len(member_header)
    count = 0 if defect == "zero-member-count" else 1
    if compressed:
        encoded = zlib.compress(encoded)
    if defect == "corrupt-flate-payload":
        assert compressed
        encoded = b"\x00\x00" + encoded[2:]
    declared_length = len(encoded) - (defect == "declared-length-underflow")
    filter_entry = b"/Filter /FlateDecode " if compressed else b""
    terminator = (b"endstreaX" if defect == "missing-endstream-terminator"
                  else b"endstream")
    dictionary = (b"<< /Type /ObjStm /N " + str(count).encode("ascii")
                  + b" /First " + str(first).encode("ascii") + b" "
                  + filter_entry + b"/Length "
                  + str(declared_length).encode("ascii") + b" >>")
    add_object(4, dictionary + b"\nstream\n" + encoded + b"\n" + terminator)

    offsets[5] = len(document)

    def xref_entry(number):
        if number == 0:
            return bytes((0,)) + (0).to_bytes(4, "big") + (65535).to_bytes(2, "big")
        if number == 3:
            return bytes((2,)) + (4).to_bytes(4, "big") + (0).to_bytes(2, "big")
        return bytes((1,)) + offsets[number].to_bytes(4, "big") + (0).to_bytes(2, "big")

    entries = b"".join(xref_entry(number) for number in range(6))
    xref_dictionary = (b"<< /Type /XRef /Size 6 /Root 1 0 R "
                       b"/W [1 4 2] /Index [0 6] /Length "
                       + str(len(entries)).encode("ascii") + b" >>")
    add_object(5, xref_dictionary + b"\nstream\n" + entries + b"\nendstream")
    document.extend(b"startxref\n" + str(offsets[5]).encode("ascii") + b"\n%%EOF\n")
    return bytes(document)


VALID_OBJECT_STREAM_PDFS = (
    ObjectStreamFixture("plain-object-stream", _object_stream_pdf()),
    ObjectStreamFixture("flate-object-stream", _object_stream_pdf(compressed=True)),
)

MALFORMED_OBJECT_STREAM_PDFS = tuple(
    ObjectStreamFixture(name, _object_stream_pdf(name, compressed=name == "corrupt-flate-payload"))
    for name in (
        "zero-member-count",
        "first-points-into-header",
        "member-offset-past-object",
        "nonnumeric-member-id",
        "broken-object-dictionary",
        "declared-length-underflow",
        "missing-endstream-terminator",
        "corrupt-flate-payload",
    )
)
