"""UWV Arbeidsmarkt collector — labour market tension and sector data."""

from datetime import datetime
import httpx
from bs4 import BeautifulSoup
import structlog

from app.collectors.base import BaseCollector
from app.models.knowledge import KnowledgeDocument, SourceType, KnowledgeCategory

logger = structlog.get_logger()


class UWVArbeidsmarktCollector(BaseCollector):
    """
    Collects labour market data from UWV (Uitvoeringsinstituut Werknemersverzekeringen).

    Sources:
    - UWV Spanningsindicator (arbeidsmarktkrapte per sector/regio)
    - UWV Sectorpagina's (sectorspecifieke arbeidsmarktinformatie)
    - UWV Beroepenkaart (knelpuntberoepen)

    Note: UWV data is partially available via data.overheid.nl and partially
    needs to be scraped from their dashboard pages.
    """

    name = "UWV Arbeidsmarkt"
    description = "Arbeidsmarktkrapte en sectorinformatie van UWV"
    source_type = SourceType.API_DATA
    category = KnowledgeCategory.ARBEIDSMARKT
    layer = 1
    default_expiry_days = 14  # UWV updates frequently

    # UWV public data endpoints
    SECTOR_PAGES = {
        "zorg": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/zorg-en-welzijn",
            "title": "UWV Arbeidsmarktinformatie Zorg en Welzijn",
        },
        "bouw": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/bouw",
            "title": "UWV Arbeidsmarktinformatie Bouw",
        },
        "techniek": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/techniek-en-industrie",
            "title": "UWV Arbeidsmarktinformatie Techniek en Industrie",
        },
        "onderwijs": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/onderwijs",
            "title": "UWV Arbeidsmarktinformatie Onderwijs",
        },
        "overheid": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/overheid",
            "title": "UWV Arbeidsmarktinformatie Overheid",
        },
        "financieel": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/financiele-dienstverlening",
            "title": "UWV Arbeidsmarktinformatie Financiële Dienstverlening",
        },
        "retail": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/handel",
            "title": "UWV Arbeidsmarktinformatie Handel",
        },
        "transport": {
            "url": "https://www.werk.nl/arbeidsmarktinformatie/sector/transport-en-logistiek",
            "title": "UWV Arbeidsmarktinformatie Transport en Logistiek",
        },
    }

    # UWV Open Data via data.overheid.nl
    OPEN_DATA_URL = "https://data.overheid.nl/dataset/uwv-arbeidsmarktdata"

    async def collect(self) -> list[KnowledgeDocument]:
        docs = []
        async with httpx.AsyncClient(
            timeout=30,
            headers={"User-Agent": "ModellenWerk-Architect/0.1 (workforce research)"},
            follow_redirects=True,
        ) as client:
            # Collect sector pages
            for sector, info in self.SECTOR_PAGES.items():
                try:
                    doc = await self._fetch_sector_page(client, sector, info)
                    if doc:
                        docs.append(doc)
                except Exception as e:
                    logger.warning(
                        "uwv_sector_fetch_failed",
                        sector=sector,
                        error=str(e),
                    )

            # Collect spanningsindicator overview
            try:
                spanning_doc = await self._fetch_spanningsindicator(client)
                if spanning_doc:
                    docs.append(spanning_doc)
            except Exception as e:
                logger.warning("uwv_spanning_fetch_failed", error=str(e))

        return docs

    async def _fetch_sector_page(
        self, client: httpx.AsyncClient, sector: str, info: dict
    ) -> KnowledgeDocument | None:
        """Fetch and parse a UWV sector information page."""
        resp = await client.get(info["url"])

        if resp.status_code != 200:
            logger.info("uwv_page_not_found", sector=sector, status=resp.status_code)
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # Extract main content
        content_parts = []
        content_parts.append(f"# {info['title']}")
        content_parts.append(f"Bron: UWV werk.nl | Sector: {sector}")
        content_parts.append("")

        # Try to find the main content area
        main = soup.find("main") or soup.find("article") or soup.find("div", class_="content")
        if main:
            # Extract headings and paragraphs
            for elem in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
                text = elem.get_text(strip=True)
                if not text or len(text) < 5:
                    continue
                if elem.name.startswith("h"):
                    level = int(elem.name[1])
                    content_parts.append(f"\n{'#' * level} {text}")
                elif elem.name == "li":
                    content_parts.append(f"- {text}")
                else:
                    content_parts.append(text)

        content = "\n".join(content_parts)

        if len(content) < 100:
            logger.info("uwv_page_too_short", sector=sector, length=len(content))
            return None

        return self.make_document(
            title=info["title"],
            content=content,
            source_url=info["url"],
            sector=[sector],
            metadata={"page_length": len(content)},
        )

    async def _fetch_spanningsindicator(
        self, client: httpx.AsyncClient
    ) -> KnowledgeDocument | None:
        """
        Fetch the UWV Spanningsindicator overview.
        This shows labour market tension per sector and region.
        """
        url = "https://www.werk.nl/arbeidsmarktinformatie/dashboards/spanningsindicator"
        resp = await client.get(url)

        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        content_parts = [
            "# UWV Spanningsindicator — Arbeidsmarktkrapte Nederland",
            f"Bron: UWV werk.nl | Opgehaald: {datetime.now().strftime('%Y-%m-%d')}",
            "",
            "De Spanningsindicator van het UWV geeft per beroepsgroep en regio aan "
            "hoe krap of ruim de arbeidsmarkt is. De indicator loopt van 'ruim' (veel "
            "werkzoekenden per vacature) tot 'zeer krap' (weinig werkzoekenden per vacature).",
            "",
        ]

        # Extract any tables or data from the page
        main = soup.find("main") or soup
        for elem in main.find_all(["h2", "h3", "p", "li", "table"]):
            text = elem.get_text(strip=True)
            if text and len(text) > 10:
                if elem.name.startswith("h"):
                    content_parts.append(f"\n## {text}")
                elif elem.name == "li":
                    content_parts.append(f"- {text}")
                elif elem.name == "table":
                    content_parts.append(self._parse_table(elem))
                else:
                    content_parts.append(text)

        content = "\n".join(content_parts)

        return self.make_document(
            title="UWV Spanningsindicator — Arbeidsmarktkrapte Nederland",
            content=content,
            source_url=url,
            metadata={"type": "spanningsindicator"},
            expiry_days=14,
        )

    @staticmethod
    def _parse_table(table_elem) -> str:
        """Parse an HTML table to markdown."""
        rows = table_elem.find_all("tr")
        if not rows:
            return ""

        lines = []
        for i, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            cell_texts = [c.get_text(strip=True) for c in cells]
            lines.append("| " + " | ".join(cell_texts) + " |")
            if i == 0:
                lines.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")

        return "\n".join(lines)
