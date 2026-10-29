# Passive PDF behavior classification (opener-0298)

PDFs can contain legitimate links, navigation, bookmarks, annotations, forms,
and attachments. Their mere presence is not evidence of malicious execution.
Conversely, a normal form or link must not hide a launch instruction or a
privileged script action elsewhere in the document.

`pdf_behavior_classification.classify_pdf_behavior` classifies **validated
metadata from an inspector**, never executes actions or parses untrusted bytes.
The supported evidence kinds and trigger categories are fixed enums. User
provided URLs, local filenames, script bodies, and other PDF strings cannot
appear in the resulting findings. Unknown kinds, malformed inputs, and overly
large evidence collections raise a fixed, path-free classification error.

- **Legitimate PDF feature**: ordinary navigation, bookmarks, text annotations,
  form fields, attachment references, and explicitly user-triggered URI links or
  embedded navigation. This means only that the *feature type* is ordinary;
  it says nothing about the safety of its destination or embedded payload.
- **Requires review**: JavaScript actions (even in forms), form submission and
  import, external navigation, or a link whose trigger is not established. A
  lack of lexical JavaScript hints never proves that a script is harmless.
- **Dangerous behavior**: launch actions and evidence of privileged file/network
  script operations or dynamic execution, as well as automatic external link
  navigation, remote navigation, form submission, or import. These are
  **dangerous capabilities**, not claims that an operation actually executed.

When any dangerous observation coexists with legitimate content, the maximum
severity remains dangerous. With no findings the result is **unassessed**, not
clean. Every result has `permits_open=False` and `pdf_is_clean=False`;
classification never overrides ClamAV, cached-scan integrity verification,
quarantine, launch checks or individual user preferences.

## Integration boundary

`classify_external_action_inspection` consumes the existing passive findings
from `pdf_external_launch_actions.inspect_pdf_external_launch_actions`.
Those findings summarize action *kinds*, not trigger placement, so it keeps
triggers `unknown` and does not assume a URI action required a user click.
The bridge does not read a file or reparse a PDF.

The optional automatic-action and JavaScript inspection work in
[PR #183](https://github.com/PDF-magic/opener/pull/183) and
[PR #184](https://github.com/PDF-magic/opener/pull/184), respectively, has not
yet been merged into the installed scanner. Once those separately scoped
inspectors and structured findings are available, a later Enhanced pipeline
can supply their trusted trigger/evidence categories here. This task does
not duplicate that parsing work or assert that lexical hints detect all
hazards.

The active Built-in ClamAV scan gate remains the only selectable protection.
No automatic behavior analysis is activated, and the classifier alone is
**not a security or opening decision**. A future integrated stage must still
provide complete bounded inspection, enforce resource/time limits, and fail
closed on unknown/unsupported PDFs before any profile is selectable.
