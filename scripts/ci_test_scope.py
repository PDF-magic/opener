#!/usr/bin/env python3
"""Conservative dependency-group selection for PDF-magic/opener CI.

Unknown paths and shared scanner/security infrastructure deliberately select
the full suite. This is a group-level dependency map, not filename-only
workflow triggers; central workflows always start and retain a final gate.
"""
from pathlib import Path
import subprocess
import sys

GROUPS = ("pdf", "policy", "maximum", "macos")
ALL_GROUPS = frozenset(GROUPS)

SHARED_SECURITY_FILES = frozenset({
    "scan-and-open.py",
    "scan_results.py",
    "scan_request.py",
    "protection_profiles.py",
    "protection_policy_definitions.py",
    "install-allow-and-open.sh",
    "allow-and-open.sh",
    "update-malware-signatures.sh",
    "requirements-enhanced-pdf.txt",
})

CONFIG_FILES = frozenset({
    "pyproject.toml", "setup.cfg", "tox.ini", "Makefile",
    "Pipfile", "Pipfile.lock", ".python-version",
})

MACOS_TESTS = frozenset({
    "test-scan-progress-component.py",
    "test-maximum-filesystem-sandbox.py",
    "test-maximum-isolated-renderer.py",
    "test-maximum-isolated-analysis.py",
    "test-maximum-process-termination.py",
    "test-maximum-memory-limits.py",
    "test-maximum-sanitizer-memory-limits.py",
    "test-maximum-sanitizer-time-limits.py",
    "test-maximum-sanitized-copy.py",
    "test-maximum-generated-rescan.py",
    "test-maximum-password-protected.py",
    "test-maximum-safe-copy-handoff.py",
    "test-maximum-sanitized-structure.py",
    "test-maximum-network-isolation.py",
})

MACOS_MAXIMUM_FILES = frozenset({
    "maximum_filesystem_sandbox.py",
    "maximum_isolated_renderer.py",
    "maximum_render_worker.py",
    "maximum_network_isolation.py",
    "maximum_sanitizer_process.py",
    "maximum_process_termination.py",
    "maximum_isolated_analysis.py",
    "maximum_isolated_worker.py",
    "maximum_memory_limits.py",
    "maximum_sanitized_copy.py",
    "maximum_generated_rescan.py",
    "maximum_safe_copy_handoff.py",
    "maximum_sanitized_structure.py",
})

TESTED_DOCS = {
    "docs/maximum/renderer-selection.md": "maximum",
    "docs/pdf-parser-evaluation.md": "pdf",
}


def _documentation_only(path):
    if path in {"README.md", "CONTRIBUTING.md", "CHANGELOG.md"}:
        return True
    return path.startswith("docs/") and path.endswith((".md", ".rst"))


def select_groups(paths):
    """Return affected suites; unknown/shared changes conservatively run all."""
    normalized = {str(path).replace("\\", "/") for path in paths}
    if not normalized:
        return ALL_GROUPS

    for path in normalized:
        name = Path(path).name
        if (
            path.startswith(".github/workflows/")
            or path.startswith(".github/scripts/")
            or path.startswith("scripts/")
            or name.startswith("requirements")
            or path in CONFIG_FILES
            or path in SHARED_SECURITY_FILES
        ):
            return ALL_GROUPS

    groups = set()
    for path in normalized:
        if path in TESTED_DOCS:
            groups.add(TESTED_DOCS[path])
            continue
        if _documentation_only(path):
            continue

        name = Path(path).name
        if path.startswith("PDFMagicOpenerApp/") or path.startswith("PDFMagicOpener.xcodeproj/"):
            groups.add("macos")
            continue
        if path.endswith((".swift", ".entitlements", ".sb", ".applescript")):
            groups.add("macos")
            continue
        if name in MACOS_TESTS or name in MACOS_MAXIMUM_FILES:
            groups.update(("maximum", "macos"))
            continue

        if name.startswith("pdf_") or name.startswith("test-pdf-") or name == "pdf_parser_memory_benchmark.py":
            groups.add("pdf")
            continue
        if name.startswith("enhanced_") or name.startswith("test-enhanced-"):
            groups.update(("pdf", "policy"))
            continue
        if (
            name.startswith("protection_")
            or name.startswith("test-protection-")
            or name.startswith("test-scan-")
            or name.startswith("test-detection-")
            or name.startswith("test-clamav-")
            or name in {
                "test-scan-and-open.py", "test-combined-scan-results.py",
                "test-document-security-report.py", "test-effective-policy-display.py",
                "test-stable-finding-identifiers.py",
            }
        ):
            groups.add("policy")
            continue
        if name.startswith("maximum_") or name.startswith("test-maximum-") or name == "test-opened-document-origin.py":
            groups.add("maximum")
            continue

        # New or unclassified source/test files are not silently omitted.
        return ALL_GROUPS

    return frozenset(groups)


def changed_paths(base_sha, head_sha):
    if not base_sha or not head_sha:
        raise ValueError("missing comparison SHAs")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", base_sha, head_sha],
        check=True, capture_output=True, text=True, timeout=30,
    )
    return [line for line in result.stdout.splitlines() if line]


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: ci_test_scope.py BASE_SHA HEAD_SHA GITHUB_OUTPUT")
    base_sha, head_sha, output_path = sys.argv[1:]
    reason = "diff"
    try:
        paths = changed_paths(base_sha, head_sha)
        if not paths:
            reason = "empty-diff; conservative full suite"
            groups = ALL_GROUPS
        else:
            groups = select_groups(paths)
    except (OSError, ValueError, subprocess.SubprocessError):
        paths = []
        groups = ALL_GROUPS
        reason = "diff-unavailable; conservative full suite"

    with Path(output_path).open("a", encoding="utf-8") as output:
        for group in GROUPS:
            output.write(f"run_{group}={'true' if group in groups else 'false'}\n")
        output.write(f"changed_file_count={len(paths)}\n")
        output.write(f"scope_reason={reason}\n")

    selected = ", ".join(f"{group}={'yes' if group in groups else 'no'}" for group in GROUPS)
    print(f"CI dependency scope: {selected}; changed files={len(paths)}; reason={reason}")


if __name__ == "__main__":
    main()
