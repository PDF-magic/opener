# Enhanced PDF object-relationship inspection (opener-0284)

The optional `pdf_object_relationships.inspect_pdf_object_relationships(bytes)`
entry point inspects relationships between parsed PDF objects using the same
maintained, pinned `pypdf` dependency introduced in
[PR #179](https://github.com/PDF-magic/opener/pull/179) (opener-0283).
The input is immutable PDF bytes, never a filesystem path. Its immutable result
records object count, indirect-reference count, and verified page count.

## Checked relationships

- Enumerates indirect objects from strict cross-reference entries and
  validates every indirect link, including its generation and target existence.
- Checks the document catalog's page-tree root, each `/Pages` → `/Kids`
  relationship, every `/Page` → `/Parent` backlink, nested `/Count` values,
  cycles and shared page children. Legitimate upward `/Parent` references do
  not count as malicious graph cycles.
- Traverses dictionaries and arrays but never interprets text or stream
  contents as indirect references. Invalid structures yield only fixed,
  path-free errors rather than PDF contents or local filenames.
- Rejects encrypted documents, unsupported compressed object streams,
  missing dependencies, unresolvable references, and excessive graph sizes.
  Limits are 16 MiB of input, 4,096 objects, 65,536 references, 64 levels of
  nesting and the shared parser's 1,024-page limit.

**Boundary:** This is not a full PDF-security validator. No result grants
permission to open a PDF. Enhanced remains non-selectable, and the installed
Built-in ClamAV gate does **not** call this module. The existing signature
freshness, clean-cache, file-integrity, quarantine and app-handoff controls
remain unchanged. Before production Enhanced integration, parsing of untrusted
PDFs requires an isolated process with enforced CPU, wall-time and memory
limits and a completed, independently reviewed structural and feature policy.

The focused CI suite uses generated harmless PDFs and the existing reference
corpus, including explicit malformed and adversarial object-graph cases. It
runs after the dependency parser tests in `scanner-tests`; the full
`macos-build` job remains required before merging.