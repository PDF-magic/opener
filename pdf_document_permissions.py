"""Passive PDF document-permission inspection; never decrypts or authorizes opening.

Encryption flags and catalog signature declarations are untrusted metadata,
not verified signatures or overrides of the installed ClamAV scan gate.
"""
from dataclasses import dataclass, field
from io import BytesIO
import re

from pdf_structure_parser import parse_pdf_structure

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_INDIRECT_HOPS = 32
MAX_SIGNATURE_REFERENCES = 16
BLOCK_MESSAGE = "PDF document permissions could not be fully inspected; opening was stopped."
_HEADER = re.compile(rb"\A%PDF-(1\.[0-7]|2\.0)[\r\n]")
_XREF = re.compile(rb"startxref\s+([0-9]{1,16})\s+%%EOF\s*\Z")
_BITS = (("print", 2), ("modify", 3), ("copy", 4),
         ("annotate", 5), ("fill_forms", 8), ("accessibility_extract", 9),
         ("assemble", 10), ("high_quality_print", 11))
_OPERATIONS = frozenset(key for key, _ in _BITS)
_DECLARATIONS = frozenset(("doc_mdp", "ur", "ur3"))


class PDFDocumentPermissionsError(RuntimeError):
    """A malformed or unsupported permissions document is not clean."""


@dataclass(frozen=True)
class PDFDocumentPermissions:
    is_encrypted: bool
    permission_bits: int | None
    allowed_operations: tuple[str, ...]
    catalog_inspected: bool
    catalog_declarations: tuple[str, ...]
    declared_doc_mdp_level: int | None
    signature_verified: bool = field(default=False, init=False)
    authorizes_open: bool = field(default=False, init=False)

    def __post_init__(self):
        if (type(self.is_encrypted) is not bool
            or self.is_encrypted != (self.permission_bits is not None)
            or (self.permission_bits is not None and (
                type(self.permission_bits) is not int or
                not -(1 << 31) <= self.permission_bits < 1 << 31))
            or type(self.allowed_operations) is not tuple
            or self.allowed_operations != tuple(sorted(set(self.allowed_operations)))
            or any(value not in _OPERATIONS for value in self.allowed_operations)
            or (not self.is_encrypted and bool(self.allowed_operations))
            or type(self.catalog_inspected) is not bool
            or (self.is_encrypted and self.catalog_inspected)
            or type(self.catalog_declarations) is not tuple
            or self.catalog_declarations != tuple(sorted(set(self.catalog_declarations)))
            or any(value not in _DECLARATIONS for value in self.catalog_declarations)
            or (not self.catalog_inspected and (
                bool(self.catalog_declarations) or self.declared_doc_mdp_level is not None))
            or (self.declared_doc_mdp_level is not None and (
                type(self.declared_doc_mdp_level) is not int or
                self.declared_doc_mdp_level not in (1, 2, 3) or
                "doc_mdp" not in self.catalog_declarations))
            or self.signature_verified is not False or self.authorizes_open is not False):
            raise ValueError("Invalid non-opening PDF permission evidence")

    def to_dict(self):
        return {
            "schemaVersion": 1,
            "isEncrypted": self.is_encrypted,
            "permissionBits": self.permission_bits,
            "allowedOperations": list(self.allowed_operations),
            "catalogInspected": self.catalog_inspected,
            "catalogDeclarations": list(self.catalog_declarations),
            "declaredDocMDPLevel": self.declared_doc_mdp_level,
            "signatureVerified": False,
            "authorizesOpen": False,
        }


def _operations(bits):
    if (not isinstance(bits, int) or isinstance(bits, bool) or
        not -(1 << 31) <= bits < 1 << 31):
        raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
    mask = bits & 0xffffffff
    return tuple(sorted(name for name, index in _BITS if mask & (1 << index)))


def inspect_pdf_document_permissions(contents: bytes) -> PDFDocumentPermissions:
    """Inspect /Encrypt /P and catalog /Perms without passwords or execution.

    An encrypted catalog is deliberately not read: catalog_inspected=False
    means unknown, not no declarations. DocMDP declarations are unverified.
    """
    if (type(contents) is not bytes or not 0 < len(contents) <= MAX_PDF_BYTES or
        _HEADER.match(contents[:9]) is None):
        raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
    xref = _XREF.search(contents[-2048:])
    if xref is None:
        raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
    offset = int(xref.group(1))
    if not 0 < offset < len(contents) or contents[offset:offset + 4] != b"xref":
        # Avoid implicit compressed-object / xref-stream expansion.
        raise PDFDocumentPermissionsError(BLOCK_MESSAGE)

    try:
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject

        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.xref_objStm:
            raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
        count = 0

        def resolve(value):
            nonlocal count
            seen = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in seen or count >= MAX_INDIRECT_HOPS:
                    raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
                seen.add(key)
                count += 1
                value = value.get_object()
            return value

        def dictionary(value):
            value = resolve(value)
            if not isinstance(value, DictionaryObject) or isinstance(value, StreamObject):
                raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
            return value

        if reader.is_encrypted:
            encrypt = dictionary(reader.trailer.raw_get("/Encrypt"))
            if encrypt.get("/Filter") != "/Standard":
                raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
            flags = resolve(encrypt.raw_get("/P"))
            allowed = _operations(flags)
            # NumberObject is an int subclass; freeze to a trusted Python int.
            return PDFDocumentPermissions(True, int(flags), allowed, False, (), None)

        # Existing strict parser validates unencrypted page tree and stream lengths.
        parse_pdf_structure(contents)
        root = dictionary(reader.trailer.raw_get("/Root"))
        if root.get("/Type") != "/Catalog":
            raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
        declarations = []
        certification = None
        if "/Perms" in root:
            perms = dictionary(root.raw_get("/Perms"))
            for key, label in (("/DocMDP", "doc_mdp"), ("/UR", "ur"), ("/UR3", "ur3")):
                if key not in perms:
                    continue
                sig = dictionary(perms.raw_get(key))
                if sig.get("/Type") not in (None, "/Sig"):
                    raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
                declarations.append(label)
                if key == "/DocMDP" and "/Reference" in sig:
                    refs = resolve(sig.raw_get("/Reference"))
                    if not isinstance(refs, ArrayObject) or len(refs) > MAX_SIGNATURE_REFERENCES:
                        raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
                    for ref in refs:
                        rule = dictionary(ref)
                        if rule.get("/TransformMethod") != "/DocMDP":
                            continue
                        params = dictionary(rule.raw_get("/TransformParams"))
                        level = resolve(params.raw_get("/P"))
                        if (not isinstance(level, int) or isinstance(level, bool)
                            or level not in (1, 2, 3)
                            or (certification is not None and level != certification)):
                            raise PDFDocumentPermissionsError(BLOCK_MESSAGE)
                        certification = int(level)

        return PDFDocumentPermissions(
            False, None, (), True, tuple(sorted(declarations)), certification
        )
    except PDFDocumentPermissionsError:
        raise
    except Exception:
        # Suppress filenames, passwords and parser exception strings.
        raise PDFDocumentPermissionsError(BLOCK_MESSAGE) from None
