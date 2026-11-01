"""
tests/test_math_auditing_e2e.py
-------------------------------
End-to-end verification of deterministic mathematical auditing.
"""

from citecheck import audit_answer
from citecheck.models.schemas import Decision, MathOpType
from citecheck.verifiers.math_auditor import audit_math_statement


def test_explicit_equation_correct():
    report = audit_answer("12.5 + 7.5 = 20")
    assert report.decision == Decision.PASS
    assert report.summary.math_errors == 0
    assert len(report.math_results) == 1
    op = report.math_results[0].operations[0]
    assert op.is_correct is True
    assert op.expression_detected == "12.5 + 7.5"
    assert op.calculated_value == "20"


def test_explicit_equation_incorrect():
    report = audit_answer("100 / 4 = 20")
    assert report.decision == Decision.REVISE
    assert report.summary.math_errors == 1
    assert len(report.math_results) == 1
    op = report.math_results[0].operations[0]
    assert op.is_correct is False
    assert op.calculated_value == "25"
    assert op.claimed_value == "20"
    # Ensure conservative correction updated the sentence without inventing facts
    assert "25" in report.corrections.corrected_text
    assert report.corrections.total_modifications == 1


def test_discount_correct():
    report = audit_answer("A 20% discount on 100 is 80")
    assert report.decision == Decision.PASS
    assert report.summary.math_errors == 0
    assert len(report.math_results) == 1
    op = report.math_results[0].operations[0]
    assert op.op_type == MathOpType.DISCOUNT
    assert op.is_correct is True
    assert op.calculated_value == "80"


def test_ambiguous_math_statement():
    report = audit_answer("The company saw exponential growth in numbers last quarter.")
    assert report.decision == Decision.NEEDS_HUMAN_REVIEW
    assert report.summary.math_errors == 0
    # Operations list must be empty for ambiguous text: no fabricated operations
    assert len(report.math_results) == 0


def test_division_by_zero_not_flagged_as_verified_error():
    result = audit_math_statement("Increased from 0 to 50, a 100% increase")
    # Should catch division by zero without raising an uncaught exception
    assert result.has_math_error is False
    if result.operations:
        assert result.operations[0].calculated_value == "UNDEFINED"
        assert result.operations[0].is_correct is False
