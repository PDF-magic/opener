"""Passive, bounded inspection of embedded PDF URLs (opener-0292).

This inactive Enhanced-stage inspector never authorizes opening or fetches,
resolves, logs, or returns a document-supplied destination.
"""
from dataclasses import dataclass
from io import BytesIO
from ipaddress import ip_address
import re
import unicodedata
from urllib.parse import urlsplit

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_INDIRECT_OBJECTS = 4096
MAX_GRAPH_NODES = 65536
MAX_PAGES = 1024
MAX_URLS = 512
MAX_URL_LENGTH = 2048
BLOCK_MESSAGE = "Embedded PDF URLs could not be fully inspected; opening was stopped."

FINDING_CATEGORIES = frozenset({
    "unencrypted_http", "non_web_scheme", "relative_reference",
    "embedded_credentials", "non_global_ip", "numeric_host",
    "local_hostname", "hidden_service", "internationalized_host",
    "encoded_host", "encoded_control", "nonstandard_port",
})
_HEX_ESCAPE = re.compile(r"%(?![0-9a-fA-F]{2})")
_NUMERIC_HOST = re.compile(
    r"(?i)^(?:0x[0-9a-f]+|0[0-7]+|[0-9]+)"
    r"(?:\.(?:0x[0-9a-f]+|0[0-7]+|[0-9]+))*$"
)
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")


class PDFSuspiciousURLInspectionError(RuntimeError):
    """Fixed, path-free failure for incomplete or malformed inspection."""


@dataclass(frozen=True)
class PDFSuspiciousURLInspection:
    url_count: int
    suspicious_count: int
    categories: tuple[str, ...]
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.url_count) is not int or not 0 <= self.url_count <= MAX_URLS or
                type(self.suspicious_count) is not int or
                not 0 <= self.suspicious_count <= self.url_count or
                type(self.categories) is not tuple or
                self.categories != tuple(sorted(set(self.categories))) or
                any(category not in FINDING_CATEGORIES for category in self.categories) or
                bool(self.suspicious_count) != bool(self.categories) or
                self.permits_open is not False):
            raise ValueError("URL inspection findings cannot authorize opening")

    @property
    def has_suspicious_urls(self) -> bool:
        return self.suspicious_count > 0


def _read_url(value):
    """Accept only bounded, unambiguous PDF text or byte strings."""
    from pypdf.generic import ByteStringObject, TextStringObject

    if isinstance(value, TextStringObject):
        candidate = str(value)
    elif isinstance(value, ByteStringObject):
        raw = bytes(value)
        if len(raw) > MAX_URL_LENGTH * 2:
            raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
        try:
            candidate = (raw[2:].decode("utf-16-be", errors="strict")
                         if raw.startswith(b"\xfe\xff")
                         else raw.decode("utf-8", errors="strict"))
        except UnicodeError as exc:
            raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE) from exc
    else:
        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
    if (not candidate or len(candidate) > MAX_URL_LENGTH or
            any(ord(c) < 32 or ord(c) == 127 or c.isspace() or
                c == "\\" or unicodedata.category(c) in ("Cf", "Cs")
                for c in candidate) or _HEX_ESCAPE.search(candidate)):
        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
    return candidate


def _classify_url(value):
    url = _read_url(value)
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        findings = set()
        if not scheme:
            findings.add("relative_reference")
        elif not _SCHEME.fullmatch(scheme):
            raise ValueError("invalid scheme")
        elif scheme == "http":
            findings.add("unencrypted_http")
        elif scheme != "https":
            findings.add("non_web_scheme")

        if scheme in ("http", "https") and not parsed.netloc:
            raise ValueError("missing authority")
        if parsed.netloc:
            hostname = parsed.hostname
            if not hostname or any(c.isspace() or ord(c) < 33 for c in hostname):
                raise ValueError("invalid hostname")
            if parsed.username is not None or parsed.password is not None:
                findings.add("embedded_credentials")
            if "%" in parsed.netloc:
                findings.add("encoded_host")
            if (any(ord(c) > 127 for c in hostname) or
                    any(label.startswith("xn--") for label in hostname.lower().split("."))):
                findings.add("internationalized_host")
            host = hostname.lower().rstrip(".")
            if host in ("localhost", "localhost.localdomain") or host.endswith(
                (".localhost", ".local", ".internal", ".home.arpa")
            ):
                findings.add("local_hostname")
            if host.endswith(".onion"):
                findings.add("hidden_service")
            try:
                address = ip_address(host)
            except ValueError:
                if _NUMERIC_HOST.fullmatch(host):
                    findings.add("numeric_host")
            else:
                if not address.is_global:
                    findings.add("non_global_ip")
            port = parsed.port
            if port is not None and (scheme not in ("http", "https") or
                                     port != (80 if scheme == "http" else 443)):
                findings.add("nonstandard_port")
        if re.search(r"(?i)%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)", url):
            findings.add("encoded_control")
        return findings
    except (ValueError, UnicodeError) as exc:
        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE) from exc


