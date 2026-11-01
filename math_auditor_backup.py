"""
citecheck.verifiers.math_auditor
--------------------------------
Deterministic mathematical verification engine.
Extracts mathematical statements, evaluates them using safe_math,
and compares claimed values with computed results using precision-adaptive rounding.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Optional

from citecheck.models.schemas import Claim, ClaimType, MathOpType, MathOperation, MathResult
from citecheck.utils.safe_math import (
    evaluate_expression,
    SafeDivisionByZeroError,
    SafeMathError,
)


def _extract_math_operation(text: str) -> Optional[tuple[MathOpType, str, str]]:
    """
    Conservatively extract a mathematical operation from text.
    Returns (MathOpType, expression_string, claimed_value_string) or None if ambiguous.
    """
    cleaned = text.strip()

    # 1. Explicit Arithmetic Equations: e.g. "12.5 + 7.5 = 20" or "(10 + 20) / 2 = 15"
    eq_pat = re.compile(
        r"([0-9\.\(\)\s]+[\+\-\*\/][0-9\.\(\)\s\+\-\*\/]+)\s*=\s*([0-9]+(?:\.[0-9]+)?)"
    )
    m = eq_pat.search(cleaned)
    if m:
        expr_cand = m.group(1).strip()
        claimed_cand = m.group(2).strip()
        # Verify it has at least one arithmetic operator
        if any(op in expr_cand for op in ["+", "-", "*", "/"]):
            return MathOpType.OTHER, expr_cand, claimed_cand

    # 2. Discounts: e.g. "A 20% discount on 100 is 80" or "20% discount on $100 is $80"
    disc_pat1 = re.compile(
        r"(?:a\s+)?([0-9]+(?:\.[0-9]+)?)\s*%\s+discount\s+on\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)\s+(?:is|equals|=)\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    m = disc_pat1.search(cleaned)
    if m:
        rate, base, claimed = m.groups()
        return MathOpType.DISCOUNT, f"{base} - ({base} * ({rate} / 100))", claimed

    # 2b. Discounts alternative syntax: e.g. "$100 with a 20% discount is $80"
    disc_pat2 = re.compile(
        r"[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)\s+with\s+(?:a\s+)?([0-9]+(?:\.[0-9]+)?)\s*%\s+discount\s+(?:is|equals|=)\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    m = disc_pat2.search(cleaned)
    if m:
        base, rate, claimed = m.groups()
        return MathOpType.DISCOUNT, f"{base} - ({base} * ({rate} / 100))", claimed

    # 3. Percentages of a number: e.g. "15% of 200 is 30"
    pct_pat = re.compile(
        r"([0-9]+(?:\.[0-9]+)?)\s*%\s+of\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)\s+(?:is|equals|=)\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    m = pct_pat.search(cleaned)
    if m:
        rate, base, claimed = m.groups()
        return MathOpType.PERCENTAGE, f"({rate} / 100) * {base}", claimed

    # 4. Percentage Change: e.g. "increased from 50 to 75, a 50% increase"
    pct_change_pat = re.compile(
        r"(?:from\s+)?[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)\s+to\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)[,\s]+(?:is\s+|a\s+)?([0-9]+(?:\.[0-9]+)?)\s*%\s+(?:increase|decrease|growth|drop|change)",
        re.IGNORECASE,
    )
    m = pct_change_pat.search(cleaned)
    if m:
        from_val, to_val, claimed = m.groups()
        return MathOpType.PERCENTAGE_CHANGE, f"(({to_val} - {from_val}) / {from_val}) * 100", claimed

    # 5. Totals / Sums: e.g. "total of 10, 20 and 30 is 60"
    tot_pat = re.compile(
        r"(?:total|sum)\s+of\s+([0-9\.,\s\$€£and]+?)\s+(?:is|equals|=)\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    m = tot_pat.search(cleaned)
    if m:
        nums = re.findall(r"[0-9]+(?:\.[0-9]+)?", m.group(1))
        if len(nums) >= 2:
            return MathOpType.TOTAL, " + ".join(nums), m.group(2).strip()

    # 6. Averages / Means: e.g. "average of 10, 20 and 30 is 20"
    avg_pat = re.compile(
        r"(?:average|mean)\s+of\s+([0-9\.,\s\$€£and]+?)\s+(?:is|equals|=)\s+[\$€£]?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    m = avg_pat.search(cleaned)
    if m:
        nums = re.findall(r"[0-9]+(?:\.[0-9]+)?", m.group(1))
        if len(nums) >= 2:
            return MathOpType.AVERAGE, f"({' + '.join(nums)}) / {len(nums)}", m.group(2).strip()

    # Ambiguous or non-extractable
    return None


def audit_claim_math(claim: Claim) -> MathResult:
    """
    Audits a single Claim object for mathematical operations.
    Returns MathResult with operations and has_math_error status.
    """
    extracted = _extract_math_operation(claim.claim_text)
    if not extracted and claim.source_sentence and claim.source_sentence != claim.claim_text:
        extracted = _extract_math_operation(claim.source_sentence)

    if not extracted:
        # Ambiguous or unsupported mathematical claim: return empty operations list without guessing
        return MathResult(claim_id=claim.id, operations=[], has_math_error=False)

    op_type, expression_str, claimed_str = extracted

    # Execute deterministic calculation
    try:
        calculated_dec = evaluate_expression(expression_str)
    except SafeDivisionByZeroError:
        op = MathOperation(
            op_type=op_type,
            expression_detected=expression_str,
            claimed_value=claimed_str,
            calculated_value="UNDEFINED",
            is_correct=False,
            explanation="Calculation is mathematically undefined (division by zero); cannot verify claimed value.",
        )
        # Undefined calculation is not marked as a verified math error
        return MathResult(claim_id=claim.id, operations=[op], has_math_error=False)
    except SafeMathError as e:
        op = MathOperation(
            op_type=op_type,
            expression_detected=expression_str,
            claimed_value=claimed_str,
            calculated_value="ERROR",
            is_correct=False,
            explanation=f"Calculation error: {e}",
        )
        return MathResult(claim_id=claim.id, operations=[op], has_math_error=True)

    # Adaptive Precision Rounding (ROUND_HALF_UP)
    try:
        claimed_clean = claimed_str.strip()
        if "." in claimed_clean:
            places = len(claimed_clean.split(".")[1])
            quantizer = Decimal("1." + "0" * places)
        else:
            places = 0
            quantizer = Decimal("1")

        rounded_calc = calculated_dec.quantize(quantizer, rounding=ROUND_HALF_UP)
        claimed_dec = Decimal(claimed_clean)
        is_correct = (rounded_calc == claimed_dec)
    except (InvalidOperation, ValueError):
        op = MathOperation(
            op_type=op_type,
            expression_detected=expression_str,
            claimed_value=claimed_str,
            calculated_value=str(calculated_dec),
            is_correct=False,
            explanation=f"Invalid claimed numeric format: '{claimed_str}'",
        )
        return MathResult(claim_id=claim.id, operations=[op], has_math_error=True)

    if is_correct:
        explanation = f"Correct: calculated value {rounded_calc} matches claimed value {claimed_clean}."
        has_error = False
    else:
        explanation = (
            f"Incorrect: claimed {claimed_clean}, but deterministic calculation yields {calculated_dec} "
            f"(rounded: {rounded_calc})."
        )
        has_error = True

    op = MathOperation(
        op_type=op_type,
        expression_detected=expression_str,
        claimed_value=claimed_str,
        calculated_value=str(rounded_calc),
        is_correct=is_correct,
        explanation=explanation,
    )

    return MathResult(
        claim_id=claim.id,
        operations=[op],
        has_math_error=has_error,
    )


def audit_claims_math(claims: list[Claim]) -> list[MathResult]:
    """Audits multiple claims for mathematical operations."""
    return [audit_claim_math(c) for c in claims]


def audit_math_statement(text: str, claim_id: str = "math_claim_1") -> MathResult:
    """Convenience helper for auditing a raw statement string directly."""
    temp_claim = Claim(
        id=claim_id,
        claim_text=text,
        claim_type=ClaimType.MATHEMATICAL,
        source_sentence=text,
    )
    return audit_claim_math(temp_claim)
