"""
Seed script — load initial knowledge base from existing ModellenWerk research.

Run once to bootstrap the knowledge base with:
- Sectorale analyse (8 sectoren × 5 dimensies)
- Organisatie analyse (40 organisaties)
- Workforce intelligence report

Usage: python -m app.pipeline.seed --data-dir /path/to/workspace
"""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import structlog

from app.core.logging import setup_logging
from app.core.database import init_pool, close_pool
from app.services.embedder import EmbeddingService
from app.models.knowledge import KnowledgeDocument, SourceType, KnowledgeCategory

logger = structlog.get_logger()


# Files to load and their knowledge base mappings
SEED_FILES = [
    {
        "filename": "MW_Sectorale_Analyse_8x5_Dimensies.md",
        "source_name": "ModellenWerk Sectorale Analyse",
        "title": "Sectorale Analyse — 8 sectoren × 5 dimensies",
        "source_type": SourceType.OWN_RESEARCH,
        "category": KnowledgeCategory.SECTORKENNIS,
        "layer": 2,
        "sector": None,  # cross-sector
    },
    {
        "filename": "MW_Organisatie_Analyse_40_Organisaties.md",
        "source_name": "ModellenWerk Organisatie Analyse",
        "title": "Organisatie Analyse — 40 toonaangevende Nederlandse organisaties",
        "source_type": SourceType.OWN_RESEARCH,
        "category": KnowledgeCategory.SECTORKENNIS,
        "layer": 2,
        "sector": None,
    },
    {
        "filename": "MW_Workforce_Intelligence_Report_2026.md",
        "source_name": "ModellenWerk Workforce Intelligence Report",
        "title": "Workforce Intelligence Report 2026 — Nederlandse Arbeidsmarkt",
        "source_type": SourceType.OWN_RESEARCH,
        "category": KnowledgeCategory.ARBEIDSMARKT,
        "layer": 1,
        "sector": None,
    },
    {
        "filename": "MW_Workforce_Agent_Training_Blueprint.md",
        "source_name": "ModellenWerk Training Blueprint",
        "title": "Workforce Agent Training Blueprint — 48 databronnen in 7 lagen",
        "source_type": SourceType.FRAMEWORK,
        "category": KnowledgeCategory.ADVIESFRAMEWORKS,
        "layer": 7,
        "sector": None,
    },
]


async def seed_knowledge_base(data_dir: str):
    """Load initial knowledge base from existing research files."""
    setup_logging()
    await init_pool()
    embedder = EmbeddingService()
    data_path = Path(data_dir)

    total_docs = 0
    total_chunks = 0

    for file_config in SEED_FILES:
        filepath = data_path / file_config["filename"]

        if not filepath.exists():
            logger.warning("seed_file_not_found", path=str(filepath))
            continue

        content = filepath.read_text(encoding="utf-8")
        logger.info(
            "seeding_file",
            filename=file_config["filename"],
            length=len(content),
        )

        doc = KnowledgeDocument(
            source_name=file_config["source_name"],
            source_url=None,
            source_type=file_config["source_type"],
            category=file_config["category"],
            layer=file_config["layer"],
            sector=file_config["sector"],
            title=file_config["title"],
            content=content,
            metadata={
                "seeded": True,
                "seed_date": datetime.now().isoformat(),
                "original_file": file_config["filename"],
            },
            source_date=datetime.now().date(),
        )

        doc_id, chunks = await embedder.process_document(doc)
        total_docs += 1
        total_chunks += len(chunks)

        logger.info(
            "file_seeded",
            filename=file_config["filename"],
            document_id=doc_id,
            chunks=len(chunks),
        )

    await close_pool()
    print(f"\nSeed complete: {total_docs} documents, {total_chunks} chunks embedded.")


def main():
    parser = argparse.ArgumentParser(description="Seed the knowledge base")
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Path to the Workspace directory with MW_*.md files",
    )
    args = parser.parse_args()
    asyncio.run(seed_knowledge_base(args.data_dir))


if __name__ == "__main__":
    main()
