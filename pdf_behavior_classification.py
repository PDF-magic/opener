"""Conservative, passive classification of PDF behaviors for planned Enhanced checks.

The caller must have inspected the PDF already. This module consumes fixed,
path-free evidence, not PDF bytes, URLs, script text, or executable commands.
It never grants permission to open a document, replaces a required scan, or
activates the currently non-selectable Enhanced profile (opener-0298).
"""

from dataclasses import dataclass
from enum import Enum

from pdf_external_launch_actions import PDFExternalLaunchInspection


MAX_OBSERVATIONS = 512
BLOCK_MESSAGE = "PDF behavior evidence could not be classified; opening was stopped."


class BehaviorClassificationError(RuntimeError):
    """Invalid or unsupported evidence must not become a benign finding."""


class PDFBehaviorKind(str, Enum):
    INTERNAL_NAVIGATION = "internal_navigation"
    BOOKMARK = "bookmark"
    TEXT_ANNOTATION = "text_annotation"
    FORM_FIELD = "form_field"
    FILE_ATTACHMENT = "file_attachment"
    URI_LINK = "uri_link"
    REMOTE_NAVIGATION = "remote_navigation"
    EMBEDDED_NAVIGATION = "embedded_navigation"
    FORM_SUBMISSION = "form_submission"
    FORM_IMPORT = "form_import"
    JAVASCRIPT_ACTION = "javascript_action"
    SCRIPT_NETWORK_ACCESS = "script_network_access"
    SCRIPT_FILE_ACCESS = "script_file_access"
    SCRIPT_DYNAMIC_EXECUTION = "script_dynamic_execution"
    EXECUTABLE_LAUNCH = "executable_launch"


class PDFBehaviorTrigger(str, Enum):
    USER = "user"
    AUTOMATIC = "automatic"
    UNKNOWN = "unknown"


class PDFBehaviorDisposition(str, Enum):
    UNASSESSED = "unassessed"
    LEGITIMATE_FEATURE = "legitimate_feature"
    REQUIRES_REVIEW = "requires_review"
    DANGEROUS_BEHAVIOR = "dangerous_behavior"


_PASSIVE = frozenset((
    PDFBehaviorKind.INTERNAL_NAVIGATION,
    PDFBehaviorKind.BOOKMARK,
    PDFBehaviorKind.TEXT_ANNOTATION,
    PDFBehaviorKind.FORM_FIELD,
    PDFBehaviorKind.FILE_ATTACHMENT,
))
_HIGH_RISK = frozenset((
    PDFBehaviorKind.EXECUTABLE_LAUNCH,
    PDFBehaviorKind.SCRIPT_NETWORK_ACCESS,
    PDFBehaviorKind.SCRIPT_FILE_ACCESS,
    PDFBehaviorKind.SCRIPT_DYNAMIC_EXECUTION,
))
_AUTOMATIC_RISK = frozenset((
    PDFBehaviorKind.URI_LINK,
    PDFBehaviorKind.REMOTE_NAVIGATION,
    PDFBehaviorKind.FORM_SUBMISSION,
    PDFBehaviorKind.FORM_IMPORT,
))
_USER_NAVIGATION = frozenset((
    PDFBehaviorKind.URI_LINK,
    PDFBehaviorKind.EMBEDDED_NAVIGATION,
))


@dataclass(frozen=True)
class PDFBehaviorObservation:
    """A category established by an inspector, without document-supplied text."""

    kind: PDFBehaviorKind
    trigger: PDFBehaviorTrigger = PDFBehaviorTrigger.UNKNOWN

    def __post_init__(self):
        if (not isinstance(self.kind, PDFBehaviorKind) or
                not isinstance(self.trigger, PDFBehaviorTrigger)):
            raise BehaviorClassificationError(BLOCK_MESSAGE)


@dataclass(frozen=True)
class PDFBehaviorFinding:
    kind: PDFBehaviorKind
    trigger: PDFBehaviorTrigger
    disposition: PDFBehaviorDisposition


