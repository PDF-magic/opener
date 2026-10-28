"""Run allowlisted complex PDF inspections in a bounded child process.

An opt-in building block for planned Maximum protection (opener-0306).
Never a PDF clean verdict and never connected to the deployed ClamAV gate.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from types import MappingProxyType

MAX_PDF_BYTES = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 4096
WORKER_WALL_TIMEOUT_SECONDS = 30
WORKER_CPU_SECONDS = 25
WORKER_MEMORY_MIB = 1024
BLOCK_MESSAGE = "Isolated PDF analysis could not complete; opening was stopped."

# Trusted literal dispatch: no document-controlled path, import, executable,
# function or shell command may be supplied. Additional inspections are a
# separate reviewed change, not inferred from arbitrary caller-provided strings.
_INSPECTORS = MappingProxyType({
    "structureAmbiguity": (
        "pdf_structure_ambiguity", "inspect_pdf_structure_ambiguity",
        ("inspected_objects",),
    ),
    "malformedStructures": (
        "pdf_malformed_structures", "inspect_pdf_malformed_structures",
        ("object_count", "page_count"),
    ),
    "decompressionRequirements": (
        "pdf_decompression_requirements", "inspect_pdf_decompression_requirements",
        ("stream_count", "flate_stream_count", "decoded_bytes",
         "maximum_expansion_ratio"),
    ),
})


class IsolatedPDFAnalysisError(RuntimeError):
    """Fixed path-free failure; never expose PDF contents or child diagnostics."""


@dataclass(frozen=True)
class IsolatedPDFAnalysis:
    inspection: str
    worker_pid: int
    metrics: tuple[tuple[str, int], ...]
    permits_open: bool = False

    def __post_init__(self):
        if (type(self.inspection) is not str or self.inspection not in _INSPECTORS or
                type(self.worker_pid) is not int or self.worker_pid <= 0 or
                type(self.metrics) is not tuple or
                tuple(name for name, _ in self.metrics) != _INSPECTORS[self.inspection][2] or
                any(type(v) is not int or not 0 <= v <= 2**31 - 1
                    for _, v in self.metrics) or self.permits_open is not False):
            raise ValueError("Isolated analysis is not permission to open a PDF")

    def to_dict(self) -> dict:
        return {
            "inspection": self.inspection,
            "workerPid": self.worker_pid,
            "metrics": dict(self.metrics),
            "permitsOpen": False,
        }


def _unique_json_pairs(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("Duplicate result key")
        document[key] = value
    return document


def run_isolated_pdf_analysis(contents: bytes, inspection: str) -> IsolatedPDFAnalysis:
    """Run one static inspector in a separate limited interpreter.

    Input is in-memory PDF bytes via stdin. An isolated Python interpreter
    ignores user-site configuration and Python environment variables. The
    child applies CPU, memory and no-filesystem-output rlimits before any PDF
    parser import; wall-clock expiry kills it. No shell, temp files or PDF paths
    are passed to the worker. Failure is always non-clean and path-free.

    This is process/resource isolation, not a full OS network sandbox. It does
    not replace host file identity, mandatory scanner gates or quarantine.
    """
    if (type(contents) is not bytes or not 0 < len(contents) <= MAX_PDF_BYTES or
            type(inspection) is not str or inspection not in _INSPECTORS):
        raise IsolatedPDFAnalysisError(BLOCK_MESSAGE)

    worker = Path(__file__).resolve().with_name("maximum_isolated_worker.py")
    command = [sys.executable, "-I", "-B", str(worker), inspection]
    try:
        completed = subprocess.run(
            command,
            input=contents,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=WORKER_WALL_TIMEOUT_SECONDS,
            check=False,
            close_fds=True,
            start_new_session=True,
            cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "LANG": "C",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            },
        )
        if (completed.returncode != 0 or
                type(completed.stdout) is not bytes or
                not 0 < len(completed.stdout) <= MAX_RESPONSE_BYTES):
            raise IsolatedPDFAnalysisError(BLOCK_MESSAGE)
        response = json.loads(completed.stdout, object_pairs_hook=_unique_json_pairs)
        if (type(response) is not dict or
                set(response) != {"protocol", "inspection", "workerPid",
                                  "metrics", "permitsOpen"} or
                type(response["protocol"]) is not int or response["protocol"] != 1 or
                response["inspection"] != inspection or
                response["permitsOpen"] is not False or
                type(response["metrics"]) is not dict or
                set(response["metrics"]) != set(_INSPECTORS[inspection][2])):
            raise IsolatedPDFAnalysisError(BLOCK_MESSAGE)
        return IsolatedPDFAnalysis(
            inspection,
            response["workerPid"],
            tuple((key, response["metrics"][key])
                  for key in _INSPECTORS[inspection][2]),
        )
    except Exception:
        raise IsolatedPDFAnalysisError(BLOCK_MESSAGE) from None
