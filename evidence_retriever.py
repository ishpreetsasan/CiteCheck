
"""
CiteCheck Multi-Source Evidence Retriever.

Retrieves candidate evidence from multiple providers.
Search results are NOT proof that a claim is true.
"""

import re
from typing import Any

import requests




def prepare_wikidata_query(query: str) -> str:
    """Extract the main subject from common factual questions."""

    if not isinstance(query, str):
        return ""

    cleaned = query.strip().rstrip("?.! ")
    lowered = cleaned.lower()

    prefixes = [
        "who discovered ",
        "who developed ",
        "who invented ",
        "who created ",
        "who wrote ",
        "what is ",
        "where is ",
        "when was ",
        "when did ",
        "tell me about ",
    ]

    for prefix in prefixes:
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    cleaned = cleaned.strip()

    # Remove descriptive words that are not part of the subject.
    descriptors = [
        "the novel ",
        "novel ",
        "the book ",
        "book ",
        "the programming language ",
    ]

    for descriptor in descriptors:
        if cleaned.lower().startswith(descriptor):
            cleaned = cleaned[len(descriptor):]
            break

    suffixes = [
        " built",
        " discovered",
        " developed",
        " invented",
        " created",
        " written",
    ]

    for suffix in suffixes:
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break

    if cleaned.lower().startswith("the "):
        cleaned = cleaned[4:]

    return cleaned.strip()


def detect_expected_entity_type(query: str) -> str:
    """Identify the expected entity category from question wording."""

    lowered = query.lower().strip()

    if lowered.startswith("who wrote "):
        return "written_work"

    if lowered.startswith("who developed "):
        if "python" in lowered:
            return "software"
        return "product_or_technology"

    if lowered.startswith("who discovered "):
        return "discovery"

    if lowered.startswith("when was ") or lowered.startswith("where is "):
        return "place_or_structure"

    return "unknown"


def matches_expected_entity_type(
    expected_type: str,
    actual_types: list[str]
) -> bool:
    """Check whether Wikidata types match the expected entity category."""

    if expected_type == "unknown":
        return True

    normalized_types = {
        item.lower() for item in actual_types
    }

    type_keywords = {
        "written_work": {
            "literary work",
            "written work",
            "novel",
            "book",
        },
        "software": {
            "programming language",
            "software",
            "computer program",
        },
        "discovery": {
            "discovery",
            "scientific discovery",
        },
        "place_or_structure": {
            "tower",
            "building",
            "structure",
            "architectural structure",
        },
        "product_or_technology": {
            "technology",
            "software",
            "product",
        },
    }

    accepted_types = type_keywords.get(expected_type, set())

    return any(
        actual_type in accepted_types
        for actual_type in normalized_types
    )




HEADERS = {
    "User-Agent": "CiteCheck/1.0 (student hackathon project)"
}
TIMEOUT = 15

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
CROSSREF_API = "https://api.crossref.org/works"
OPENALEX_API = "https://api.openalex.org/works"



def _tokens(text: str) -> set[str]:
    """Extract meaningful terms for basic evidence matching."""
    stopwords = {
        "the", "and", "for", "was", "were", "who",
        "what", "when", "where", "how", "is", "are",
        "does", "did", "with", "from", "that", "this",
        "novel", "wrote", "write", "written",
        "tell", "me", "about", "please",
    }

    return {
        word.lower()
        for word in re.findall(r"\b[a-zA-Z0-9]+\b", text)
        if len(word) >= 2 and word.lower() not in stopwords
    }



def _relevance_score(query: str, result: dict[str, Any]) -> float:
    """
    Estimate relevance using the main subject of the question.
    This is NOT a factual confidence score.
    """

    subject_query = prepare_wikidata_query(query)
    subject_words = _tokens(subject_query)

    if not subject_words:
        subject_words = _tokens(query)

    if not subject_words:
        return 0.0

    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()

    title_words = _tokens(title)
    snippet_words = _tokens(snippet)

    title_matches = len(subject_words & title_words)
    snippet_matches = len(subject_words & snippet_words)

    title_score = title_matches / len(subject_words)
    snippet_score = snippet_matches / len(subject_words)

    score = (0.8 * title_score) + (0.2 * snippet_score)

    normalized_subject = " ".join(
        re.findall(r"[a-zA-Z0-9]+", subject_query.lower())
    )

    normalized_title = " ".join(
        re.findall(r"[a-zA-Z0-9]+", title)
    )

    if normalized_subject and normalized_subject in normalized_title:
        score = max(score, 0.95)

    return round(min(score, 1.0), 3)