@dataclass(frozen=True)
class PDFBehaviorAnalysis:
    """Partial evidence only. Even legitimate features cannot authorize opening."""

    findings: tuple[PDFBehaviorFinding, ...]
    highest_disposition: PDFBehaviorDisposition
    permits_open: bool = False
    pdf_is_clean: bool = False

    def __post_init__(self):
        if (type(self.findings) is not tuple or
                any(type(x) is not PDFBehaviorFinding for x in self.findings) or
                len(self.findings) > MAX_OBSERVATIONS or
                not isinstance(self.highest_disposition, PDFBehaviorDisposition) or
                self.permits_open is not False or self.pdf_is_clean is not False):
            raise BehaviorClassificationError(BLOCK_MESSAGE)

    @property
    def has_dangerous_behavior(self):
        return any(x.disposition is PDFBehaviorDisposition.DANGEROUS_BEHAVIOR
                   for x in self.findings)


def _disposition(observation: PDFBehaviorObservation) -> PDFBehaviorDisposition:
    kind, trigger = observation.kind, observation.trigger
    if kind in _HIGH_RISK or (trigger is PDFBehaviorTrigger.AUTOMATIC and
                              kind in _AUTOMATIC_RISK):
        return PDFBehaviorDisposition.DANGEROUS_BEHAVIOR
    if kind in _PASSIVE or (trigger is PDFBehaviorTrigger.USER and
                            kind in _USER_NAVIGATION):
        return PDFBehaviorDisposition.LEGITIMATE_FEATURE
    # JavaScript can implement legitimate forms, but lexical hints cannot
    # prove it benign. Unknown triggers and external data flows need review.
    return PDFBehaviorDisposition.REQUIRES_REVIEW


def classify_pdf_behavior(observations: tuple[PDFBehaviorObservation, ...]
                          ) -> PDFBehaviorAnalysis:
    """Classify bounded validated evidence, without evaluating or trusting it.

    An empty observation set means *unassessed*, not 'clean'. Legitimate
    features are normal capabilities, not proof that the surrounding PDF,
    attachment, link destination, or JavaScript is trustworthy.
    """
    if (type(observations) is not tuple or len(observations) > MAX_OBSERVATIONS or
            any(type(item) is not PDFBehaviorObservation for item in observations)):
        raise BehaviorClassificationError(BLOCK_MESSAGE)
    findings = tuple(PDFBehaviorFinding(item.kind, item.trigger, _disposition(item))
                     for item in observations)
    levels = {item.disposition for item in findings}
    highest = next((
        level for level in (
            PDFBehaviorDisposition.DANGEROUS_BEHAVIOR,
            PDFBehaviorDisposition.REQUIRES_REVIEW,
            PDFBehaviorDisposition.LEGITIMATE_FEATURE,
        ) if level in levels
    ), PDFBehaviorDisposition.UNASSESSED)
    return PDFBehaviorAnalysis(findings, highest)


_EXTERNAL_KINDS = {
    "launch": PDFBehaviorKind.EXECUTABLE_LAUNCH,
    "remote_goto": PDFBehaviorKind.REMOTE_NAVIGATION,
    "embedded_goto": PDFBehaviorKind.EMBEDDED_NAVIGATION,
    "uri": PDFBehaviorKind.URI_LINK,
    "submit_form": PDFBehaviorKind.FORM_SUBMISSION,
    "import_data": PDFBehaviorKind.FORM_IMPORT,
}


def classify_external_action_inspection(
    report: PDFExternalLaunchInspection,
) -> PDFBehaviorAnalysis:
    """Bridge the already-implemented external-action inspector, not a parser.

    Its aggregate action kinds do not identify whether an action was clicked
    or automatic. All such triggers MUST remain unknown. In particular a URI
    action is not an executable launch, but it is not assumed user-initiated.
    """
    if type(report) is not PDFExternalLaunchInspection:
        raise BehaviorClassificationError(BLOCK_MESSAGE)
    try:
        observations = tuple(PDFBehaviorObservation(_EXTERNAL_KINDS[kind])
                             for kind in report.action_kinds)
    except (KeyError, TypeError, ValueError) as exc:
        raise BehaviorClassificationError(BLOCK_MESSAGE) from exc
    return classify_pdf_behavior(observations)
