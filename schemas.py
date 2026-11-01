"""
citecheck.models.schemas
------------------------
Canonical Pydantic schemas defining the single backend contract for CiteCheck.
Owned by Person 2; consumed by Person 1 (UI) and Person 4 (QA).
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Decision(str, Enum):
    """Overall auditing decision for the audited text."""
    PASS = "PASS"
    REVISE = "REVISE"
    BLOCK = "BLOCK"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"


class ClaimType(str, Enum):
    """Classification of an extracted atomic claim."""
    FACTUAL = "FACTUAL"
    MATHEMATICAL = "MATHEMATICAL"
    CITATION_BASED = "CITATION_BASED"


class CitationStatus(str, Enum):
    """
    Status of an audited citation.
    Distinguishes definitively broken links from temporary server/network issues.
    """
    VERIFIED = "VERIFIED"                      # URL accessible, quote matches, content directly supports claim
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"# URL accessible, partially backs up claim, minor nuance missing
    BROKEN = "BROKEN"                          # Definitive 404, 410, or DNS failure
    MISSING = "MISSING"                        # Claim refers to an external source but provides no link/reference
    IRRELEVANT = "IRRELEVANT"                  # Page loads, but content has no semantic relation to claim
    UNSUPPORTED = "UNSUPPORTED"                # Page relevant, but contradicts or fails to support claim
    UNVERIFIABLE = "UNVERIFIABLE"              # Timeout, 5xx server error, Cloudflare bot challenge, or parse failure


class FactualStatus(str, Enum):
    """
    Status of a factual claim against retrieved evidence or provided context.
    INSUFFICIENT_EVIDENCE is strictly kept distinct from UNSUPPORTED:
    lack of evidence alone is never treated as a contradiction.
    """
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class MathOpType(str, Enum):
    """Type of deterministic mathematical operation evaluated."""
    TOTAL = "TOTAL"
    AVERAGE = "AVERAGE"
    PERCENTAGE = "PERCENTAGE"
    DISCOUNT = "DISCOUNT"
    PERCENTAGE_CHANGE = "PERCENTAGE_CHANGE"
    OTHER = "OTHER"


# --- Sub-Models ---

class Claim(BaseModel):
    """An individual atomic claim extracted from the original answer."""
    id: str                                    # e.g. "claim_1"
    claim_text: str
    claim_type: ClaimType
    source_sentence: str


class EvidenceItem(BaseModel):
    """
    Preserved evidence grounding a factual verification verdict.
    Guarantees exact excerpt preservation and source traceability.
    """
    source_uri_or_name: str
    extracted_snippet: str
    is_sufficient: bool = True
    notes: Optional[str] = None


class CitationResult(BaseModel):
    """Audit result for a single citation or cited claim."""
    claim_id: str
    url: Optional[str] = None
    status: CitationStatus
    http_status_code: Optional[int] = None
    extracted_title: Optional[str] = None
    quoted_text: Optional[str] = None
    quote_matched: bool = False
    support_explanation: str


class MathOperation(BaseModel):
    """Deterministic arithmetic verification evaluated via Python Decimal."""
    op_type: MathOpType
    expression_detected: str                  # e.g., "100 - (100 * 0.20)"
    claimed_value: str                        # e.g., "75"
    calculated_value: str                     # e.g., "80.00" derived deterministically
    is_correct: bool
    explanation: str


class MathResult(BaseModel):
    """Collection of math operations tied to an atomic claim."""
    claim_id: str
    operations: list[MathOperation] = Field(default_factory=list)
    has_math_error: bool = False


class FactualResult(BaseModel):
    """Grounding verification for a factual claim."""
    claim_id: str
    status: FactualStatus
    evidence: Optional[EvidenceItem] = None   # None if status == INSUFFICIENT_EVIDENCE
    rationale: str


class SentenceCorrection(BaseModel):
    """
    Sentence-level revision preserving verified portions of mixed sentences.
    Minimally corrects or prunes only erroneous/unsupported portions.
    """
    original_sentence: str
    corrected_sentence: str
    preserved_parts: list[str] = Field(default_factory=list)
    modified_or_removed_parts: list[str] = Field(default_factory=list)
    correction_type: str                      # "PRUNED_UNSUPPORTED", "MATH_FIXED", "UNTOUCHED"
    reason: str


class CorrectionResult(BaseModel):
    """
    Output of the No-New-Claims conservative correction engine.
    Ensures zero invented facts or hallucinations in the corrected text.
    """
    corrected_text: str
    sentence_corrections: list[SentenceCorrection] = Field(default_factory=list)
    total_modifications: int = 0
    guarantee_policy: str = "Preserved supported content; removed or fixed only verified errors; zero invented facts."


class AuditSummary(BaseModel):
    """Structured counts and high-level summary of the audit."""
    total_claims: int = 0
    supported_claims: int = 0
    partially_supported_claims: int = 0
    unsupported_claims: int = 0
    math_errors: int = 0
    citation_issues: int = 0                  # Sum of broken, missing, irrelevant, unsupported, unverifiable
    overview_text: str                        # Concise high-level summary statement


# --- Root Audit Report ---

class AuditReport(BaseModel):
    """
    Canonical audit report returned by audit_answer().
    Single contract adhered to by Backend, UI, and QA.
    """
    decision: Decision
    decision_reasons: list[str] = Field(default_factory=list)
    original_answer: str
    summary: AuditSummary
    claims: list[Claim] = Field(default_factory=list)
    citation_results: list[CitationResult] = Field(default_factory=list)
    math_results: list[MathResult] = Field(default_factory=list)
    factual_results: list[FactualResult] = Field(default_factory=list)
    corrections: CorrectionResult
