"""Installeer de robotparameters per sector (migratie 006 plus data).

Waarom een eigen installer en niet run_migration() uit seed_organizations:
die splitst de SQL op ';' en gooit elk blok weg dat met '--' begint, waardoor
een statement met een commentaarregel erboven stilzwijgend verdwijnt. Hier
worden commentaarregels eerst gestript en pas daarna wordt er gesplitst.

Waarom niet via seed_sector_profiles(): die functie keert vroegtijdig terug
zodra er negen sectoren in de tabel staan, dus hij zou niets doen.

Idempotent: ADD COLUMN IF NOT EXISTS, DROP CONSTRAINT IF EXISTS en een UPDATE
per sector. Meermaals draaien is veilig.
"""

import json
from pathlib import Path

import structlog

from app.core.database import execute, fetch_one, fetch_all, get_connection

logger = structlog.get_logger()

WORTEL = Path(__file__).parent.parent.parent
MIGRATIE = WORTEL / "migrations" / "006_robot_parameters.sql"
DATA = WORTEL / "data" / "sector_profiles_robot.json"

VELDEN = (
    "robotrelevant_aandeel_pct",
    "robot_ondersteuning_pct",
    "robot_augmentatie_pct",
    "robot_vervanging_pct",
)


def _statements(sql: str) -> list[str]:
    """Strip commentaarregels, splits daarna pas op puntkomma."""
    schoon = "\n".join(
        r for r in sql.splitlines() if not r.strip().startswith("--")
    )
    return [s.strip() for s in schoon.split(";") if s.strip()]


async def install_robot_parameters() -> dict:
    if not MIGRATIE.exists():
        raise FileNotFoundError(f"Migratie ontbreekt: {MIGRATIE}")
    if not DATA.exists():
        raise FileNotFoundError(f"Datafile ontbreekt: {DATA}")

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    sectoren = payload["sector_profiles_robot"]

    # 1. Invariant vooraf toetsen. Beter hier falen dan op de CHECK-constraint.
    for s in sectoren:
        som = (
            (s.get("robot_ondersteuning_pct") or 0)
            + (s.get("robot_augmentatie_pct") or 0)
            + (s.get("robot_vervanging_pct") or 0)
        )
        grens = s.get("robotrelevant_aandeel_pct") or 100
        if som > grens:
            raise ValueError(
                f"{s['sector_slug']}: som {som} boven de bovengrens {grens}"
            )

    # 2. Schema
    ddl = _statements(MIGRATIE.read_text(encoding="utf-8"))
    uitgevoerd = 0
    async with get_connection() as conn:
        for stmt in ddl:
            await conn.execute(stmt)
            uitgevoerd += 1
    logger.info("robot_parameters_schema_klaar", statements=uitgevoerd)

    # 3. Data. UPDATE en geen INSERT: de negen rijen bestaan al.
    bijgewerkt, ontbrekend = 0, []
    async with get_connection() as conn:
        for s in sectoren:
            rij = await conn.fetchrow(
                "SELECT 1 FROM sector_profiles WHERE sector_slug = $1", s["sector_slug"]
            )
            if not rij:
                ontbrekend.append(s["sector_slug"])
                continue
            await conn.execute(
                """
                UPDATE sector_profiles SET
                    robotrelevant_aandeel_pct = $2,
                    robot_ondersteuning_pct   = $3,
                    robot_augmentatie_pct     = $4,
                    robot_vervanging_pct      = $5,
                    nea_fysiek_belastend_pct  = $6,
                    robot_params_herkomst     = $7::jsonb,
                    robot_params_peildatum    = $8::date,
                    robot_params_versie       = $9,
                    robot_params_onzekerheid  = $10,
                    updated_at                = CURRENT_TIMESTAMP
                WHERE sector_slug = $1
                """,
                s["sector_slug"],
                s["robotrelevant_aandeel_pct"],
                s["robot_ondersteuning_pct"],
                s["robot_augmentatie_pct"],
                s["robot_vervanging_pct"],
                s.get("nea_fysiek_belastend_pct"),
                json.dumps(s["robot_params_herkomst"], ensure_ascii=False),
                s["robot_params_peildatum"],
                s["robot_params_versie"],
                s.get("robot_params_onzekerheid"),
            )
            bijgewerkt += 1

    # 4. Controle achteraf
    gevuld = await fetch_one(
        "SELECT COUNT(*) AS n FROM sector_profiles WHERE robot_params_herkomst IS NOT NULL"
    )
    vreemd = await fetch_all(
        """
        SELECT DISTINCT trim(s) AS sector
        FROM documents, unnest(string_to_array(sector, ',')) AS s
        WHERE trim(s) <> ''
          AND trim(s) NOT IN ('overheid','ict','transport','energie','onderwijs',
                              'finance','zorg','bouw','industrie')
        """
    )

    resultaat = {
        "schema_statements": uitgevoerd,
        "sectoren_bijgewerkt": bijgewerkt,
        "sectoren_niet_gevonden": ontbrekend,
        "sectoren_met_herkomst": (gevuld or {}).get("n", 0),
        "versie": payload.get("versie"),
        "peildatum": payload.get("peildatum"),
        "afwijkende_sectorlabels_in_documents": [r["sector"] for r in (vreemd or [])],
    }
    logger.info("robot_parameters_geinstalleerd", **resultaat)
    return resultaat