def inspect_pdf_suspicious_urls(contents: bytes) -> PDFSuspiciousURLInspection:
    """Inspect URI actions, URL file specifications and catalog base dictionaries.

    The bounded strict-parser walk includes indexed orphan actions, page links,
    form-submission URLs, /Next chains, and catalog /URI /Base values. It never
    decodes content streams or follows any document-supplied network target.
    """
    if type(contents) is not bytes or not contents or len(contents) > MAX_PDF_BYTES:
        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
    try:
        from pypdf import PdfReader
        from pypdf.generic import (ArrayObject, DictionaryObject, IndirectObject,
                                   TextStringObject, ByteStringObject)
    except (ImportError, OSError) as exc:
        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE) from exc

    try:
        reader = PdfReader(BytesIO(contents), strict=True)
        if reader.is_encrypted or reader.xref_objStm or len(reader.pages) > MAX_PAGES:
            raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
        roots = [reader.trailer]
        indexed = 0
        for generation, offsets in reader.xref.items():
            if type(generation) is not int or not 0 <= generation <= 65535:
                raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
            for number, offset in offsets.items():
                if number == 0:
                    continue
                if (type(number) is not int or type(offset) is not int or
                        number < 1 or offset <= 0):
                    raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
                indexed += 1
                if indexed > MAX_INDIRECT_OBJECTS:
                    raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
                roots.append(IndirectObject(number, generation, reader))

        cached_refs = {}
        examined = set()
        url_count = suspicious_count = visited = 0
        categories = set()

        def resolve(value):
            chain = set()
            while isinstance(value, IndirectObject):
                key = (value.idnum, value.generation)
                if key in chain:
                    raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
                chain.add(key)
                if key not in cached_refs:
                    if len(cached_refs) >= MAX_INDIRECT_OBJECTS:
                        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
                    cached_refs[key] = value.get_object()
                value = cached_refs[key]
                if value is None:
                    raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
            return value

        def record(value):
            nonlocal url_count, suspicious_count
            url_count += 1
            if url_count > MAX_URLS:
                raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
            matches = _classify_url(resolve(value))
            if matches:
                suspicious_count += 1
                categories.update(matches)

        stack = roots
        while stack:
            node = resolve(stack.pop())
            visited += 1
            if visited > MAX_GRAPH_NODES:
                raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
            if not isinstance(node, (DictionaryObject, ArrayObject)):
                continue
            if id(node) in examined:
                continue
            examined.add(id(node))
            if isinstance(node, DictionaryObject):
                if node.get("/S") == "/URI" and "/URI" not in node:
                    raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
                if "/URI" in node:
                    uri = resolve(node.raw_get("/URI"))
                    if isinstance(uri, (TextStringObject, ByteStringObject)):
                        record(uri)
                    elif (node.get("/Type") == "/Catalog" and
                          isinstance(uri, DictionaryObject) and "/Base" in uri):
                        record(uri.raw_get("/Base"))
                    else:
                        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
                # /FS /URL file specs and form-action /F targets can carry URLs.
                # Other action semantics belong to separately scoped inspectors.
                if node.get("/FS") == "/URL" and "/F" in node:
                    target = resolve(node.raw_get("/F"))
                    if not isinstance(target, (TextStringObject, ByteStringObject)):
                        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE)
                    record(target)
                elif node.get("/S") in ("/SubmitForm", "/ImportData") and "/F" in node:
                    target = resolve(node.raw_get("/F"))
                    if isinstance(target, (TextStringObject, ByteStringObject)):
                        value = _read_url(target)
                        if value.lower().startswith(("http:", "https:", "//")):
                            record(target)
                stack.extend(node.raw_get(k) for k in node.keys())
            else:
                stack.extend(node)
        return PDFSuspiciousURLInspection(
            url_count, suspicious_count, tuple(sorted(categories))
        )
    except PDFSuspiciousURLInspectionError:
        raise
    except Exception as exc:
        raise PDFSuspiciousURLInspectionError(BLOCK_MESSAGE) from exc
