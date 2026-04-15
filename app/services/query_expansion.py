"""
Query expansion — appends Dutch workforce/public-sector acronyms with
their spelled-out forms before retrieval.

Why: the dutch tsvector config used by hybrid_search_chunks (BM25 leg)
does not know abbreviations like ZSM, SPO, or DBV. A user query
"ZSM OM capaciteit" gets a near-zero BM25 score against chunks that
spell out "Zo Snel Mogelijk". Expansion fixes that without touching
the tsvector column or reindexing the knowledge base.

Dense (Voyage) embeddings handle synonyms reasonably well, so we only
append the expansion — we do NOT replace the original term. Both forms
in the query means both forms get matched.

Scope: kept deliberately tight to domain jargon. We do not expand
common Dutch words or international tech acronyms (AI, API, KPI, FTE,
ROI, HR, CHRO) — those already embed well and wouldn't gain from
literal expansion.
"""

import re
import structlog

logger = structlog.get_logger()


# Domain-specific acronyms used by ModellenWerk / nlmtd clients.
# Keys must be UPPERCASE; matching is case-insensitive on whole-word boundary.
ACRONYM_DICT: dict[str, str] = {
    # Openbaar Ministerie / justitie
    "ZSM": "Zo Snel Mogelijk strafrechtketen",
    "OM": "Openbaar Ministerie",
    "DBV": "Dienst Bewaken en Beveiligen",
    "AP": "Arrondissementsparket",
    # Strategische personeels(planning/ontwikkeling)
    "SPO": "Strategische Personeelsontwikkeling",
    "SPP": "Strategische Personeelsplanning",
    "SWD": "Strategic Workforce Development",
    # Hoger onderwijs
    "HvA": "Hogeschool van Amsterdam",
    # Zorg — conservatief, alleen wat niet generiek al werkt
    "UMC": "Universitair Medisch Centrum",
    "ZMC": "Zaans Medisch Centrum",
    # Politie / veiligheid
    "NP": "Nationale Politie",
    # Ministeries
    "MinJV": "Ministerie van Justitie en Veiligheid",
    "MinOCW": "Ministerie van Onderwijs Cultuur en Wetenschap",
    "MinVWS": "Ministerie van Volksgezondheid Welzijn en Sport",
    # Toezicht / uitvoering
    "UWV": "Uitvoeringsinstituut Werknemersverzekeringen",
    "CBS": "Centraal Bureau voor de Statistiek",
}


def expand_query(query: str) -> str:
    """
    Return the query with known acronyms appended as spelled-out forms.

    Behavior:
    - Matches acronyms on word boundaries, case-insensitive.
    - APPENDS expansions to the query; never replaces original text.
    - Deduplicates: each acronym expanded once per query, even if it
      appears multiple times.
    - Returns the original string unchanged if no acronyms match.

    Example:
        >>> expand_query("ZSM OM capaciteit")
        'ZSM OM capaciteit (Zo Snel Mogelijk strafrechtketen) (Openbaar Ministerie)'
    """
    if not query:
        return query

    expansions: list[str] = []
    seen: set[str] = set()

    for acronym, spelled_out in ACRONYM_DICT.items():
        if acronym in seen:
            continue
        # Whole-word, case-insensitive match (avoids matching "OM" inside "komma")
        pattern = re.compile(rf"\b{re.escape(acronym)}\b", flags=re.IGNORECASE)
        if pattern.search(query):
            expansions.append(f"({spelled_out})")
            seen.add(acronym)

    if not expansions:
        return query

    expanded = f"{query} {' '.join(expansions)}"
    logger.debug(
        "query_expanded",
        original=query[:120],
        expansions=list(seen),
        expanded_len=len(expanded),
    )
    return expanded