def _request_json(url: str, params: dict) -> dict:
    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def search_wikipedia(query: str, limit: int = 3) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        return []

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query.strip(),
        "gsrlimit": max(1, min(limit, 5)),
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "exchars": 1200,
        "format": "json",
    }

    try:
        data = _request_json(WIKIPEDIA_API, params)
        pages = data.get("query", {}).get("pages", {})
        results = []

        for page in pages.values():
            title = page.get("title", "")
            snippet = page.get("extract", "")

            if title and snippet:
                results.append({
                    "source": "Wikipedia",
                    "title": title,
                    "url": "https://en.wikipedia.org/wiki/" +
                           requests.utils.quote(title.replace(" ", "_")),
                    "snippet": snippet,
                })

        return results

    except (requests.RequestException, ValueError):
        return []



def search_wikidata(query: str, limit: int = 3) -> list[dict]:
    """Search Wikidata for relevant entities."""

    if not isinstance(query, str) or not query.strip():
        return []

    params = {
        "action": "wbsearchentities",
        "search": query.strip(),
        "language": "en",
        "limit": max(1, min(limit, 5)),
        "format": "json",
    }

    try:
        data = _request_json(WIKIDATA_API, params)
        results = []

        for item in data.get("search", []):
            entity_id = item.get("id")
            title = item.get("label", "")

            if entity_id and title:
                results.append({
                    "source": "Wikidata",
                    "title": title,
                    "url": f"https://www.wikidata.org/entity/{entity_id}",
                    "entity_id": entity_id,
                    "snippet": item.get("description", ""),
                })

        return results

    except (requests.RequestException, ValueError):
        return []

    params = {
        "action": "wbsearchentities",
        "search": query.strip(),
        "language": "en",
        "limit": max(1, min(limit, 5)),
        "format": "json",
    }

    try:
        data = _request_json(WIKIDATA_API, params)
        results = []

        for item in data.get("search", []):
            label = item.get("label", "")
            description = item.get("description", "")

            if label:
                results.append({
    "source": "Wikidata",
    "title": label,
    "url": item.get("concepturi", ""),
    "entity_id": item.get("id", ""),
    "snippet": description,
})

        return results

    except (requests.RequestException, ValueError):
        return []



def get_wikidata_entity(entity_id: str) -> dict:
    """Retrieve structured entity information from Wikidata."""

    if not isinstance(entity_id, str) or not re.fullmatch(r"Q\d+", entity_id):
        return {}

    params = {
        "action": "wbgetentities",
        "ids": entity_id,
        "props": "labels|descriptions|claims",
        "languages": "en",
        "format": "json",
    }

    try:
        data = _request_json(WIKIDATA_API, params)
        entity = data.get("entities", {}).get(entity_id, {})

        if "missing" in entity:
            return {}

        return {
            "entity_id": entity_id,
            "label": entity.get("labels", {}).get("en", {}).get("value", ""),
            "description": entity.get("descriptions", {}).get("en", {}).get("value", ""),
            "claims": entity.get("claims", {}),
        }

    except (requests.RequestException, ValueError):
        return {}



