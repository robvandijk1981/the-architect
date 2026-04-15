"""
FASE 5.1: AI Interpretation Layer
Transforms calculation results into human-readable Dutch insights using Claude API.
"""

import httpx
import json
import structlog
from typing import Dict, Any
from datetime import datetime

from app.core.config import get_settings

logger = structlog.get_logger()


class ArchitectInterpreter:
    """
    Uses Claude API to generate natural language insights from calculation results.
    Positioned as ModellenWerk's workforce strategy AI.
    """

    # Dutch system prompts for different contexts
    SYSTEM_PROMPTS = {
        "default": """Je bent de workforce intelligence van ModellenWerk.
Je taak is om ingewikkelde calculatieresultaten om te zetten in heldere, actionable inzichten.

Richtlijnen:
- Schrijf altijd in Nederlands
- Wees direct en concreet: geen jargon
- Focus op de business-impact, niet op de getallen
- Geef duidelijke aanbevelingen die te implementeren zijn
- Vlag risico's en onzekerheden expliciet
- Positioneer ModellenWerk als strategische partner van de CHRO/bestuur

Format van output:
- Begrijpelijk voor niet-technische stakeholders
- Geschikt voor C-level presentaties
- Grounded in data maar leesbaar als verhaal
- Action-oriented: wat doen we eraan?""",

        "chro": """Je bent de workforce intelligence van ModellenWerk.
Adresseer een Chief HR Officer die werkelijkheden wil begrijpen en beslissingen moet nemen.

Focus:
- Wat betekent dit voor ons organisatie en cultuur?
- Welke risico's lopen we?
- Waar moet het bestuur op letten?
- Welke interventies geven het meeste return?

Schrijf accessible maar serieus. Geen fluff.""",

        "workshop": """Je bent de workforce intelligence van ModellenWerk.
Genereer een snelle, inspirerende insight voor een live workshop sessie.
Maximum 100 woorden. Maak het relevant, actionable, en spannend.""",
    }

    @classmethod
    async def interpret_results(
        cls,
        calculation_type: str,
        results: Dict[str, Any],
        sector: str,
        confidence_level: str = "medium",
    ) -> Dict[str, Any]:
        """
        Interpret calculation results and generate structured insights.

        Args:
            calculation_type: Type of calculation (vacancy_cost, turnover_cost, etc.)
            results: Raw calculation result dict
            sector: Sector ID (healthcare, overheid, etc.)
            confidence_level: Confidence level of the calculation

        Returns:
            Structured insights: {
                "executive_summary": str,
                "key_findings": [str, ...],
                "recommendations": [str, ...],
                "risk_flags": [str, ...],
                "confidence_assessment": str,
                "generated_at": ISO timestamp
            }
        """
        settings = get_settings()
        if not settings.anthropic_api_key:
            logger.warning("anthropic_api_key_not_set")
            return cls._fallback_interpretation(calculation_type, results, sector)

        prompt = cls._build_interpretation_prompt(calculation_type, results, sector)

        try:
            response = await cls._call_claude(
                prompt,
                system_prompt=cls.SYSTEM_PROMPTS["default"],
                max_tokens=1500,
            )

            # Parse Claude's response as JSON
            try:
                insights = json.loads(response)
            except json.JSONDecodeError:
                # If Claude didn't return JSON, parse the text into structured format
                insights = cls._parse_text_response(response, calculation_type)

            insights["generated_at"] = datetime.utcnow().isoformat()
            insights["confidence_assessment"] = cls._assess_confidence(confidence_level, results)

            return insights

        except Exception as e:
            logger.error("claude_interpretation_error", error=str(e))
            return cls._fallback_interpretation(calculation_type, results, sector)

    @classmethod
    async def generate_narrative(
        cls,
        results: Dict[str, Any],
        audience: str = "chro",
    ) -> str:
        """
        Generate a narrative paragraph suitable for board presentation.

        Args:
            results: Calculation results
            audience: Target audience (chro, board, workshop)

        Returns:
            A single coherent paragraph in Dutch
        """
        settings = get_settings()
        if not settings.anthropic_api_key:
            return cls._fallback_narrative(results, audience)

        system = cls.SYSTEM_PROMPTS.get(audience, cls.SYSTEM_PROMPTS["default"])

        prompt = f"""Zet deze calculatieresultaten om in een korte, impactvolle paragraaf (max 4 zinnen)
voor presentatie aan het {audience}.

Resultaten:
{json.dumps(results, indent=2, ensure_ascii=False)}

Vereisten:
- Nederlands
- Direct op het punt af
- Focus op business-impact
- Begrijpelijk voor niet-technische lezers
- Geen getallen tenzij ze echt cruciaal zijn

Antwoord: [alleen de paragraaf, geen introductie]"""

        try:
            narrative = await cls._call_claude(prompt, system_prompt=system, max_tokens=300)
            return narrative.strip()
        except Exception as e:
            logger.error("claude_narrative_error", error=str(e))
            return cls._fallback_narrative(results, audience)

    @classmethod
    async def compare_scenarios_narrative(
        cls,
        scenario_a: Dict[str, Any],
        scenario_b: Dict[str, Any],
    ) -> str:
        """
        Compare two scenarios in natural language.

        Args:
            scenario_a: First scenario results
            scenario_b: Second scenario results

        Returns:
            Comparison narrative in Dutch
        """
        settings = get_settings()
        if not settings.anthropic_api_key:
            return cls._fallback_scenario_comparison(scenario_a, scenario_b)

        prompt = f"""Vergelijk deze twee workforce scenario's en geef een helder advies welke te kiezen.

Scenario A (baseline):
{json.dumps(scenario_a, indent=2, ensure_ascii=False)[:1000]}

Scenario B (alternative):
{json.dumps(scenario_b, indent=2, ensure_ascii=False)[:1000]}

Antwoord:
1. Korte samenvatting van het verschil
2. Voor- en nadelen van elk scenario
3. Wat is je aanbeveling en waarom?

Schrijf in Nederlands, voor CHRO-publiek."""

        try:
            comparison = await cls._call_claude(
                prompt,
                system_prompt=cls.SYSTEM_PROMPTS["chro"],
                max_tokens=600,
            )
            return comparison.strip()
        except Exception as e:
            logger.error("claude_scenario_comparison_error", error=str(e))
            return cls._fallback_scenario_comparison(scenario_a, scenario_b)

    @classmethod
    async def generate_workshop_insight(
        cls,
        live_data: Dict[str, Any],
    ) -> str:
        """
        Generate quick insight for live workshop (< 100 words).

        Args:
            live_data: Live workshop data/calculation

        Returns:
            Quick insight in Dutch
        """
        settings = get_settings()
        if not settings.anthropic_api_key:
            return "Workshop insight: gegevens ontvangen. Analyseer met het team."

        prompt = f"""Workshop-inzicht nodig - snelle, inspirerende observatie.

Data:
{json.dumps(live_data, indent=2, ensure_ascii=False)[:500]}

Eisen:
- Max 100 woorden
- Nederlands
- Actionable en inspirerend
- Geschikt om live te presenteren aan het team"""

        try:
            insight = await cls._call_claude(
                prompt,
                system_prompt=cls.SYSTEM_PROMPTS["workshop"],
                max_tokens=150,
            )
            return insight.strip()
        except Exception as e:
            logger.error("claude_workshop_insight_error", error=str(e))
            return "Workshop insight: Data ontvangen. Verder analyseren."

    # ============ PRIVATE HELPERS ============

    @classmethod
    async def _call_claude(
        cls,
        user_message: str,
        system_prompt: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Call Anthropic Claude API.

        Args:
            user_message: User prompt
            system_prompt: System context
            max_tokens: Max response tokens

        Returns:
            Claude's text response
        """
        settings = get_settings()
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload = {
            "model": settings.claude_model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

            result = response.json()
            return result["content"][0]["text"]

    @classmethod
    def _build_interpretation_prompt(
        cls,
        calculation_type: str,
        results: Dict[str, Any],
        sector: str,
    ) -> str:
        """Build the interpretation prompt for Claude."""

        context = {
            "vacancy_cost": "Analyse van de kosten van openstaande vacatures",
            "turnover_cost": "Analyse van de kosten van personeelsverloop",
            "absenteeism_cost": "Analyse van de kosten van ziekteverzuim en burnout",
            "cost_of_inaction": "Integrale analyse van workforce-risico's (vacatures, verloop, verzuim)",
            "reskilling_roi": "Return on Investment analyse van scholingsprogramma's",
            "automation_roi": "Return on Investment analyse van procesautomatie",
            "benchmark_score": "Benchmarking van organisatie tegen sector",
        }

        prompt = f"""Analyseer deze workforce calculatieresultaten en genereer gestructureerde inzichten.

Context: {context.get(calculation_type, calculation_type)}
Sector: {sector}

Resultaten:
{json.dumps(results, indent=2, ensure_ascii=False)[:2000]}

Genereer een JSON-response met deze structure:
{{
  "executive_summary": "1-2 zinnen over de kernbevinding",
  "key_findings": ["bevinding 1", "bevinding 2", "bevinding 3"],
  "recommendations": ["aanbeveling 1", "aanbeveling 2", "aanbeveling 3"],
  "risk_flags": ["risico 1", "risico 2"],
}}

Richtlijnen:
- Nederlands
- Concreet, niet abstract
- Action-oriented
- Geschikt voor CHRO-niveau"""

        return prompt

    @classmethod
    def _parse_text_response(
        cls,
        text: str,
        calculation_type: str,
    ) -> Dict[str, Any]:
        """
        Parse Claude's text response into structured format if not JSON.
        """
        return {
            "executive_summary": text[:200],
            "key_findings": [text[200:400]],
            "recommendations": [text[400:600]],
            "risk_flags": ["Controleer data quality en benchmarks"],
        }

    @classmethod
    def _assess_confidence(
        cls,
        confidence_level: str,
        results: Dict[str, Any],
    ) -> str:
        """
        Assess and articulate confidence in the results.
        """
        assessments = {
            "high": "Deze berekening is gebaseerd op valide data en geverifieerde benchmarks. Hoge zekerheid.",
            "medium": "Deze berekening is gebaseerd op redelijke aannames. Gebruik als gids, valideer met experts.",
            "low": "Deze berekening is illustratief. Verzamel meer data voordat je grote beslissingen neemt.",
        }

        base = assessments.get(confidence_level, assessments["medium"])

        # Add data quality note
        if "sources" in results and len(results.get("sources", [])) < 2:
            base += " Bron-diversiteit kan verbeteren."

        return base

    @classmethod
    def _fallback_interpretation(
        cls,
        calculation_type: str,
        results: Dict[str, Any],
        sector: str,
    ) -> Dict[str, Any]:
        """
        Fallback interpretation when Claude API is unavailable.
        """
        total_cost = results.get("total_annual_cost", 0)

        return {
            "executive_summary": f"Calculatie voltooid voor {sector}. Jaarlijkse impact geschat op €{total_cost:,.0f}.",
            "key_findings": [
                f"Primaire kostendriver geïdentificeerd: {calculation_type.replace('_', ' ')}",
                "Benchmarking tegen sector beschikbaar",
                "Details in volledige rapportage",
            ],
            "recommendations": [
                "Valideer deze bevindingen met je HR-team",
                "Scenario-analyse uitvoeren voor interventie-opties",
                "Plan vervolgstappen met ModellenWerk",
            ],
            "risk_flags": [
                "Claude API niet beschikbaar - template-based fallback gebruikt",
                "Valideer alle aannames met domeinexperts",
            ],
            "generated_at": datetime.utcnow().isoformat(),
            "confidence_assessment": "Template-based fallback. Zet Claude API in production voor betere inzichten.",
        }

    @classmethod
    def _fallback_narrative(
        cls,
        results: Dict[str, Any],
        audience: str,
    ) -> str:
        """Fallback narrative when Claude API is unavailable."""
        cost = results.get("total_annual_cost", 0)
        return f"De calculatie toont een jaarlijkse impact van €{cost:,.0f}. Meer context nodig voor volledig inzicht."

    @classmethod
    def _fallback_scenario_comparison(
        cls,
        scenario_a: Dict[str, Any],
        scenario_b: Dict[str, Any],
    ) -> str:
        """Fallback scenario comparison when Claude API is unavailable."""
        cost_a = scenario_a.get("total_cost", 0)
        cost_b = scenario_b.get("total_cost", 0)
        diff = cost_b - cost_a
        better = "B" if diff < 0 else "A"
        return f"Scenario {better} is kosteffectiver (verschil: €{abs(diff):,.0f}). Valideer met team."
