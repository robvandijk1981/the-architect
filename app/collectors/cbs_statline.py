"""CBS StatLine collector — Dutch national statistics via OData API."""

from datetime import datetime
import httpx
import structlog

from app.collectors.base import BaseCollector
from app.models.knowledge import KnowledgeDocument, SourceType, KnowledgeCategory

logger = structlog.get_logger()


class CBSStatLineCollector(BaseCollector):
    """
    Collects labour market data from CBS (Centraal Bureau voor de Statistiek)
    via the open OData v4 API.

    API docs: https://www.cbs.nl/nl-nl/onze-diensten/open-data/open-data-v4
    Catalog: https://opendata.cbs.nl/ODataCatalog/Tables?$format=json
    """

    name = "CBS StatLine"
    description = "Arbeidsmarktdata van het CBS via OData API"
    source_type = SourceType.API_DATA
    category = KnowledgeCategory.ARBEIDSMARKT
    layer = 1
    default_expiry_days = 30

    BASE_URL = "https://odata4.cbs.nl/CBS"

    # Key tables for workforce intelligence
    TABLES = {
        "beroepsbevolking": {
            "id": "85275NED",
            "title": "Arbeidsdeelname en werkloosheid per maand",
            "description": "Beroepsbevolking, werkzame en werkloze beroepsbevolking, seizoengecorrigeerd",
        },
        "vacatures": {
            "id": "80472NED",
            "title": "Vacatures per kwartaal naar bedrijfstak",
            "description": "Ontstaan, openstaand en vervuld vacatures per sector",
        },
        "cao_lonen": {
            "id": "83131NED",
            "title": "CAO-lonen, contractuele loonkosten en arbeidsduur",
            "description": "Indexcijfers CAO-lonen per bedrijfstak",
        },
        "ziekteverzuim": {
            "id": "83055NED",
            "title": "Ziekteverzuim volgens werknemers",
            "description": "Verzuimpercentage per bedrijfstak en geslacht",
        },
        "banen_werknemers": {
            "id": "85256NED",
            "title": "Banen van werknemers naar bedrijfstak",
            "description": "Aantal banen, arbeidsvolume, lonen per bedrijfstak",
        },
        "bedrijven_grootte": {
            "id": "81588NED",
            "title": "Bedrijven naar bedrijfstak en grootteklasse",
            "description": "Aantal bedrijven en werkzame personen per sector en grootteklasse",
        },
    }

    # Sector mapping: CBS bedrijfstak → our sector slugs
    SECTOR_MAP = {
        "Q Gezondheids- en welzijnszorg": ["zorg"],
        "F Bouwnijverheid": ["bouw"],
        "C Industrie": ["techniek"],
        "P Onderwijs": ["onderwijs"],
        "O Openbaar bestuur": ["overheid"],
        "K Financiële dienstverlening": ["financieel"],
        "G Handel": ["retail"],
        "H Vervoer en opslag": ["transport"],
    }

    async def collect(self) -> list[KnowledgeDocument]:
        docs = []
        async with httpx.AsyncClient(timeout=30) as client:
            for key, table_info in self.TABLES.items():
                try:
                    doc = await self._fetch_table(client, key, table_info)
                    if doc:
                        docs.append(doc)
                except Exception as e:
                    logger.warning(
                        "cbs_table_fetch_failed",
                        table=key,
                        error=str(e),
                    )
        return docs

    async def _fetch_table(
        self, client: httpx.AsyncClient, key: str, table_info: dict
    ) -> KnowledgeDocument | None:
        """Fetch a single CBS table and convert to KnowledgeDocument."""
        table_id = table_info["id"]

        # Fetch metadata
        meta_url = f"{self.BASE_URL}/{table_id}"
        meta_resp = await client.get(meta_url, params={"$format": "json"})
        meta_resp.raise_for_status()

        # Fetch properties (column definitions)
        props_url = f"{self.BASE_URL}/{table_id}/Properties"
        props_resp = await client.get(props_url, params={"$format": "json"})

        # Fetch most recent observations (last 20 rows for context)
        obs_url = f"{self.BASE_URL}/{table_id}/Observations"
        obs_resp = await client.get(
            obs_url,
            params={
                "$format": "json",
                "$orderby": "Id desc",
                "$top": 50,
            },
        )
        obs_resp.raise_for_status()
        observations = obs_resp.json().get("value", [])

        if not observations:
            logger.info("cbs_table_empty", table=key)
            return None

        # Format as readable text
        content = self._format_observations(key, table_info, observations)

        # Determine last update
        modified = meta_resp.json().get("Modified")
        source_date = datetime.fromisoformat(modified) if modified else datetime.now()

        return self.make_document(
            title=f"CBS {table_info['title']}",
            content=content,
            source_url=f"https://opendata.cbs.nl/statline/#/CBS/nl/dataset/{table_id}",
            source_date=source_date,
            metadata={
                "table_id": table_id,
                "key": key,
                "observations_count": len(observations),
            },
        )

    def _format_observations(self, key: str, table_info: dict, observations: list) -> str:
        """Format CBS observations as readable text for embedding."""
        lines = [
            f"# CBS StatLine: {table_info['title']}",
            f"Beschrijving: {table_info['description']}",
            f"Tabel-ID: {table_info['id']}",
            "",
        ]

        if not observations:
            lines.append("Geen recente data beschikbaar.")
            return "\n".join(lines)

        # Get column names from first observation
        columns = [k for k in observations[0].keys() if k != "Id"]

        # Format as text table
        lines.append("## Recente data")
        lines.append("")

        for obs in observations[:30]:  # limit for chunk size
            row_parts = []
            for col in columns:
                val = obs.get(col)
                if val is not None:
                    row_parts.append(f"{col}: {val}")
            if row_parts:
                lines.append("- " + " | ".join(row_parts))

        # Add sector mapping context
        lines.append("")
        lines.append("## Sectorindeling")
        for cbs_sector, our_sectors in self.SECTOR_MAP.items():
            lines.append(f"- {cbs_sector} → {', '.join(our_sectors)}")

        return "\n".join(lines)
