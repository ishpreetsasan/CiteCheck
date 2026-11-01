
"""
citecheck.core.engine
---------------------
Central auditing engine and backend entry point for CiteCheck.
"""

import re
from typing import Optional

from citecheck.models.schemas import (
    AuditReport,
    AuditSummary,
    Claim,
    ClaimType,
    CorrectionResult,
    Decision,
    MathResult,
    SentenceCorrection,
)

from citecheck.verifiers.math_auditor import (
    audit_claim_math,
    _extract_math_operation,
)

from citecheck.verifiers.factual_verifier import (
    verify_author_claim,
    verify_developer_claim,
)


def _split_into_claims(text: str) -> list[Claim]:
    """Decompose raw answer into claims by sentences or line breaks."""

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    raw_sentences = []

    for line in lines:
        sentences = re.split(r"(?<=[.!?])\s+", line)

        for sentence in sentences:
            if sentence.strip():
                raw_sentences.append(sentence.strip())

    if not raw_sentences:
        raw_sentences = [text.strip()]

    claims = []

    for idx, sentence in enumerate(raw_sentences, start=1):
        has_math = _extract_math_operation(sentence) is not None

        claim_type = (
            ClaimType.MATHEMATICAL
            if has_math
            else ClaimType.FACTUAL
        )

        claims.append(
            Claim(
                id=f"claim_{idx}",
                claim_text=sentence,
                claim_type=claim_type,
                source_sentence=sentence,
            )
        )

    return claims


def _detect_relationship_claim(claim: Claim):
    """Identify author and software-developer claims."""

    text = claim.claim_text.strip()

    # Example: George Orwell wrote 1984.
    author_match = re.match(
        r"^(.+?)\s+wrote\s+(?:the novel\s+|the book\s+)?(.+?)[.!?]*$",
        text,
        re.IGNORECASE,
    )

    if author_match:
        author = author_match.group(1).strip()
        work = author_match.group(2).strip()

        return verify_author_claim(
            claim_id=claim.id,
            query=f"Who wrote {work}?",
            claimed_author=author,
        )

    # Example: Python was developed by Guido van Rossum.
    developer_match = re.match(
        r"^(.+?)\s+was developed by\s+(.+?)[.!?]*$",
        text,
        re.IGNORECASE,
    )

    if developer_match:
        software = developer_match.group(1).strip()
        developer = developer_match.group(2).strip()

        return verify_developer_claim(
            claim_id=claim.id,
            query=f"Who developed {software}?",
            claimed_developer=developer,
        )

    return None