def get_wikidata_authors(entity_id: str) -> list[str]:
    """Extract readable author names from a Wikidata entity."""

    entity = get_wikidata_entity(entity_id)
    author_claims = entity.get("claims", {}).get("P50", [])

    author_ids = []

    for claim in author_claims:
        value = (
            claim.get("mainsnak", {})
            .get("datavalue", {})
            .get("value", {})
        )

        author_id = value.get("id")

        if author_id:
            author_ids.append(author_id)

    if not author_ids:
        return []

    params = {
        "action": "wbgetentities",
        "ids": "|".join(author_ids),
        "props": "labels",
        "languages": "en",
        "format": "json",
    }

    try:
        data = _request_json(WIKIDATA_API, params)

        return [
            data["entities"][author_id]["labels"]["en"]["value"]
            for author_id in author_ids
            if author_id in data.get("entities", {})
            and "en" in data["entities"][author_id].get("labels", {})
        ]

    except (requests.RequestException, ValueError, KeyError):
        return []
    

    params = {
        "action": "wbgetentities",
        "ids": entity_id,
        "props": "labels|descriptions|claims",
        "languages": "en",
        "format": "json",
    }

    try:
        data = _request_json(WIKIDATA_API, params)
        entity = data.get("entities", {}).get(entity_id, {})

        if "missing" in entity:
            return {}

        return {
            "entity_id": entity_id,
            "label": entity.get("labels", {}).get("en", {}).get("value", ""),
            "description": entity.get("descriptions", {}).get("en", {}).get("value", ""),
            "claims": entity.get("claims", {}),
        }

    except (requests.RequestException, ValueError):
        return {}


def get_wikidata_creators(entity_id: str) -> dict[str, list[str]]:
    """Extract readable creator and developer names from Wikidata."""

    entity = get_wikidata_entity(entity_id)
    claims = entity.get("claims", {})

    relationship_properties = {
        "creators": "P170",
        "developers": "P178",
    }

    relationships = {}

    for relationship_name, property_id in relationship_properties.items():
        related_ids = []

        for claim in claims.get(property_id, []):
            value = (
                claim.get("mainsnak", {})
                .get("datavalue", {})
                .get("value", {})
            )

            related_id = value.get("id")

            if related_id:
                related_ids.append(related_id)

        if not related_ids:
            relationships[relationship_name] = []
            continue

        params = {
            "action": "wbgetentities",
            "ids": "|".join(related_ids),
            "props": "labels",
            "languages": "en",
            "format": "json",
        }

        try:
            data = _request_json(WIKIDATA_API, params)

            names = [
                data["entities"][related_id]["labels"]["en"]["value"]
                for related_id in related_ids
                if related_id in data.get("entities", {})
                and "en" in data["entities"][related_id].get("labels", {})
            ]

            relationships[relationship_name] = names

        except (requests.RequestException, ValueError, KeyError):
            relationships[relationship_name] = []

    return relationships


def get_wikidata_types(entity_id: str) -> list[str]:
    """Extract readable instance-of types from a Wikidata entity."""

    entity = get_wikidata_entity(entity_id)
    type_claims = entity.get("claims", {}).get("P31", [])

    type_ids = []

    for claim in type_claims:
        value = (
            claim.get("mainsnak", {})
            .get("datavalue", {})
            .get("value", {})
        )

        type_id = value.get("id")

        if type_id:
            type_ids.append(type_id)

    if not type_ids:
        return []

    params = {
        "action": "wbgetentities",
        "ids": "|".join(type_ids),
        "props": "labels",
        "languages": "en",
        "format": "json",
    }

    try:
        data = _request_json(WIKIDATA_API, params)

        return [
            data["entities"][type_id]["labels"]["en"]["value"]
            for type_id in type_ids
            if type_id in data.get("entities", {})
            and "en" in data["entities"][type_id].get("labels", {})
        ]

    except (requests.RequestException, ValueError, KeyError):
        return []


def get_wikidata_dates(entity_id: str) -> dict[str, list[str]]:
    """Extract date values from selected Wikidata properties."""

    entity = get_wikidata_entity(entity_id)
    claims = entity.get("claims", {})

    date_properties = {
        "inception": "P571",
        "publication_date": "P577",
        "dissolution_date": "P576",
    }

    dates = {}

    for property_name, property_id in date_properties.items():
        values = []

        for claim in claims.get(property_id, []):
            value = (
                claim.get("mainsnak", {})
                .get("datavalue", {})
                .get("value", {})
            )

            date_value = value.get("time")

            if date_value:
                values.append(date_value)

        if values:
            dates[property_name] = values

    return dates


