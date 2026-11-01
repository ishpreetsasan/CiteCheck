
"""
app.py
------
CiteCheck Streamlit Frontend.

Features:
- AI Answer vs. CiteCheck Audit comparison
- Factual verification evidence
- Mathematical audit evidence
- Decision explanation
- Claim-level traceability
- Verification summary
- JSON report download
- Interactive deterministic math evaluator
"""

import html
import re
import streamlit as st

# =========================================================
# BACKEND IMPORTS
# =========================================================

try:
    from citecheck.core.engine import audit_answer
    AUDIT_ANSWER_AVAILABLE = True
except (ImportError, ModuleNotFoundError, AttributeError):
    try:
        from citecheck import audit_answer
        AUDIT_ANSWER_AVAILABLE = True
    except (ImportError, ModuleNotFoundError, AttributeError):
        audit_answer = None
        AUDIT_ANSWER_AVAILABLE = False

from citecheck.utils.safe_math import (
    evaluate_expression,
    SafeMathError,
    SafeDivisionByZeroError,
    SafeArithmeticError,
    UnsafeExpressionError,
)

from citecheck.models.schemas import Decision, AuditReport


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="CiteCheck — AI Answer Auditing Engine",
    page_icon="🔍",
    layout="wide",
)


# =========================================================
# DASHBOARD STYLING
# =========================================================

