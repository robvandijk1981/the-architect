"""AZW (Arbeidsmarkt Zorg & Welzijn) monitor collector."""

from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import structlog

from app.collectors.base import BaseCollector
from app.models.knowledge import KnowledgeDocument, SourceType, KnowledgeCategory

logger = structlog.get_logger()


class AZWMonitorCollector(BaseCollector):
    """
    Collects data from the AZW (Arbeidsmarkt Zorg & Welzijn) monitor.

    The AZW program provides detailed labour market data for the healthcare
    and welfare sector, including:
    - Personnel numbers by branch
    - Vacancy rates
    - Absence rates
    - Training and development
    - Regional variation

    Source: https://www.azwinfo.nl
    Data: https://azwstatline.cbs.nl
    """

    name = "AZW Monitor"
    description = "Arbeidsmarkt Zorg & Welzijn — sectorspecifieke arbeidsmarktdata zorg"
    source_type = SourceType.SECTOR_MONITOR
    category = KnowledgeCategory.SECTORKENNIS
    layer = 2
    default_expiry_days = 30

    # AZW StatLine tables (hosted by CBS for AZW)
    AZW_STATLINE_BASE = "https://odata4.cbs.nl/AZWstatline"

    AZW_TABLES = {
        "werknemers": {
            "id": "120010NED",
            "title": "AZW Werknemers in zorg en welzijn",
            "description": "Aantal werknemers, banen, arbeidsduur per branche",
        },
        "vacatures": {
            "id": "120020NED",
            "title": "AZW Vacatures in zorg en welzijn",
            "description": "Openstaande vacatures per branche en regio",
        },
        "verzuim": {
            "id": "120030NED",
            "title": "AZW Ziekteverzuim in zorg en welzijn",
            "description": "Verzuimpercentage en meldingsfrequentie per branche",
        },
        "mobiliteit": {
            "id": "120040NED",
            "title": "AZW Mobiliteit in zorg en welzijn",
            "description": "In- en uitstroom, interne mobiliteit per branche",
        },
    }

    # AZW info pages for qualitative data
    AZW_INFO_PAGES = [
        {
            "url": "https://www.azwinfo.nl/jaarrapport",
            "title": "AZW Jaarrapport — Stand van zaken arbeidsmarkt zorg en welzijn",
        },
        {
            "url": "https://www.azwinfo.nl/highlights",
            "title": "AZW Highlights — Belangrijkste ontwikkelingen zorg en welzijn",
        },
    ]

    # Healthcare sub-branches
    ZW_BRANCHES = [
        "Ziekenhuizen",
        "GGZ",
        "Gehandicaptenzorg",
        "Verpleging en verzorging",
        "Thuiszorg",
        "Huisartsen en gezondheidscentra",
        "Jeugdzorg",
        "Sociaal werk",
        "Kinderopvang",
    ]

    async def collect(self) -> list[KnowledgeDocument]:
        docs = []
        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "ModellenWerk-Architect/0.1 (workforce research)"},
            follow_redirects=True,
        ) as client:
            # Collect AZW StatLine tables
            for key, table_info in self.AZW_TABLES.items():
                try:
                    doc = await self._fetch_azw_table(client, key, table_info)
                    if doc:
                        docs.append(doc)
                except Exception as e:
                    logger.warning("azw_table_fetch_failed", table=key, error=str(e))

            # Collect AZW info pages
            for page_info in self.AZW_INFO_PAGES:
                try:
                    doc = await self._fetch_info_page(client, page_info)
                    if doc:
                        docs.append(doc)
                except Exception as e:
                    logger.warning("azw_page_fetch_failed", url=page_info["url"], error=str(e))

        return docs

    async def _fetch_azw_table(
        self, client: httpx.AsyncClient, key: str, table_info: dict
    ) -> KnowledgeDocument | None:
        """Fetch an AZW StatLine table."""
        table_id = table_info["id"]

        try:
            # Fetch observations
            obs_url = f"{self.AZW_STATLINE_BASE}/{table_id}/Observations"
            resp = await client.get(obs_url, params={"$format": "json", "$top": 50, "$orderby": "Id desc"})
            resp.raise_for_status()
            observations = resp.json().get("value", [])
        except httpx.HTTPStatusError as e:
            # AZW StatLine may use different endpoint structure
            logger.info("azw_odata_fallback", table=key, status=e.response.status_code)
            # Try alternative endpoint
            try:
                alt_url = f"https://azwstatline.cbs.nl/ODataApi/odata/{table_id}/TypedDataSet"
                resp = await client.get(alt_url, params={"$format": "json", "$top": 50})
                resp.raise_for_status()
                observations = resp.json().get("value", [])
            except Exception:
                observations = []

        content_parts = [
            f"# AZW Monitor: {table_info['title']}",
            f"Beschrijving: {table_info['description']}",
            f"Sector: Zorg en Welzijn",
            "",
        ]

        if observations:
            content_parts.append("## Data")
            content_parts.append("")

            # Get column names
            columns = [k for k in observations[0].keys() if k not in ("Id", "ID")]
            for obs in observations[:30]:
                parts = []
                for col in columns:
                    val = obs.get(col)
                    if val is not None:
                        parts.append(f"{col}: {val}")
                if parts:
                    content_parts.append("- " + " | ".join(parts))
        else:
            content_parts.append("Geen data beschikbaar via API. Mogelijk zijn de gegevens ")
            content_parts.append("beschikbaar via de AZW StatLine webinterface.")

        # Add context about healthcare branches
        content_parts.extend([
            "",
            "## Branches in Zorg en Welzijn",
            "",
        ])
        for branch in self.ZW_BRANCHES:
            content_parts.append(f"- {branch}")

        content = "\n".join(content_parts)

        return self.make_document(
            title=f"AZW {table_info['title']}",
            content=content,
            source_url=f"https://azwstatline.cbs.nl/#/AZW/nl/dataset/{table_id}",
            sector=["zorg"],
            metadata={"table_id": table_id, "key": key, "observations": len(observations)},
        )

    async def _fetch_info_page(
        self, client: httpx.AsyncClient, page_info: dict
    ) -> KnowledgeDocument | None:
        """Fetch and parse an AZW informational page."""
        resp = await client.get(page_info["url"])

        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        content_parts = [
            f"# {page_info['title']}",
            f"Bron: AZW Monitor (azwinfo.nl)",
            "",
        ]

        main = soup.find("main") or soup.find("article") or soup
        for elem in main.find_all(["h1", "h2", "h3", "p", "li"]):
            text = elem.get_text(strip=True)
            if text and len(text) > 10:
                if elem.name.startswith("h"):
                    level = int(elem.name[1])
                    content_parts.append(f"\n{'#' * level} {text}")
                elif elem.name == "li":
                    content_parts.append(f"- {text}")
                else:
                    content_parts.append(text)

        content = "\n".join(content_parts)

        if len(content) < 100:
            return None

        return self.make_document(
            title=page_info["title"],
            content=content,
            source_url=page_info["url"],
            sector=["zorg"],
            metadata={"type": "info_page"},
        )
