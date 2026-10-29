"""Read PDF document structure with the maintained pypdf parser (opener-0283).

This is a callable, fail-closed Enhanced-protection building block, NOT an
active profile or a file-opening verdict. It never opens filesystem paths,
decrypts documents, runs page content, or changes the established ClamAV,
quarantine, cache, and launch gates. The caller must separately enforce the
scan-time budget and verify the same file bytes before any future handoff.
"""

from dataclasses import dataclass
from enum import Enum
from io import BytesIO
import re


MAX_STRUCTURE_INPUT_BYTES = 16 * 1024 * 1024
MAX_STRUCTURE_PAGES = 1024
MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES = 8 * 1024 * 1024
MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_STRUCTURE_RECURSION_DEPTH = 64
_NESTING_TOKENS = re.compile(rb'<<|>>|stream(?:\r\n|\n|\r)|[\[\]()%<>]')
_HEADER = re.compile(rb"\A%PDF-(1\.[0-7]|2\.0)[\r\n]")
_ERROR = "PDF structure could not be verified; opening was stopped."
_ENCRYPTED = "Encrypted PDF structure cannot be inspected; opening was stopped."
_DEPENDENCY = "The PDF structure parser is unavailable; opening was stopped."
_SIZE = "The PDF exceeds the structure inspection limit; opening was stopped."


class PDFStructureParseError(RuntimeError):
    """A non-clean structural result with no private PDF content in the message."""


@dataclass(frozen=True)
class PDFStructure:
    """Validated, immutable parser evidence; never an opening authorization.

    Version 1 of the JSON contract intentionally exposes only known metadata:
    PDF version and bounded page count. PDF-controlled strings, document paths,
    attachment names, page content and parser exception text are excluded.
    """

    pdf_version: str
    page_count: int

    def __post_init__(self):
        allowed_versions = {*(f"1.{minor}" for minor in range(8)), "2.0"}
        if type(self.pdf_version) is not str or self.pdf_version not in allowed_versions:
            raise ValueError("Unsupported PDF structural version")
        if type(self.page_count) is not int or not 1 <= self.page_count <= MAX_STRUCTURE_PAGES:
            raise ValueError("Invalid PDF structural page count")

    def to_dict(self) -> dict[str, str | int | bool]:
        """Return a detached, stable and JSON-serializable output record."""
        return {
            "schemaVersion": 1,
            "pdfVersion": self.pdf_version,
            "pageCount": self.page_count,
            "authorizesOpen": False,
        }


class PDFStructureFailureCode(str, Enum):
    """Trusted, path-free failure categories, never sourced from PDF strings."""

    invalidInput = "invalidInput"
    invalidStructure = "invalidStructure"
    sizeLimit = "sizeLimit"
    encrypted = "encrypted"
    dependencyUnavailable = "dependencyUnavailable"


@dataclass(frozen=True)
class PDFStructureParseFailure:
    """Non-clean parser outcome that never represents permission to proceed."""

    code: PDFStructureFailureCode

    def __post_init__(self):
        if type(self.code) is not PDFStructureFailureCode:
            raise TypeError("A known parsing failure code is required")

    def to_dict(self) -> dict[str, str | int | bool]:
        """Return detached, bounded, JSON-compatible diagnostic metadata."""
        return {
            "schemaVersion": 1,
            "status": "failure",
            "failureCode": self.code.value,
            "authorizesOpen": False,
        }


def _validate_direct_nesting(contents: bytes) -> None:
    """Bound direct PDF arrays/dictionaries before pypdf can recurse into them.

    Stream bytes, comments, literal strings (including escaped parentheses),
    and hex strings are not object containers. This bounded lexical preflight
    does not replace strict parsing; uncertain or unbalanced syntax fails closed.
    """
    containers = []
    literal_depth = 0
    skip_before = 0
    for match in _NESTING_TOKENS.finditer(contents):
        position = match.start()
        if position < skip_before:
            continue
        token = match.group()
        if literal_depth:
            if token in (b"(", b")"):
                escapes = 0
                previous = position - 1
                while previous >= 0 and contents[previous] == 92:
                    escapes += 1
                    previous -= 1
                if escapes % 2 == 0:
                    literal_depth += 1 if token == b"(" else -1
            continue
        if token == b"%":
            lf = contents.find(b"\n", position + 1)
            cr = contents.find(b"\r", position + 1)
            ends = [end for end in (lf, cr) if end >= 0]
            skip_before = min(ends) + 1 if ends else len(contents)
        elif token == b"(":
            literal_depth = 1
        elif token == b"<":
            end = contents.find(b">", position + 1)
            if end < 0:
                raise PDFStructureParseError(_ERROR)
            skip_before = end + 1
        elif token.startswith(b"stream"):
            # A stream body begins only after an indirect object's dictionary.
            # Never interpret arbitrary binary stream payload as PDF containers.
            previous = position - 1
            while previous >= 0 and contents[previous] in b" \t\f\r\n":
                previous -= 1
            if not containers and contents[max(0, previous - 1):previous + 1] == b">>":
                end = contents.find(b"endstream", match.end())
                if end < 0:
                    raise PDFStructureParseError(_ERROR)
                skip_before = end + len(b"endstream")
        elif token in (b"<<", b"["):
            containers.append(token)
            if len(containers) > MAX_STRUCTURE_RECURSION_DEPTH:
                raise PDFStructureParseError(_ERROR)
        elif token in (b">>", b"]"):
            expected = b"<<" if token == b">>" else b"["
            if not containers or containers[-1] != expected:
                raise PDFStructureParseError(_ERROR)
            containers.pop()
    if containers or literal_depth:
        raise PDFStructureParseError(_ERROR)