def format_wikidata_date(date_value: str) -> str:
    """Convert a Wikidata timestamp into a readable date."""

    if not isinstance(date_value, str):
        return "Unknown date"

    match = re.match(r"^[+-]?(\d{4})-(\d{2})-(\d{2})", date_value)

    if not match:
        return "Unknown date"

    year, month, day = match.groups()

    if month == "00":
        return year

    if day == "00":
        return f"{year}-{month}"

    return f"{year}-{month}-{day}"





def enrich_wikidata_result(result: dict) -> dict:
    """Add structured information to a Wikidata search result."""

    entity_id = result.get("entity_id")

    if not entity_id:
        return result

    authors = get_wikidata_authors(entity_id)
    creators_and_developers = get_wikidata_creators(entity_id)
    entity_types = get_wikidata_types(entity_id)
    dates = get_wikidata_dates(entity_id)

    readable_dates = {
        property_name: [
            format_wikidata_date(date_value)
            for date_value in date_values
        ]
        for property_name, date_values in dates.items()
    }

    return {
        **result,
        "authors": authors,
        "creators": creators_and_developers["creators"],
        "developers": creators_and_developers["developers"],
        "entity_types": entity_types,
        "dates": dates,
        "readable_dates": readable_dates,
    }






def search_crossref(query: str, limit: int = 3) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        return []

    params = {
        "query.bibliographic": query.strip(),
        "rows": max(1, min(limit, 5)),
    }

    try:
        data = _request_json(CROSSREF_API, params)
        items = data.get("message", {}).get("items", [])
        results = []

        for item in items:
            titles = item.get("title", [])
            title = titles[0] if titles else ""

            if title:
                results.append({
                    "source": "Crossref",
                    "title": title,
                    "url": item.get("URL", ""),
                    "snippet": (
                        "Publisher: " +
                        item.get("publisher", "Unknown")
                    ),
                })

        return results

    except (requests.RequestException, ValueError):
        return []


def search_openalex(query: str, limit: int = 3) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        return []

    params = {
        "search": query.strip(),
        "per-page": max(1, min(limit, 5)),
    }

    try:
        data = _request_json(OPENALEX_API, params)
        results = []

        for item in data.get("results", []):
            title = item.get("title", "")

            if title:
                results.append({
                    "source": "OpenAlex",
                    "title": title,
                    "url": item.get("doi") or item.get("id", ""),
                    "snippet": (
                        "Scholarly work. "
                        f"Publication year: {item.get('publication_year', 'Unknown')}"
                    ),
                })

        return results

    except (requests.RequestException, ValueError):
        return []






def retrieve_evidence(query: str) -> list[dict[str, Any]]:
    """Retrieve, enrich, and rank evidence from configured providers."""

    if not isinstance(query, str) or not query.strip():
        return []

    results = []
    expected_type = detect_expected_entity_type(query)

    providers = [
        search_wikipedia,
        search_wikidata,
        search_crossref,
        search_openalex,
    ]

    for provider in providers:
        search_query = (
            prepare_wikidata_query(query)
            if provider == search_wikidata
            else query.strip()
        )

        provider_results = provider(search_query)

        if provider == search_wikidata:
            enriched_results = []

            for result in provider_results:
                result = enrich_wikidata_result(result)

                actual_types = result.get("entity_types", [])

                result["expected_entity_type"] = expected_type

                result["entity_type_match"] = (
                    matches_expected_entity_type(
                        expected_type,
                        actual_types
                    )
                    if actual_types
                    else None
                )

                result["search_query"] = search_query
                enriched_results.append(result)

            provider_results = enriched_results

        for result in provider_results:
            result["relevance_score"] = _relevance_score(query, result)
            results.append(result)

        source_priority = {
        "Wikipedia": 0,
        "Wikidata": 1,
        "Crossref": 2,
        "OpenAlex": 3,
    }

    def entity_type_priority(item: dict[str, Any]) -> int:
        match = item.get("entity_type_match")

        if match is True:
            return 0
        if match is False:
            return 2

        # Unknown type information is neutral, not a mismatch.
        return 1

    results.sort(
        key=lambda item: (
            entity_type_priority(item),
            -item["relevance_score"],
            source_priority.get(item["source"], 99),
        )
    )

    return results