def audit_answer(
    original_answer: str,
    reference_context: Optional[str] = None,
) -> AuditReport:
    """
    Main backend entry point.

    Mathematical claims are checked deterministically.
    Recognized author and developer claims are checked using
    structured Wikidata evidence.
    Other factual claims remain unverified.
    """

    # Handle empty input.
    if not isinstance(original_answer, str) or not original_answer.strip():
        return AuditReport(
            decision=Decision.NEEDS_HUMAN_REVIEW,
            decision_reasons=[
                "Empty input provided; nothing to audit."
            ],
            original_answer=original_answer or "",
            summary=AuditSummary(
                total_claims=0,
                supported_claims=0,
                partially_supported_claims=0,
                unsupported_claims=0,
                math_errors=0,
                citation_issues=0,
                overview_text="No claims extracted from empty input.",
            ),
            claims=[],
            citation_results=[],
            math_results=[],
            factual_results=[],
            corrections=CorrectionResult(
                corrected_text=original_answer or "",
                sentence_corrections=[],
                total_modifications=0,
            ),
        )

    # 1. Claim Decomposition
    claims = _split_into_claims(original_answer)

    # 2. Mathematical Auditing
    math_results: list[MathResult] = []

    for claim in claims:
        result = audit_claim_math(claim)

        if result.operations:
            math_results.append(result)

    # 3. Factual Auditing
    factual_results = []

    for claim in claims:
        if claim.claim_type == ClaimType.FACTUAL:
            factual_result = _detect_relationship_claim(claim)

            if factual_result is not None:
                factual_results.append(factual_result)

    # 4. Analyze Math Results
    math_errors = sum(
        1 for result in math_results
        if result.has_math_error
    )

    supported_math = sum(
        1 for result in math_results
        if result.operations and not result.has_math_error
    )

    # 5. Conservative Math Corrections
    sentence_corrections: list[SentenceCorrection] = []
    corrected_sentences = []

    for claim in claims:
        claim_corrected = claim.claim_text

        matching_result = next(
            (
                result
                for result in math_results
                if result.claim_id == claim.id
            ),
            None,
        )

        if matching_result and matching_result.has_math_error:
            for operation in matching_result.operations:

                if (
                    not operation.is_correct
                    and operation.calculated_value
                    not in ("UNDEFINED", "ERROR")
                ):
                    old_value = operation.claimed_value
                    new_value = operation.calculated_value

                    if old_value in claim_corrected:
                        claim_corrected = claim_corrected.replace(
                            old_value,
                            new_value,
                        )

                        sentence_corrections.append(
                            SentenceCorrection(
                                original_sentence=claim.source_sentence,
                                corrected_sentence=claim_corrected,
                                preserved_parts=[
                                    claim.source_sentence.replace(
                                        old_value, ""
                                    )
                                ],
                                modified_or_removed_parts=[
                                    f"{old_value} -> {new_value}"
                                ],
                                correction_type="MATH_FIXED",
                                reason=(
                                    "Deterministic correction: replaced "
                                    f"incorrect value '{old_value}' "
                                    f"with '{new_value}'."
                                ),
                            )
                        )

        corrected_sentences.append(claim_corrected)

    corrected_full_text = " ".join(corrected_sentences)

    # 6. Analyze Factual Results
    supported_factual = sum(
        1 for result in factual_results
        if result.status.value == "SUPPORTED"
    )

    partial_factual = sum(
        1 for result in factual_results
        if result.status.value == "PARTIALLY_SUPPORTED"
    )

    unsupported_factual = sum(
        1 for result in factual_results
        if result.status.value == "UNSUPPORTED"
    )

    unverified_factual = sum(
        1 for result in factual_results
        if result.status.value == "INSUFFICIENT_EVIDENCE"
    )

    supported_claims = supported_math + supported_factual

    # 7. Overall Decision Logic
    decision_reasons: list[str] = []

    if math_errors > 0:
        decision = Decision.REVISE

        decision_reasons.append(
            f"Detected {math_errors} mathematical calculation error(s)."
        )

        for math_result in math_results:
            if math_result.has_math_error:
                for operation in math_result.operations:
                    if not operation.is_correct:
                        decision_reasons.append(
                            f"Arithmetic failure: {operation.explanation}"
                        )

    elif unsupported_factual > 0:
        decision = Decision.REVISE

        decision_reasons.append(
            f"{unsupported_factual} factual claim(s) were marked unsupported."
        )

    elif (
        supported_claims == len(claims)
        and partial_factual == 0
        and unverified_factual == 0
    ):
        decision = Decision.PASS

        decision_reasons.append(
            "All extracted claims were verified."
        )

    else:
        decision = Decision.NEEDS_HUMAN_REVIEW

        if partial_factual:
            decision_reasons.append(
                f"{partial_factual} factual claim(s) were partially supported."
            )

        if unverified_factual:
            decision_reasons.append(
                f"{unverified_factual} factual claim(s) need more evidence."
            )

        if supported_math:
            decision_reasons.append(
                f"{supported_math} mathematical calculation(s) passed."
            )

        if supported_factual:
            decision_reasons.append(
                f"{supported_factual} factual claim(s) were supported."
            )

        if not decision_reasons:
            decision_reasons.append(
                "Some claims could not be verified by the available verifiers."
            )

    # 8. Structured Summary
    summary = AuditSummary(
        total_claims=len(claims),
        supported_claims=supported_claims,
        partially_supported_claims=partial_factual,
        unsupported_claims=unsupported_factual,
        math_errors=math_errors,
        citation_issues=0,
        overview_text=(
            f"Audited {len(claims)} claim(s). "
            f"{supported_math} mathematical calculation(s) verified. "
            f"{supported_factual} factual claim(s) supported. "
            f"{partial_factual} partially supported. "
            f"{unverified_factual} requiring more evidence. "
            f"{math_errors} mathematical error(s) found."
        ),
    )

    # 9. Final Audit Report
    return AuditReport(
        decision=decision,
        decision_reasons=decision_reasons,
        original_answer=original_answer,
        summary=summary,
        claims=claims,
        citation_results=[],
        math_results=math_results,
        factual_results=factual_results,
        corrections=CorrectionResult(
            corrected_text=corrected_full_text,
            sentence_corrections=sentence_corrections,
            total_modifications=len(sentence_corrections),
        ),
    )
