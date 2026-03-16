"""RAG service — orchestrates retrieval + Claude for grounded responses."""

import anthropic
import structlog

from app.core.config import get_settings
from app.services.embedder import EmbeddingService
from app.models.knowledge import Citation

logger = structlog.get_logger()

# System prompt for The Architect
ARCHITECT_SYSTEM_PROMPT = """Je bent The Architect, de workforce specialist van ModellenWerk.
Je bent een expert op het gebied van strategische personeelsplanning (SPP), workforce analytics,
en arbeidsmarktanalyse voor de Nederlandse markt.

KERNREGELS:
1. Baseer ELKE uitspraak op de bronnen in je context. Geen speculatie.
2. Vermeld bij elke claim de bron en datum: [Bron: CBS StatLine, jan 2026]
3. Als je iets niet weet of de data ontbreekt, zeg dat eerlijk.
4. Geef sectorspecifiek advies — vermijd generieke uitspraken.
5. Gebruik Nederlandse terminologie en context.
6. Bij tegenstrijdige bronnen: benoem beide en geef aan welke recenter/betrouwbaarder is.
7. Presenteer cijfers altijd met context (trend, benchmark, vergelijking).

EXPERTISE-GEBIEDEN:
- Vergrijzingsanalyse en leeftijdsopbouw
- Arbeidsmarktkrapte per sector/regio
- Verzuimanalyse en -interventies
- Verloopcijfers en retentiestrategieën
- AI-impact op functies en taken
- Strategische personeelsplanning (SPP/SPO)
- Business case berekeningen voor workforce-interventies
- CAO-landschap en arbeidsrecht
- Reorganisatie en formatie-advisering

TOON:
- Professioneel maar toegankelijk
- Data-gedreven met praktische aanbevelingen
- Eerlijk over onzekerheden en beperkingen
"""