def _validate_page_tree_depth(root) -> None:
    """Walk /Pages iteratively before invoking pypdf's recursive flattening."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    pending = [(root.raw_get("/Pages"), 0)]
    seen_refs = set()
    seen_direct = set()
    while pending:
        node, depth = pending.pop()
        if depth > MAX_STRUCTURE_RECURSION_DEPTH:
            raise PDFStructureParseError(_ERROR)
        if isinstance(node, IndirectObject):
            identity = (node.idnum, node.generation)
            if identity in seen_refs:
                raise PDFStructureParseError(_ERROR)
            seen_refs.add(identity)
            node = node.get_object()
        else:
            identity = id(node)
            if identity in seen_direct:
                raise PDFStructureParseError(_ERROR)
            seen_direct.add(identity)
        if not isinstance(node, DictionaryObject):
            raise PDFStructureParseError(_ERROR)
        if node.get("/Type") == "/Page":
            continue
        children = node.get("/Kids")
        if not isinstance(children, ArrayObject):
            raise PDFStructureParseError(_ERROR)
        pending.extend((child, depth + 1) for child in children)


def _verify_decoded_stream_budget(reader) -> None:
    """Count decoded bytes for all indexed streams, including unreferenced ones.

    pypdf's scoped filter limits bound each allocation before get_data() can
    materialize it; the total budget stops cumulative decompression bombs.
    Stream data is never returned or interpreted as a clean verdict.
    """
    from pypdf.generic import IndirectObject, StreamObject

    total = 0
    for generation, objects in reader.xref.items():
        for number in objects:
            if number <= 0:
                continue
            stream = reader.get_object(IndirectObject(number, generation, reader))
            if not isinstance(stream, StreamObject):
                continue
            decoded_size = len(stream.get_data())
            if decoded_size > MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES:
                raise PDFStructureParseError(_SIZE)
            total += decoded_size
            if total > MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES:
                raise PDFStructureParseError(_SIZE)


def parse_pdf_structure(contents: bytes) -> PDFStructure:
    """Parse an in-memory PDF with pypdf's strict object and page-tree reader.

    Accept bytes only: callers must read and validate a file through the
    existing secure file-handling workflow. The strict pypdf reader resolves
    traditional cross-reference tables, PDF 1.5 cross-reference streams, and
    compressed objects in object streams as needed to traverse the page tree.
    Avoid decoding page content streams, following attachments/links, or
    invoking user-specified applications.
    """
    if type(contents) is not bytes:
        raise PDFStructureParseError(_ERROR)
    if len(contents) > MAX_STRUCTURE_INPUT_BYTES:
        raise PDFStructureParseError(_SIZE)
    header = _HEADER.match(contents[:9])
    if header is None or b"%%EOF" not in contents[-1024:]:
        raise PDFStructureParseError(_ERROR)
    _validate_direct_nesting(contents)

    try:
        from pypdf import PdfReader, apply_configuration
        from pypdf.errors import LimitReachedError
    except (ImportError, OSError):
        raise PDFStructureParseError(_DEPENDENCY) from None

    try:
        with apply_configuration(
            maximum_declared_stream_length=MAX_STRUCTURE_INPUT_BYTES,
            zlib_maximum_output_length=MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES,
            lzw_maximum_output_length=MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES,
            run_length_maximum_output_length=MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES,
            brotli_maximum_output_length=MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES,
            jbig2_maximum_output_length=MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES,
            stream_decoding_work_maximum_length=MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES,
        ):
            reader = PdfReader(BytesIO(contents), strict=True)
            if reader.is_encrypted:
                raise PDFStructureParseError(_ENCRYPTED)
            # Check original bytes, not a library-recovered stream payload.
            from pdf_stream_lengths import validate_pdf_stream_lengths
            validate_pdf_stream_lengths(contents, reader)
            _verify_decoded_stream_budget(reader)
            root = reader.trailer["/Root"]
            if root.get("/Type") != "/Catalog":
                raise PDFStructureParseError(_ERROR)
            _validate_page_tree_depth(root)
            pages = reader.pages
            count = len(pages)
            if count < 1 or count > MAX_STRUCTURE_PAGES:
                raise PDFStructureParseError(_ERROR)
            for page in pages:
                if page.get("/Type") != "/Page":
                    raise PDFStructureParseError(_ERROR)
    except PDFStructureParseError:
        raise
    except LimitReachedError:
        raise PDFStructureParseError(_SIZE) from None
    except Exception:
        # pypdf error details may contain untrusted PDF strings or filenames.
        raise PDFStructureParseError(_ERROR) from None

    return PDFStructure(pdf_version=header.group(1).decode("ascii"), page_count=count)

# Map only fixed error messages created by this module. The wrapper never
# serializes exception text, raw input, filenames, object values, or paths.
_FAILURE_CODES = {
    _ERROR: PDFStructureFailureCode.invalidStructure,
    _ENCRYPTED: PDFStructureFailureCode.encrypted,
    _DEPENDENCY: PDFStructureFailureCode.dependencyUnavailable,
    _SIZE: PDFStructureFailureCode.sizeLimit,
}


def parse_pdf_structure_result(contents: bytes) -> PDFStructure | PDFStructureParseFailure:
    """Return strict parsing evidence or a structured, fail-closed failure.

    Keep parse_pdf_structure's existing exception behavior for older callers.
    This explicit result-based API is optional and does not authorize opening,
    cache reuse, profile activation, or any change to the installed scan gate.
    """
    if type(contents) is not bytes:
        return PDFStructureParseFailure(PDFStructureFailureCode.invalidInput)
    try:
        return parse_pdf_structure(contents)
    except PDFStructureParseError as error:
        return PDFStructureParseFailure(
            _FAILURE_CODES.get(str(error), PDFStructureFailureCode.invalidStructure)
        )
