
import re

from citecheck.models.schemas import (
    EvidenceItem,
    FactualResult,
    FactualStatus,
)
from citecheck.verifiers.evidence_retriever import retrieve_evidence


def _normalize_name(name: str) -> str:
    """Normalize names for case-insensitive comparison."""
    return re.sub(r"\s+", " ", name.strip()).casefold()


def verify_author_claim(
    claim_id: str,
    query: str,
    claimed_author: str,
) -> FactualResult:
    """
    Verify an author claim using structured Wikidata author data.

    A matching author supports the claim.
    Missing or incomplete data produces insufficient evidence.
    """

    if not all(
        isinstance(value, str) and value.strip()
        for value in (claim_id, query, claimed_author)
    ):
        return FactualResult(
            claim_id=claim_id or "unknown",
            status=FactualStatus.INSUFFICIENT_EVIDENCE,
            evidence=None,
            rationale="Claim information is missing or invalid.",
        )

    results = retrieve_evidence(query)

    for result in results:
        if result.get("source") != "Wikidata":
            continue

        if result.get("entity_type_match") is not True:
            continue

        authors = result.get("authors", [])

        if not authors:
            continue

        source_url = result.get("url", "")
        title = result.get("title", "Unknown work")

        for author in authors:
            if _normalize_name(author) == _normalize_name(claimed_author):
                return FactualResult(
                    claim_id=claim_id,
                    status=FactualStatus.SUPPORTED,
                    evidence=EvidenceItem(
                        source_uri_or_name=source_url,
                        extracted_snippet=(
                            f"Wikidata lists {author} as an author "
                            f"of {title}."
                        ),
                        is_sufficient=True,
                        notes="Structured author-property match.",
                    ),
                    rationale=(
                        f"The retrieved Wikidata author information "
                        f"matches the claimed author: {author}."
                    ),
                )

    return FactualResult(
        claim_id=claim_id,
        status=FactualStatus.INSUFFICIENT_EVIDENCE,
        evidence=None,
        rationale=(
            "No matching author relationship was found in the "
            "retrieved structured evidence. This does not prove "
            "that the claim is false."
        ),
    )

def verify_developer_claim(
    claim_id: str,
    query: str,
    claimed_developer: str,
) -> FactualResult:
    """Verify a software developer claim using structured Wikidata data."""

    if not all(
        isinstance(value, str) and value.strip()
        for value in (claim_id, query, claimed_developer)
    ):
        return FactualResult(
            claim_id=claim_id or "unknown",
            status=FactualStatus.INSUFFICIENT_EVIDENCE,
            evidence=None,
            rationale="Claim information is missing or invalid.",
        )

    results = retrieve_evidence(query)

    for result in results:
        if result.get("source") != "Wikidata":
            continue

        if result.get("entity_type_match") is not True:
            continue

        developers = result.get("developers", [])

        if not developers:
            continue

        for developer in developers:
            if _normalize_name(developer) == _normalize_name(
                claimed_developer
            ):
                return FactualResult(
                    claim_id=claim_id,
                    status=FactualStatus.SUPPORTED,
                    evidence=EvidenceItem(
                        source_uri_or_name=result.get("url", ""),
                        extracted_snippet=(
                            f"Wikidata lists {developer} as a developer "
                            f"of {result.get('title', 'the software')}."
                        ),
                        is_sufficient=True,
                        notes="Structured developer-property match.",
                    ),
                    rationale=(
                        f"The retrieved Wikidata developer information "
                        f"matches: {developer}."
                    ),
                )

    return FactualResult(
        claim_id=claim_id,
        status=FactualStatus.INSUFFICIENT_EVIDENCE,
        evidence=None,
        rationale=(
            "No matching developer relationship was found in the "
            "retrieved structured evidence. This does not prove "
            "that the claim is false."
        ),
    )