st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.2rem;
    }

    .sub-title {
        color: #475569;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }

    .diff-card {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 18px 20px;
        background-color: #ffffff;
        min-height: 130px;
        line-height: 1.6;
        font-size: 1.05rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        overflow-wrap: anywhere;
    }

    .diff-header {
        font-weight: 700;
        font-size: 0.95rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }

    .error-highlight {
        background-color: #fee2e2;
        color: #991b1b;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 700;
        text-decoration: line-through;
        border: 1px solid #fca5a5;
    }

    .correct-highlight {
        background-color: #dcfce7;
        color: #166534;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 700;
        border: 1px solid #86efac;
    }

    .verified-highlight {
        background-color: #ecfdf5;
        color: #065f46;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 700;
        border: 1px solid #a7f3d0;
    }

    .decision-banner-pass {
        background: linear-gradient(135deg, #059669 0%, #10b981 100%);
        color: white;
        padding: 16px 22px;
        border-radius: 10px;
        font-size: 1.25rem;
        font-weight: 800;
        margin-bottom: 1.2rem;
    }

    .decision-banner-revise {
        background: linear-gradient(135deg, #d97706 0%, #f59e0b 100%);
        color: white;
        padding: 16px 22px;
        border-radius: 10px;
        font-size: 1.25rem;
        font-weight: 800;
        margin-bottom: 1.2rem;
    }

    .decision-banner-block {
        background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
        color: white;
        padding: 16px 22px;
        border-radius: 10px;
        font-size: 1.25rem;
        font-weight: 800;
        margin-bottom: 1.2rem;
    }

    .decision-banner-review {
        background: linear-gradient(135deg, #475569 0%, #64748b 100%);
        color: white;
        padding: 16px 22px;
        border-radius: 10px;
        font-size: 1.25rem;
        font-weight: 800;
        margin-bottom: 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# HEADER
# =========================================================

st.markdown(
    '<div class="main-title">🔍 CiteCheck: AI Answer Auditing Engine</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sub-title">Factual claim verification, citation auditing, '
    'deterministic math verification, and conservative correction.</div>',
    unsafe_allow_html=True,
)


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:
    st.header("Backend System Status")

    st.markdown("**Core Modules:**")
    st.markdown("✅ `citecheck.models.schemas` — Active")
    st.markdown("✅ `citecheck.utils.safe_math` — Active")

    if AUDIT_ANSWER_AVAILABLE:
        st.markdown("✅ `citecheck.core.engine` — Connected")
    else:
        st.markdown("⏳ `citecheck.core.engine` — Pending")

    st.markdown("✅ `citecheck.verifiers.math_auditor` — Active")
    st.markdown("✅ `citecheck.verifiers.factual_verifier` — Connected")
    st.markdown("⏳ Citation auditing — Pending")
    st.markdown("⏳ NLP correction — Pending")

    st.divider()

    st.info(
        "**Integrity Guarantee:**\n\n"
        "CiteCheck does not fabricate verification results. "
        "Only results returned by the connected backend are displayed."
    )


# =========================================================
# MAIN INPUT INTERFACE
# =========================================================

st.subheader("1. Input AI Answer for Auditing")

col_left, col_right = st.columns(2)

with col_left:
    original_answer = st.text_area(
        "AI-Generated Answer",
        value="The quarterly distribution is simple: 100 / 4 = 20.",
        height=140,
        placeholder="Paste the AI response here...",
        help="Paste the raw text produced by the AI model.",
    )

with col_right:
    reference_context = st.text_area(
        "Reference Context / Evidence (Optional)",
        height=140,
        placeholder="Paste reference text or documentation here...",
        help="Optional evidence for the audit.",
    )

audit_button = st.button(
    "🚀 Audit Answer",
    type="primary",
    use_container_width=True,
)

st.divider()


# =========================================================
# AUDIT EXECUTION
# =========================================================

if audit_button:

    if not original_answer.strip():
        st.warning("⚠️ Please enter an AI-generated answer to audit.")

    elif AUDIT_ANSWER_AVAILABLE and callable(audit_answer):

        try:
            with st.spinner("Auditing answer across verification engines..."):

                report: AuditReport = audit_answer(
                    original_answer=original_answer,
                    reference_context=reference_context.strip() or None,
                )

            # =====================================================
            # 1. DECISION BANNER
            # =====================================================

            decision_banners = {
                Decision.PASS: (
                    "decision-banner-pass",
                    "🟢 AUDIT DECISION: PASS",
                    "All evaluated claims passed the checks performed.",
                ),
                Decision.REVISE: (
                    "decision-banner-revise",
                    "🟡 AUDIT DECISION: REVISE",
                    "Discrepancies detected; available corrections applied.",
                ),
                Decision.BLOCK: (
                    "decision-banner-block",
                    "🔴 AUDIT DECISION: BLOCK",
                    "Critical contradictions or errors detected.",
                ),
                Decision.NEEDS_HUMAN_REVIEW: (
                    "decision-banner-review",
                    "🟠 AUDIT DECISION: NEEDS HUMAN REVIEW",
                    "Some claims need additional evidence or human oversight.",
                ),
            }

            banner_class, banner_title, banner_desc = decision_banners.get(
                report.decision,
                (
                    "decision-banner-review",
                    f"AUDIT DECISION: {report.decision}",
                    "",
                ),
            )

            st.markdown(
                f"""
                <div class="{banner_class}">
                    <div style="display:flex; justify-content:space-between;
                    align-items:center; flex-wrap:wrap; gap:8px;">
                        <div>{banner_title}</div>
                        <div style="font-size:0.95rem; font-weight:400;">
                            {banner_desc}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # =====================================================
            # 2. ORIGINAL ANSWER VS AUDITED ANSWER
            # =====================================================

            st.subheader("⚖️ AI Answer vs. CiteCheck Verification")

            raw_orig = html.escape(report.original_answer)
            raw_rev = html.escape(report.corrections.corrected_text)

            failed_ops = []
            correct_ops = []

            for math_result in report.math_results:
                for op in math_result.operations:
                    if op.is_correct:
                        correct_ops.append(op)
                    else:
                        failed_ops.append(op)

            highlighted_orig = raw_orig
            highlighted_rev = raw_rev

            # Highlight incorrect values in original answer.
            for op in failed_ops:
                claimed = html.escape(op.claimed_value)

                if claimed:
                    highlighted_orig = re.sub(
                        rf"\b{re.escape(claimed)}\b",
                        f'<span class="error-highlight">{claimed}</span>',
                        highlighted_orig,
                        count=1,
                    )

            # Highlight corrected values in revised answer.
            for op in failed_ops:
                calculated = html.escape(op.calculated_value)

                if calculated and calculated not in ("UNDEFINED", "ERROR"):
                    highlighted_rev = re.sub(
                        rf"\b{re.escape(calculated)}\b",
                        f'<span class="correct-highlight">{calculated}</span>',
                        highlighted_rev,
                        count=1,
                    )

            # Highlight correct mathematical values.
            if not failed_ops and correct_ops:
                for op in correct_ops:
                    claimed = html.escape(op.claimed_value)

                    if claimed:
                        highlighted_orig = re.sub(
                            rf"\b{re.escape(claimed)}\b",
                            f'<span class="verified-highlight">{claimed} ✓</span>',
                            highlighted_orig,
                            count=1,
                        )

                        highlighted_rev = re.sub(
                            rf"\b{re.escape(claimed)}\b",
                            f'<span class="verified-highlight">{claimed} ✓</span>',
                            highlighted_rev,
                            count=1,
                        )

            col_diff_l, col_diff_r = st.columns(2)

            with col_diff_l:
                st.markdown(
                    '<div class="diff-header" style="color:#dc2626;">'
                    'Original AI-Generated Answer</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f'<div class="diff-card">{highlighted_orig}</div>',
                    unsafe_allow_html=True,
                )

            with col_diff_r:

                answer_was_changed = (
                    report.corrections.corrected_text
                    != report.original_answer
                )

                if answer_was_changed:
                    right_heading = "CiteCheck Corrected Answer"
                    right_color = "#16a34a"

                elif report.decision == Decision.PASS:
                    right_heading = (
                        "CiteCheck Audited Answer — No Correction Needed"
                    )
                    right_color = "#16a34a"

                else:
                    right_heading = (
                        "Original Answer — Unchanged, Not Fully Verified"
                    )
                    right_color = "#d97706"

                st.markdown(
                    f'<div class="diff-header" style="color:{right_color};">'
                    f'{right_heading}</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(
                    f'<div class="diff-card">{highlighted_rev}</div>',
                    unsafe_allow_html=True,
                )

            # =====================================================
            # 3. FACTUAL VERIFICATION EVIDENCE
            # =====================================================

            if report.factual_results:

                st.divider()
                st.markdown("### 📚 Factual Verification Evidence")

                for result in report.factual_results:

                    st.markdown(f"**Claim ID:** `{result.claim_id}`")
                    st.markdown(
                        f"**Verification Status:** `{result.status.value}`"
                    )

                    st.write(result.rationale)

                    if result.evidence:
                        st.markdown(
                            "**Evidence Source:** "
                            f"{result.evidence.source_uri_or_name}"
                        )

                        st.write(
                            result.evidence.extracted_snippet
                        )

                    st.divider()

            # =====================================================
            # 4. EVIDENCE EXPLORER
            # =====================================================

            st.divider()

            st.markdown(
                "### 🔎 Evidence Explorer — Inspect Why CiteCheck Decided"
            )

            st.caption(
                "Inspect detected expressions, independent calculations, "
                "claimed vs. calculated values, and decision rationale."
            )

            all_ops = [
                op
                for math_result in report.math_results
                for op in math_result.operations
            ]

            (
                tab_evidence,
                tab_decision,
                tab_claims,
                tab_summary,
            ) = st.tabs(
                [
                    "🧮 Mathematical Audit Evidence",
                    "🎯 Why This Decision?",
                    "📋 Claim-Level Traceability",
                    "📊 Verification Summary Table",
                ]
            )

            # =====================================================
            # TAB A: MATHEMATICAL EVIDENCE
            # =====================================================

            with tab_evidence:

                if all_ops:

                    st.markdown(
                        "#### Detected Mathematical Operations "
                        "& Independent Calculations"
                    )

                    st.info(
                        "**Calculation Engine:** Python AST parsing "
                        "+ Decimal arithmetic. No eval() and no "
                        "LLM-based calculation."
                    )

                    for idx, op in enumerate(all_ops, start=1):

                        match_status = (
                            "✅ MATCH"
                            if op.is_correct
                            else "❌ MISMATCH"
                        )

                        badge_title = (
                            f"{match_status} — Step {idx}: "
                            f"[{op.op_type.value}] "
                            f"{op.expression_detected}"
                        )

                        with st.expander(badge_title, expanded=True):

                            col_exp1, col_exp2 = st.columns(2)

                            with col_exp1:
                                st.markdown(
                                    "**A. Detected Mathematical Expression**"
                                )

                                st.code(
                                    op.expression_detected,
                                    language="python",
                                )

                                st.caption(
                                    f"Operation Type: `{op.op_type.value}`"
                                )

                            with col_exp2:
                                st.markdown(
                                    "**B. Independent Calculation Engine**"
                                )

                                st.markdown(
                                    f"- **Evaluated Value:** "
                                    f"`{op.calculated_value}`"
                                )

                                st.markdown(
                                    "- **Methodology:** Safe AST + Decimal"
                                )

                                if op.is_correct:
                                    st.success(op.explanation)
                                else:
                                    st.error(op.explanation)

                            st.markdown(
                                "**C. Claimed vs. Calculated Value**"
                            )

                            c1, c2, c3 = st.columns(3)

                            c1.metric(
                                "Original Claimed Value",
                                op.claimed_value,
                            )

                            c2.metric(
                                "Independently Calculated",
                                op.calculated_value,
                            )

                            c3.metric(
                                "Values Match?",
                                "YES" if op.is_correct else "NO",
                                delta=(
                                    None
                                    if op.is_correct
                                    else "Correction Applied"
                                ),
                                delta_color="inverse",
                            )

                else:
                    st.info(
                        "No parseable mathematical operations "
                        "were detected in this answer."
                    )

            # =====================================================
            # TAB B: DECISION EXPLANATION
            # =====================================================

            with tab_decision:

                st.markdown(
                    f"#### Audit Verdict: `{report.decision.value}`"
                )

                if report.decision_reasons:

                    st.markdown("**Reported Decision Reasons:**")

                    for reason in report.decision_reasons:
                        st.markdown(f"- 📌 {reason}")

                st.divider()

                if report.decision == Decision.PASS:

                    st.success(
                        "All claims passed the checks performed by "
                        "the currently implemented verification engines."
                    )

                elif report.decision == Decision.REVISE:

                    st.warning(
                        "CiteCheck detected discrepancies and applied "
                        "available conservative corrections."
                    )

                elif report.decision == Decision.NEEDS_HUMAN_REVIEW:

                    st.info(
                        "At least one claim needs additional evidence "
                        "or human review. The answer has not been "
                        "fully verified."
                    )

                elif report.decision == Decision.BLOCK:

                    st.error(
                        "CiteCheck detected a critical contradiction "
                        "or error."
                    )

            # =====================================================
            # TAB C: CLAIM-LEVEL TRACEABILITY
            # =====================================================

            with tab_claims:

                st.markdown("#### Atomic Claims Audit Trace")

                st.caption(
                    "Inspect each decomposed claim and its "
                    "available verification evidence."
                )

                if report.claims:

                    for claim in report.claims:

                        claim_math = next(
                            (
                                mr
                                for mr in report.math_results
                                if mr.claim_id == claim.id
                            ),
                            None,
                        )

                        has_math_op = (
                            claim_math is not None
                            and len(claim_math.operations) > 0
                        )

                        if claim_math and claim_math.has_math_error:
                            claim_status = "⚠️ Math Error"

                        elif has_math_op:
                            claim_status = "✅ Math Audited"

                        else:
                            claim_status = "ℹ️ Factual / Other Review"

                        with st.expander(
                            f"Claim [{claim.id}]: "
                            f"{claim.claim_text[:75]} "
                            f"({claim_status})"
                        ):

                            st.markdown(
                                f"- **Claim ID:** `{claim.id}`"
                            )

                            st.markdown(
                                f"- **Full Claim:** {claim.claim_text}"
                            )

                            st.markdown(
                                f"- **Classified Type:** "
                                f"`{claim.claim_type.value}`"
                            )

                            if has_math_op:

                                st.markdown("**Math Evidence:**")

                                for op in claim_math.operations:

                                    st.write(
                                        f"Expression: {op.expression_detected} | "
                                        f"Claimed: {op.claimed_value} | "
                                        f"Calculated: {op.calculated_value} | "
                                        f"Match: "
                                        f"{'Yes' if op.is_correct else 'No'}"
                                    )

                            factual_result = next(
                                (
                                    fr
                                    for fr in report.factual_results
                                    if fr.claim_id == claim.id
                                ),
                                None,
                            )

                            if factual_result:

                                st.markdown(
                                    f"**Factual Status:** "
                                    f"`{factual_result.status.value}`"
                                )

                                st.write(factual_result.rationale)

                                if factual_result.evidence:

                                    st.markdown(
                                        "**Evidence Source:** "
                                        f"{factual_result.evidence.source_uri_or_name}"
                                    )

                                    st.write(
                                        factual_result.evidence.extracted_snippet
                                    )

                            elif not has_math_op:

                                st.caption(
                                    "No associated factual verification "
                                    "result is available for this claim."
                                )

                else:
                    st.info("No atomic claims were extracted.")

            # =====================================================
            # TAB D: VERIFICATION SUMMARY TABLE
            # =====================================================

            with tab_summary:

                if all_ops:

                    summary_rows = []

                    for op in all_ops:

                        if op.is_correct:
                            error_label = "None"
                            correction_label = "Preserved"
                            status_badge = "✅ Match"

                        else:
                            error_label = (
                                f"Claimed {op.claimed_value} vs. "
                                f"Calculated {op.calculated_value}"
                            )

                            correction_label = (
                                f"Replaced with {op.calculated_value}"
                            )

                            status_badge = "❌ Mismatch"

                        summary_rows.append(
                            {
                                "Operation Type": op.op_type.value,
                                "Claimed Value": op.claimed_value,
                                "Calculated Value": op.calculated_value,
                                "Error": error_label,
                                "Correction": correction_label,
                                "Status": status_badge,
                            }
                        )

                    st.dataframe(
                        summary_rows,
                        use_container_width=True,
                        hide_index=True,
                    )

                else:
                    st.info(
                        "No mathematical operations to summarize."
                    )

            # =====================================================
            # 5. AGGREGATE METRICS
            # =====================================================

            st.divider()

            st.markdown("#### 📈 Aggregate Audit Metrics")

            summary = report.summary

            m1, m2, m3, m4, m5 = st.columns(5)

            m1.metric("Total Claims", summary.total_claims)
            m2.metric("Supported", summary.supported_claims)

            m3.metric(
                "Partially Supported",
                summary.partially_supported_claims,
            )

            m4.metric("Math Errors", summary.math_errors)
            m5.metric("Citation Issues", summary.citation_issues)

            # =====================================================
            # 6. JSON REPORT DOWNLOAD
            # =====================================================

            report_json = report.model_dump_json(indent=2)

            st.download_button(
                label="💾 Download Audit Report (JSON)",
                data=report_json,
                file_name="citecheck_audit_report.json",
                mime="application/json",
            )

        except Exception as e:
            st.error(f"❌ Backend execution error: {e}")

    else:

        st.info(
            "The central audit_answer() backend is not connected. "
            "Please check the backend installation."
        )


# =========================================================
# INTERACTIVE SAFE MATH EVALUATOR
# =========================================================

st.divider()

st.subheader("🧮 Deterministic Math Evaluator")

st.caption(
    "Test the active safe_math.evaluate_expression() engine "
    "using AST parsing and Decimal arithmetic."
)

math_col1, math_col2 = st.columns([2, 1])

with math_col1:

    expression_input = st.text_input(
        "Arithmetic Expression to Evaluate",
        value="(100 - (100 * 0.20)) / 2",
        placeholder="e.g., (100 * 0.15) + 25.50",
    )

with math_col2:

    st.write("")
    st.write("")

    evaluate_button = st.button(
        "Calculate via Backend Decimal",
        use_container_width=True,
    )

if evaluate_button and expression_input.strip():

    try:

        result = evaluate_expression(expression_input)

        st.success(
            f"**Deterministic Result (Decimal):** `{result}`"
        )

    except SafeDivisionByZeroError as e:
        st.error(f"❌ SafeDivisionByZeroError: {e}")

    except SafeArithmeticError as e:
        st.error(f"❌ SafeArithmeticError: {e}")

    except UnsafeExpressionError as e:
        st.warning(f"⚠️ UnsafeExpressionError: {e}")

    except SafeMathError as e:
        st.error(f"❌ SafeMathError: {e}")

    except Exception as e:
        st.error(f"❌ Unexpected Error: {e}")
