"""Bounded, fail-closed embedded-file inspection for a future Enhanced PDF stage.

This module does not select a profile, return a PDF clean verdict, alter a
quarantine flag, or replace the installed Built-in ClamAV scan gate. A future
Enhanced pipeline must run this stage in addition to ALL Standard checks.
Requires pypdf 5.9.0 at the point the stage is invoked; absence blocks it.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import subprocess
import zlib


MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024
MAX_TOTAL_ATTACHMENT_BYTES = 64 * 1024 * 1024
MAX_ATTACHMENTS = 32
MAX_PAGES = 1024
MAX_NAME_TREE_NODES = 256
ATTACHMENT_SCAN_TIMEOUT = 120

# Never echo untrusted PDF filenames, embedded bytes, or scanner diagnostics.
BLOCK_MESSAGE = "Embedded PDF files could not be fully inspected; opening was stopped."


class EmbeddedFileInspectionError(RuntimeError):
    """Incomplete inspection is a terminal, non-clean outcome."""


@dataclass(frozen=True)
class EmbeddedFileInspection:
    """Evidence about attachments only, NOT permission to open the outer PDF."""

    inspected_count: int
    inspected_bytes: int
    pdf_is_clean: bool = False

    def __post_init__(self):
        if (type(self.inspected_count) is not int or self.inspected_count < 0 or
                type(self.inspected_bytes) is not int or self.inspected_bytes < 0 or
                self.pdf_is_clean is not False):
            raise ValueError("Attachment inspection is not a PDF clean verdict.")


def _resolve(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def _dictionary(obj, dictionary_type):
    value = _resolve(obj)
    if not isinstance(value, dictionary_type):
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    return value


def _array(obj, array_type):
    value = _resolve(obj)
    if not isinstance(value, array_type):
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    return value


def _specifications(reader, max_attachments):
    """Discover name-tree, associated-file, and page attachment references."""
    from pypdf.generic import ArrayObject, DictionaryObject

    catalog = _dictionary(reader.trailer["/Root"], DictionaryObject)
    found = []
    visited = set()

    def add(specification):
        spec = _dictionary(specification, DictionaryObject)
        marker = id(spec)
        if marker not in visited:
            visited.add(marker)
            found.append(spec)
            if len(found) > max_attachments:
                raise EmbeddedFileInspectionError(BLOCK_MESSAGE)

    def associated(obj):
        container = _dictionary(obj, DictionaryObject)
        if "/AF" in container:
            for spec in _array(container["/AF"], ArrayObject):
                add(spec)

    associated(catalog)
    if "/Names" in catalog:
        names = _dictionary(catalog["/Names"], DictionaryObject)
        if "/EmbeddedFiles" in names:
            tree_nodes = set()

            def walk(node, depth):
                if depth > 32 or len(tree_nodes) >= MAX_NAME_TREE_NODES:
                    raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
                node = _dictionary(node, DictionaryObject)
                marker = id(node)
                if marker in tree_nodes:
                    raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
                tree_nodes.add(marker)
                if "/Names" in node:
                    entries = _array(node["/Names"], ArrayObject)
                    if len(entries) % 2:
                        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
                    for index in range(1, len(entries), 2):
                        add(entries[index])
                if "/Kids" in node:
                    for kid in _array(node["/Kids"], ArrayObject):
                        walk(kid, depth + 1)
                if "/Names" not in node and "/Kids" not in node:
                    raise EmbeddedFileInspectionError(BLOCK_MESSAGE)

            walk(names["/EmbeddedFiles"], 0)

    if len(reader.pages) > MAX_PAGES:
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    for page in reader.pages:
        associated(page)
        if "/Annots" not in page:
            continue
        for annotation in _array(page["/Annots"], ArrayObject):
            annotation = _dictionary(annotation, DictionaryObject)
            if annotation.get("/Subtype") == "/FileAttachment":
                if "/FS" not in annotation:
                    raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
                add(annotation["/FS"])

    return found


def _extract(spec, maximum):
    """Decode only raw or zlib embedded streams, with a strict output ceiling."""
    from pypdf.generic import DictionaryObject, StreamObject

    if "/EF" not in spec:
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    embedded = _dictionary(spec["/EF"], DictionaryObject)
    stream_ref = embedded.get("/UF", embedded.get("/F"))
    stream = _resolve(stream_ref)
    if not isinstance(stream, StreamObject):
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)

    # pypdf's raw encoded stream bytes avoid unbounded get_data() expansion.
    raw = stream._data
    if type(raw) is not bytes or len(raw) > maximum:
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    kind = stream.get("/Filter")
    if kind is None:
        decoded = raw
    elif kind == "/FlateDecode" and stream.get("/DecodeParms") in (None,):
        try:
            inflater = zlib.decompressobj()
            decoded = inflater.decompress(raw, maximum + 1)
            if (not inflater.eof or inflater.unconsumed_tail or
                    inflater.unused_data or len(decoded) > maximum):
                raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
        except zlib.error as exc:
            raise EmbeddedFileInspectionError(BLOCK_MESSAGE) from exc
    else:
        # Unsupported filters, predictors and filter arrays cannot be skipped.
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    if not decoded or len(decoded) > maximum:
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    return decoded


def inspect_embedded_files(
    pdf_path, scanner, signature_database, *,
    max_pdf_bytes=MAX_PDF_BYTES,
    max_attachment_bytes=MAX_ATTACHMENT_BYTES,
    max_total_bytes=MAX_TOTAL_ATTACHMENT_BYTES,
    max_attachments=MAX_ATTACHMENTS,
    scan_timeout=ATTACHMENT_SCAN_TIMEOUT,
):
    """Extract every discoverable embedded stream and independently scan its bytes.

    Returns attachment inspection evidence, never an outer-PDF clean result.
    Unsupported encodings, malformed structures, missing scanner/parser, and
    non-clean ClamAV replies fail closed. No extracted bytes are written to disk.
    """
    limits = (max_pdf_bytes, max_attachment_bytes, max_total_bytes,
              max_attachments, scan_timeout)
    if any(type(value) is not int or value <= 0 for value in limits):
        raise ValueError("Inspection limits must be positive integers.")
    if type(scanner) is not str or not scanner or not signature_database:
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE) from exc

    try:
        with Path(pdf_path).open("rb") as source:
            pdf_bytes = source.read(max_pdf_bytes + 1)
        if len(pdf_bytes) > max_pdf_bytes:
            raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted:
            raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
        specs = _specifications(reader, max_attachments)
        total = 0
        for spec in specs:
            payload = _extract(spec, max_attachment_bytes)
            total += len(payload)
            if total > max_total_bytes:
                raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
            completed = subprocess.run(
                [
                    scanner, "--database=" + str(signature_database),
                    "--alert-exceeds-max=yes", "--alert-encrypted=yes",
                    "--max-filesize=0", "--max-scansize=0",
                    "--no-summary", "--stdin",
                ],
                input=payload, capture_output=True, timeout=scan_timeout,
                check=False,
            )
            # A bare zero exit status is not enough to establish a full scan.
            if (completed.returncode != 0 or completed.stderr or
                    completed.stdout.strip() not in (b"stream: OK", b"stdin: OK")):
                raise EmbeddedFileInspectionError(BLOCK_MESSAGE)
        return EmbeddedFileInspection(len(specs), total)
    except EmbeddedFileInspectionError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            AttributeError, RecursionError, subprocess.SubprocessError) as exc:
        raise EmbeddedFileInspectionError(BLOCK_MESSAGE) from exc