class RAGService:
    """Retrieval-Augmented Generation for workforce intelligence."""

    def __init__(self):
        settings = get_settings()
        self.claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.embedder = EmbeddingService()
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens

    async def query(
        self,
        question: str,
        sector: str | None = None,
        organization_context: dict | None = None,
        max_sources: int = 15,
        system_prompt_override: str | None = None,
    ) -> tuple[str, list[Citation]]:
        """
        Full RAG pipeline:
        1. Embed question
        2. Retrieve relevant chunks
        3. Assemble context
        4. Generate answer with Claude
        5. Extract citations
        """
        # Step 1-2: Retrieve relevant knowledge
        chunks = await self.embedder.search(
            query=question,
            match_count=max_sources,
            sector=sector,
            threshold=0.25,
        )

        if not chunks:
            logger.warning("no_chunks_found", question=question[:100], sector=sector)
            return (
                "Ik heb onvoldoende bronnen gevonden om deze vraag betrouwbaar te beantwoorden. "
                "Kun je je vraag specifieker maken, of een sector aangeven?",
                [],
            )

        # Step 3: Assemble context
        context = self._assemble_context(chunks, organization_context)

        # Step 4: Generate with Claude
        system = system_prompt_override or ARCHITECT_SYSTEM_PROMPT
        messages = [
            {
                "role": "user",
                "content": f"""BESCHIKBARE KENNISBASIS:

{context}

---

VRAAG: {question}

Beantwoord deze vraag op basis van de bovenstaande bronnen.
Verwijs naar specifieke bronnen met [Bron: naam, datum].""",
            }
        ]

        response = self.claude.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
        )

        answer = response.content[0].text

        # Step 5: Build citations
        citations = self._build_citations(chunks)

        logger.info(
            "rag_query_completed",
            question=question[:80],
            chunks_used=len(chunks),
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
        )

        return answer, citations

    async def analyze_organization(
        self,
        profile: dict,
        sector: str,
        analysis_type: str = "full",
    ) -> dict:
        """
        Generate a comprehensive workforce analysis for an organization.
        Used by the /analyze endpoint.
        """
        # Retrieve sector-specific knowledge
        sector_knowledge = await self.embedder.search(
            query=f"workforce analyse {sector} sector kenmerken arbeidsmarkt",
            match_count=20,
            sector=sector,
        )

        # Retrieve risk-specific knowledge
        risk_knowledge = await self.embedder.search(
            query="vergrijzing arbeidsmarkt automatisering verzuim verloop innovatie risico",
            match_count=10,
            sector=sector,
        )

        # Retrieve intervention knowledge
        intervention_knowledge = await self.embedder.search(
            query="interventies strategische personeelsplanning retentie verzuimreductie",
            match_count=10,
        )

        # Combine all knowledge
        all_chunks = sector_knowledge + risk_knowledge + intervention_knowledge
        # Deduplicate by chunk id
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            cid = chunk.get("id")
            if cid not in seen:
                seen.add(cid)
                unique_chunks.append(chunk)

        context = self._assemble_context(unique_chunks, profile)

        analysis_prompt = f"""Analyseer de volgende organisatie en genereer een workforce-rapport.

ORGANISATIEPROFIEL:
{self._format_profile(profile)}

BESCHIKBARE KENNISBASIS:
{context}

---

Genereer een JSON-response met de volgende structuur:
{{
    "workforce_health_score": <0-100>,
    "risk_summary": "<korte samenvatting van de 3 grootste risico's>",
    "arbeidsmarkt_analyse": {{
        "krapte_niveau": "<laag|midden|hoog>",
        "moeilijkst_vervulbare_functies": ["..."],
        "regionale_factoren": "..."
    }},
    "ai_impact_analyse": {{
        "exposure_level": "<laag|midden|hoog>",
        "meest_kwetsbare_functies": ["..."],
        "kansen": ["..."]
    }},
    "skills_gap_analyse": {{
        "kritieke_gaps": ["..."],
        "ontwikkelprioriteiten": ["..."]
    }},
    "verloop_verzuim_diagnose": {{
        "verloop_oorzaken": ["..."],
        "verzuim_drivers": ["..."],
        "benchmarkvergelijking": "..."
    }},
    "actieplan": {{
        "horizon_1_nu": ["<acties voor komende 3 maanden>"],
        "horizon_2_middellang": ["<acties 3-12 maanden>"],
        "horizon_3_strategisch": ["<acties 1-3 jaar>"]
    }},
    "sources_used": ["<bronvermeldingen>"]
}}

Baseer alles op de beschikbare data. Wees specifiek voor de sector {sector}."""

        response = self.claude.messages.create(
            model=self.model,
            max_tokens=8192,
            system=ARCHITECT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": analysis_prompt}],
        )

        return {
            "raw_analysis": response.content[0].text,
            "citations": self._build_citations(unique_chunks),
            "chunks_used": len(unique_chunks),
            "tokens": {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
            },
        }

    # ============================================
    # Context Assembly
    # ============================================

    def _assemble_context(
        self,
        chunks: list[dict],
        organization_context: dict | None = None,
    ) -> str:
        """Build the context string from retrieved chunks."""
        parts = []

        # Group by source for readability
        by_source: dict[str, list[dict]] = {}
        for chunk in chunks:
            source = chunk.get("source_name", "Onbekende bron")
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(chunk)

        for source, source_chunks in by_source.items():
            date_str = ""
            if source_chunks[0].get("source_date"):
                date_str = f" ({source_chunks[0]['source_date']})"

            parts.append(f"### {source}{date_str}")
            for chunk in source_chunks:
                parts.append(chunk.get("chunk_text", ""))
            parts.append("")  # blank line between sources

        context = "\n".join(parts)

        # Add organization context if available
        if organization_context:
            org_str = self._format_profile(organization_context)
            context = f"## Organisatiecontext\n{org_str}\n\n## Kennisbasis\n{context}"

        return context

    @staticmethod
    def _format_profile(profile: dict) -> str:
        """Format organization profile for inclusion in prompt."""
        lines = []
        field_labels = {
            "name": "Organisatie",
            "sector": "Sector",
            "employee_count": "Aantal medewerkers",
            "average_age": "Gemiddelde leeftijd",
            "turnover_rate": "Verlooppercentage",
            "absence_rate": "Verzuimpercentage",
            "revenue": "Omzet (EUR)",
            "fte_count": "Aantal FTE",
        }
        for key, label in field_labels.items():
            val = profile.get(key)
            if val is not None:
                lines.append(f"- {label}: {val}")

        # Strategic priorities
        priorities = profile.get("strategic_priorities")
        if priorities:
            lines.append(f"- Strategische prioriteiten: {', '.join(priorities)}")

        return "\n".join(lines) if lines else "Geen organisatiegegevens beschikbaar."

    @staticmethod
    def _build_citations(chunks: list[dict]) -> list[Citation]:
        """Build citation list from retrieved chunks."""
        seen_sources = set()
        citations = []

        for chunk in chunks:
            source = chunk.get("source_name", "")
            if source in seen_sources:
                continue
            seen_sources.add(source)

            citations.append(Citation(
                source_name=source,
                source_url=chunk.get("source_url"),
                source_date=chunk.get("source_date"),
                relevance=chunk.get("similarity", 0),
                excerpt=chunk.get("chunk_text", "")[:200],
            ))

        return sorted(citations, key=lambda c: c.relevance, reverse=True)
