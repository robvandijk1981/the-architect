"""RAG service — orchestrates retrieval + structured data + Claude for grounded responses."""

import anthropic
import structlog
from decimal import Decimal

from app.core.config import get_settings
from app.core.database import fetch_all, fetch_one
from app.services.embedder import EmbeddingService
from app.models.knowledge import Citation

logger = structlog.get_logger()

# System prompt for The Architect — v2: Intelligent Analyst
ARCHITECT_SYSTEM_PROMPT = """Je bent The Architect, de workforce intelligence specialist van ModellenWerk.
Je bent een expert op het gebied van strategische personeelsplanning (SPP), workforce analytics,
AI-impact op werk, en arbeidsmarktanalyse voor de Nederlandse markt.

KERNREGELS:
1. Baseer ELKE uitspraak op de bronnen in je context. Geen speculatie.
2. Vermeld bij elke claim de bron en datum: [Bron: CBS StatLine, jan 2026]
3. Als je iets niet weet of de data ontbreekt, zeg dat eerlijk.
4. Geef sectorspecifiek advies — vermijd generieke uitspraken.
5. Gebruik Nederlandse terminologie en context.
6. Bij tegenstrijdige bronnen: benoem beide en geef aan welke recenter/betrouwbaarder is.
7. Presenteer cijfers altijd met context (trend, benchmark, vergelijking).

ANALYTISCHE CAPACITEITEN:
1. Cross-referencing: combineer gestructureerde data (functies, organisaties, percentages)
   met kennisbank-bronnen tot geïntegreerde inzichten. Als je zowel exacte cijfers als
   contextuele kennis hebt, gebruik BEIDE in je antwoord.
2. Trendanalyse: als je data over meerdere perioden hebt (2025-2027 t/m 2037-2040),
   benoem de trend en projecteer de richting. Geef concrete cijfers per periode.
3. Benchmarking: vergelijk de gevraagde organisatie/functie ALTIJD met het sectorgemiddelde.
   Benoem expliciet of ze boven of onder benchmark zitten en wat dat betekent.
4. Scenariodenken: bij business cases, presenteer altijd drie scenario's (25%/50%/75% adoptie)
   met onderbouwing uit de data. Geef de bandbreedte, niet één getal.
5. Actiegerichtheid: sluit elk advies af met concrete aanbevelingen:
   wat moet de klant NU doen (0-3 maanden), over 6 maanden, over 2 jaar.
6. Competentie-brug: als je impact op functies bespreekt, koppel dit ALTIJD aan:
   - Welke competenties vervallen en welke nodig zijn (uit de functie-database)
   - Welke opleidingen beschikbaar zijn (uit de kennisbank)
7. Compliance-bewustzijn: als de gevraagde AI-toepassing onder hoog-risico EU AI Act valt,
   vermeld dit proactief met de relevante compliance-eisen.
8. Kostenonderbouwing: gebruik echte salarisdata en sectorparameters bij berekeningen,
   niet schattingen. Verwijs naar de bron van de gebruikte parameters.

DATABRONNEN (gebruik altijd de meest specifieke bron):
- Gestructureerde database: exacte cijfers over functies, organisaties, impact-percentages
- RAG-kennisbank: contextuele kennis over arbeidsmarkt, interventies, regelgeving
- Sectorprofielen: benchmarks per sector (FTE, verzuim, krapte, AI-baten)
- Business case parameters: kosten en baten berekeningen

TOON:
- Professioneel maar toegankelijk
- Data-gedreven met praktische aanbevelingen
- Eerlijk over onzekerheden en beperkingen
- Directief waar de data het toelaat, voorzichtig waar het onzeker is
"""


def _decimal_to_str(val):
    """Convert Decimal to string for prompt inclusion."""
    if isinstance(val, Decimal):
        return str(float(val))
    return str(val) if val is not None else "n.v.t."


class RAGService:
    """Retrieval-Augmented Generation + Structured Data for workforce intelligence."""

    def __init__(self):
        settings = get_settings()
        self.claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.embedder = EmbeddingService()
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens

    # ============================================
    # Structured Data Lookup
    # ============================================

    async def _lookup_structured_data(self, question: str, sector: str | None = None) -> str:
        """
        Query the structured database for relevant data based on the question.
        Returns formatted context string, or empty string if no relevant data found.
        """
        q_lower = question.lower()
        parts = []

        # Detect sector mentions in the question
        sector_keywords = {
            "zorg": "Zorg", "gezondheid": "Zorg", "ziekenhuis": "Zorg", "verpleeg": "Zorg",
            "overheid": "Overheid", "gemeente": "Overheid", "rijks": "Overheid", "politie": "Overheid",
            "transport": "Transport", "trein": "Transport", "bus": "Transport", "haven": "Transport",
            "energie": "Energie", "netbeheer": "Energie", "elektr": "Energie",
            "bouw": "Bouw", "construct": "Bouw",
            "onderwijs": "Onderwijs", "school": "Onderwijs", "docent": "Onderwijs", "leraar": "Onderwijs",
        }
        detected_sector = sector
        if not detected_sector:
            for keyword, sec in sector_keywords.items():
                if keyword in q_lower:
                    detected_sector = sec
                    break

        # 1. Look up function data if a function or role is mentioned
        try:
            function_rows = await fetch_all(
                "SELECT * FROM function_profiles LIMIT 0"  # Just check if table exists
            )
        except Exception:
            return ""  # Tables don't exist yet

        # Search for function names in the question
        try:
            all_functions = await fetch_all(
                "SELECT id, sector, functiegroep, functie FROM function_profiles"
            )
            matched_functions = []
            for f in all_functions:
                if f["functie"].lower() in q_lower or any(
                    word in q_lower for word in f["functie"].lower().split()
                    if len(word) > 4  # Skip short words
                ):
                    matched_functions.append(f)

            # If we have a sector but no function match, get top functions for that sector
            if not matched_functions and detected_sector:
                matched_functions = [
                    f for f in all_functions
                    if f["sector"].lower() == detected_sector.lower()
                ][:5]  # Top 5 functions for the sector

            for func in matched_functions[:3]:  # Max 3 functions in context
                func_id = str(func["id"])

                # Get impact data
                impacts = await fetch_all(
                    "SELECT * FROM function_impacts WHERE function_id = $1 ORDER BY period",
                    func_id,
                )

                if impacts:
                    parts.append(f"\n### Functie: {func['functie']} ({func['sector']} > {func['functiegroep']})")
                    parts.append("| Periode | AI Onderst. | AI Augm. | AI Verv. | Robot Onderst. | Robot Augm. | Robot Verv. |")
                    parts.append("|---------|------------|----------|----------|---------------|-------------|-------------|")
                    for imp in impacts:
                        parts.append(
                            f"| {imp['period']} | {_decimal_to_str(imp['ai_ondersteuning'])}% | "
                            f"{_decimal_to_str(imp['ai_augmentatie'])}% | {_decimal_to_str(imp['ai_vervanging'])}% | "
                            f"{_decimal_to_str(imp['robotisering_ondersteuning'])}% | "
                            f"{_decimal_to_str(imp['robotisering_augmentatie'])}% | "
                            f"{_decimal_to_str(imp['robotisering_vervanging'])}% |"
                        )

                # Get competency data for most relevant period
                comps = await fetch_all(
                    "SELECT * FROM function_competencies WHERE function_id = $1 ORDER BY period",
                    func_id,
                )
                if comps:
                    parts.append("\nCompetentie-transitie:")
                    for c in comps:
                        new_c = c.get("nieuwe_competenties") or []
                        old_c = c.get("vervallen_competenties") or []
                        if new_c or old_c:
                            parts.append(f"- {c['period']}: Nieuw: {', '.join(new_c[:3])}. Vervalt: {', '.join(old_c[:2])}")

                # Get dimension scores
                parts.append(f"\n9-Dimensie Impact: FTE={func.get('dim_fte_impact', 'n.v.t.')}, "
                           f"Competenties={func.get('dim_competenties_scholing', 'n.v.t.')}, "
                           f"Productiviteit={func.get('dim_productiviteit_kwaliteit', 'n.v.t.')}")

        except Exception as e:
            logger.warning("structured_function_lookup_failed", error=str(e))

        # 2. Look up organization data if an organization is mentioned
        try:
            org_keywords = [
                "erasmus", "umc", "amsterdam", "radboud", "isala", "maastricht",
                "alliander", "shell", "enexis", "stedin", "tennet", "gasunie", "eneco",
                "politie", "belastingdienst", "defensie", "uwv", "rijkswaterstaat",
                "bam", "heijmans", "volker", "dura", "strukton",
                "ns ", "prorail", "schiphol", "klm",
                "hogeschool", "universiteit", "roc",
            ]
            for kw in org_keywords:
                if kw in q_lower:
                    orgs = await fetch_all(
                        "SELECT * FROM organizations WHERE lower(name) LIKE '%' || $1 || '%' AND source = 'readiness_scan_2026' LIMIT 3",
                        kw,
                    )
                    for org in orgs:
                        parts.append(f"\n### Organisatie: {org['name']} ({org['sector_slug']})")
                        parts.append(f"- FTE: {org.get('employee_count', 'n.v.t.')}")
                        parts.append(f"- Personeelskosten: €{_decimal_to_str(org.get('personeelskosten_mln'))}M")
                        parts.append(f"- Verzuim: {_decimal_to_str(org.get('verzuim_pct'))}%")
                        parts.append(f"- Vacatures: {org.get('vacatures', 'n.v.t.')}")
                        parts.append(f"- Kosten krapte: €{_decimal_to_str(org.get('kosten_krapte_totaal_mln'))}M")
                        parts.append(f"- AI-baten (25%/50%/75%): €{_decimal_to_str(org.get('ai_baten_25_mln'))}M / "
                                   f"€{_decimal_to_str(org.get('ai_baten_50_mln'))}M / "
                                   f"€{_decimal_to_str(org.get('ai_baten_75_mln'))}M")
                        parts.append(f"- FTE bespaard (50%): {org.get('fte_bespaard_50', 'n.v.t.')}")
                        if org.get('ai_status'):
                            parts.append(f"- AI-status: {org['ai_status'][:300]}")
                    break  # Only match first org keyword
        except Exception as e:
            logger.warning("structured_org_lookup_failed", error=str(e))

        # 3. Look up sector profile if sector is mentioned
        if detected_sector:
            try:
                sector_slug = detected_sector.lower()
                sp = await fetch_one(
                    "SELECT * FROM sector_profiles WHERE sector_slug = $1", sector_slug
                )
                if sp:
                    parts.append(f"\n### Sectorprofiel: {detected_sector}")
                    parts.append(f"- Totaal FTE: {sp.get('fte', 'n.v.t.')}")
                    parts.append(f"- Personeelskosten: €{_decimal_to_str(sp.get('personeelskosten_mln'))}M")
                    parts.append(f"- Vacatures: {sp.get('vacatures', 'n.v.t.')}")
                    parts.append(f"- Gem. verzuim: {_decimal_to_str(sp.get('gem_verzuim_pct'))}%")
                    parts.append(f"- Kosten krapte sector: €{_decimal_to_str(sp.get('kosten_krapte_mln'))}M")
                    parts.append(f"- AI-parameters: {_decimal_to_str(sp.get('ai_ondersteuning_pct'))}% ondersteuning, "
                               f"{_decimal_to_str(sp.get('ai_augmentatie_pct'))}% augmentatie, "
                               f"{_decimal_to_str(sp.get('ai_vervanging_pct'))}% vervanging")
                    parts.append(f"- AI-baten (50%): €{_decimal_to_str(sp.get('ai_baten_50_mln'))}M")
                    parts.append(f"- FTE bespaard (50%): {sp.get('fte_bespaard_50', 'n.v.t.')}")
            except Exception as e:
                logger.warning("structured_sector_lookup_failed", error=str(e))

        # 4. If business case / kosten / baten is mentioned, add simulation context
        if any(kw in q_lower for kw in ["kosten", "baten", "business case", "besparing", "investering", "roi"]):
            try:
                totals = await fetch_one("""
                    SELECT
                        sum(kosten_krapte_totaal_mln) as total_krapte,
                        sum(ai_baten_50_mln) as total_baten,
                        sum(fte_bespaard_50) as total_fte,
                        count(*) as org_count
                    FROM organizations WHERE source = 'readiness_scan_2026'
                """)
                if totals and totals.get("total_krapte"):
                    parts.append(f"\n### Nationale Totalen (60 organisaties)")
                    parts.append(f"- Totale kosten personeelskrapte: €{_decimal_to_str(totals['total_krapte'])}M")
                    parts.append(f"- Totale AI-baten (50% adoptie): €{_decimal_to_str(totals['total_baten'])}M")
                    parts.append(f"- Totaal FTE bespaard (50%): {totals['total_fte']}")
            except Exception as e:
                logger.warning("structured_totals_lookup_failed", error=str(e))

        if parts:
            return "## GESTRUCTUREERDE DATA (exacte cijfers uit database)\n" + "\n".join(parts)
        return ""

    # ============================================
    # Main Query Pipeline
    # ============================================

    async def query(
        self,
        question: str,
        sector: str | None = None,
        organization_context: dict | None = None,
        max_sources: int = 15,
        system_prompt_override: str | None = None,
    ) -> tuple[str, list[Citation]]:
        """
        Hybrid RAG pipeline:
        1. Query structured database (functions, organizations, sectors)
        2. Embed question + retrieve relevant RAG chunks
        3. Combine structured data + RAG context
        4. Generate answer with Claude
        5. Extract citations
        """
        # Step 1: Structured data lookup
        structured_context = await self._lookup_structured_data(question, sector)

        # Step 2: Retrieve relevant knowledge (RAG)
        chunks = await self.embedder.search(
            query=question,
            match_count=max_sources,
            sector=sector,
            threshold=0.25,
        )

        if not chunks and not structured_context:
            logger.warning("no_data_found", question=question[:100], sector=sector)
            return (
                "Ik heb onvoldoende bronnen gevonden om deze vraag betrouwbaar te beantwoorden. "
                "Kun je je vraag specifieker maken, of een sector aangeven?",
                [],
            )

        # Step 3: Assemble combined context
        rag_context = self._assemble_context(chunks, organization_context)

        # Combine: structured data first (exact), then RAG (contextual)
        full_context = ""
        if structured_context:
            full_context += structured_context + "\n\n"
        if rag_context:
            full_context += "## KENNISBASIS (contextuele bronnen)\n" + rag_context

        # Step 4: Generate with Claude
        system = system_prompt_override or ARCHITECT_SYSTEM_PROMPT
        messages = [
            {
                "role": "user",
                "content": f"""BESCHIKBARE DATA EN KENNISBASIS:

{full_context}

---

VRAAG: {question}

Beantwoord deze vraag door gestructureerde data (exacte cijfers) te combineren met
contextuele kennis uit de kennisbasis. Gebruik ALTIJD de exacte cijfers als die beschikbaar zijn.
Verwijs naar bronnen met [Bron: naam, datum] en naar database-cijfers met [Data: tabel].""",
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
            "hybrid_rag_query_completed",
            question=question[:80],
            chunks_used=len(chunks),
            has_structured_data=bool(structured_context),
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
        # Get structured data for the sector
        structured_context = await self._lookup_structured_data(
            f"workforce analyse {sector} AI impact functies kosten baten", sector
        )

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
            query="interventies strategische personeelsplanning retentie verzuimreductie AI verandermanagement",
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

        rag_context = self._assemble_context(unique_chunks, profile)

        # Build full context
        full_context = ""
        if structured_context:
            full_context += structured_context + "\n\n"
        full_context += rag_context

        analysis_prompt = f"""Analyseer de volgende organisatie en genereer een workforce-rapport.

ORGANISATIEPROFIEL:
{self._format_profile(profile)}

BESCHIKBARE DATA EN KENNISBASIS:
{full_context}

---

Genereer een JSON-response met de volgende structuur:
{{
    "workforce_health_score": <0-100>,
    "risk_summary": "<korte samenvatting van de 3 grootste risico's>",
    "arbeidsmarkt_analyse": {{
        "krapte_niveau": "<laag|midden|hoog>",
        "moeilijkst_vervulbare_functies": ["..."],
        "regionale_factoren": "...",
        "benchmark_vergelijking": "<hoe verhoudt deze org zich tot sectorgemiddelde>"
    }},
    "ai_impact_analyse": {{
        "exposure_level": "<laag|midden|hoog>",
        "meest_kwetsbare_functies": ["..."],
        "kansen": ["..."],
        "scenario_25": "<korte beschrijving conservatief scenario>",
        "scenario_50": "<korte beschrijving basisscenario>",
        "scenario_75": "<korte beschrijving ambitieus scenario>",
        "eu_ai_act_risicos": ["<hoog-risico AI toepassingen in deze sector>"]
    }},
    "skills_gap_analyse": {{
        "kritieke_gaps": ["..."],
        "ontwikkelprioriteiten": ["..."],
        "beschikbare_opleidingen": ["<concrete opleidingen uit kennisbank>"]
    }},
    "verloop_verzuim_diagnose": {{
        "verloop_oorzaken": ["..."],
        "verzuim_drivers": ["..."],
        "benchmarkvergelijking": "...",
        "kosten_impact": "<berekende kosten van verzuim/verloop>"
    }},
    "actieplan": {{
        "horizon_1_nu": ["<acties voor komende 3 maanden>"],
        "horizon_2_middellang": ["<acties 3-12 maanden>"],
        "horizon_3_strategisch": ["<acties 1-3 jaar>"]
    }},
    "business_case_samenvatting": {{
        "kosten_krapte": "<berekend uit data>",
        "potentiele_baten_50": "<berekend uit data>",
        "investering_nodig": "<geschat>",
        "terugverdientijd": "<geschat>"
    }},
    "sources_used": ["<bronvermeldingen>"]
}}

Baseer alles op de beschikbare data. Gebruik EXACTE CIJFERS uit de gestructureerde database.
Wees specifiek voor de sector {sector}. Combineer data met contextuele kennis."""

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
            "has_structured_data": bool(structured_context),
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
