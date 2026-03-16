"""
Pipeline Orchestrator — coordinates weekly knowledge base updates.

This is the main entry point for the scheduled weekly job.
Run manually: python -m app.pipeline.orchestrator
Scheduled: Railway cron job, every Monday at 07:00 CET
"""

import asyncio
from datetime import datetime
import structlog

from app.core.config import get_settings
from app.core.database import init_pool, close_pool, fetch_all, execute, execute_returning, get_connection
from app.core.logging import setup_logging
from app.services.embedder import EmbeddingService
from app.collectors.cbs_statline import CBSStatLineCollector
from app.collectors.uwv_arbeidsmarkt import UWVArbeidsmarktCollector
from app.collectors.azw_monitor import AZWMonitorCollector

logger = structlog.get_logger()


# Registry of all available collectors
COLLECTORS = [
    CBSStatLineCollector(),
    UWVArbeidsmarktCollector(),
    AZWMonitorCollector(),
    # Future collectors:
    # TechniekpactCollector(),
    # EIBBouwCollector(),
    # ROAPrognoseCollector(),
    # CPBEconomieCollector(),
    # AWVNCAOCollector(),
    # KvKOpenDataCollector(),
    # JaarverslagCollector(),
    # NewsMonitorCollector(),
]


class PipelineOrchestrator:
    """Orchestrates the full weekly knowledge base update pipeline."""

    def __init__(self):
        self.embedder = EmbeddingService()
        self.stats = {
            "started_at": None,
            "collectors_run": 0,
            "collectors_failed": 0,
            "documents_new": 0,
            "documents_updated": 0,
            "documents_unchanged": 0,
            "chunks_created": 0,
            "errors": [],
        }

    async def run(self, collectors: list | None = None):
        """
        Execute the full update pipeline:
        1. Run all collectors (parallel)
        2. Process new/changed documents (embed + store)
        3. Check for expired documents
        4. Update sector intelligence
        5. Generate report
        """
        self.stats["started_at"] = datetime.now().isoformat()
        active_collectors = collectors or COLLECTORS

        logger.info(
            "pipeline_started",
            collectors=len(active_collectors),
            collector_names=[c.name for c in active_collectors],
        )

        # ── Step 1: Run all collectors in parallel ──
        logger.info("step_1_collecting", count=len(active_collectors))
        all_docs = []

        tasks = [c.safe_collect() for c in active_collectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for collector, result in zip(active_collectors, results):
            if isinstance(result, Exception):
                self.stats["collectors_failed"] += 1
                self.stats["errors"].append(f"{collector.name}: {str(result)}")
                logger.error("collector_exception", collector=collector.name, error=str(result))
            else:
                self.stats["collectors_run"] += 1
                all_docs.extend(result)
                logger.info("collector_result", collector=collector.name, documents=len(result))

        logger.info("step_1_complete", total_documents=len(all_docs))

        # ── Step 2: Process documents (embed + store) ──
        logger.info("step_2_embedding", documents=len(all_docs))

        for doc in all_docs:
            try:
                doc_id, chunks = await self.embedder.process_document(doc)
                if chunks:
                    self.stats["documents_new"] += 1
                    self.stats["chunks_created"] += len(chunks)
                else:
                    self.stats["documents_unchanged"] += 1
            except Exception as e:
                self.stats["errors"].append(f"Embed {doc.title}: {str(e)}")
                logger.error("embedding_failed", document=doc.title, error=str(e))

        logger.info(
            "step_2_complete",
            new=self.stats["documents_new"],
            unchanged=self.stats["documents_unchanged"],
            chunks=self.stats["chunks_created"],
        )

        # ── Step 3: Check for expired documents ──
        logger.info("step_3_expiry_check")
        expired = await self._check_expired_documents()
        logger.info("step_3_complete", expired=expired)

        # ── Step 4: Update sector intelligence ──
        logger.info("step_4_sector_intelligence")
        # TODO: Implement sector benchmark recalculation
        # This will aggregate new data into sector_intelligence table

        # ── Step 5: Generate report ──
        report = self._generate_report()
        logger.info("pipeline_complete", report=report)

        # Log to changelog
        import json
        await execute(
            """INSERT INTO knowledge_changelog (action, summary, source_job, details)
               VALUES ($1, $2, $3, $4)""",
            "refreshed",
            f"Weekly update: {self.stats['documents_new']} new, "
            f"{self.stats['documents_unchanged']} unchanged, "
            f"{self.stats['chunks_created']} chunks created",
            "weekly_update",
            json.dumps(self.stats),
        )

        return report

    async def _check_expired_documents(self) -> int:
        """Find and flag expired documents."""
        expired_docs = await fetch_all(
            """SELECT id, source_name, title, expires_at FROM knowledge_documents
               WHERE is_current = true AND expires_at < now()"""
        )

        for doc in expired_docs:
            logger.warning(
                "document_expired",
                source=doc["source_name"],
                title=doc["title"],
                expired_at=str(doc["expires_at"]),
            )
            await execute(
                """INSERT INTO knowledge_changelog (action, document_id, summary, source_job)
                   VALUES ($1, $2, $3, $4)""",
                "expired", doc["id"],
                f"Expired: {doc['source_name']} — {doc['title']}",
                "weekly_update",
            )

        return len(expired_docs)

    def _generate_report(self) -> dict:
        """Generate a summary report of the pipeline run."""
        return {
            "started_at": self.stats["started_at"],
            "completed_at": datetime.now().isoformat(),
            "summary": {
                "collectors_run": self.stats["collectors_run"],
                "collectors_failed": self.stats["collectors_failed"],
                "documents_new": self.stats["documents_new"],
                "documents_updated": self.stats["documents_updated"],
                "documents_unchanged": self.stats["documents_unchanged"],
                "chunks_created": self.stats["chunks_created"],
            },
            "errors": self.stats["errors"],
            "success": self.stats["collectors_failed"] == 0 and len(self.stats["errors"]) == 0,
        }


async def main():
    """CLI entry point for manual pipeline runs."""
    setup_logging()
    logger.info("manual_pipeline_run_started")

    # Initialize database pool for standalone execution
    await init_pool()

    orchestrator = PipelineOrchestrator()
    report = await orchestrator.run()

    # Clean up
    await close_pool()

    print("\n" + "=" * 60)
    print("Pipeline Report")
    print("=" * 60)
    print(f"Collectors: {report['summary']['collectors_run']} succeeded, "
          f"{report['summary']['collectors_failed']} failed")
    print(f"Documents: {report['summary']['documents_new']} new, "
          f"{report['summary']['documents_unchanged']} unchanged")
    print(f"Chunks: {report['summary']['chunks_created']} created")
    if report["errors"]:
        print(f"\nErrors ({len(report['errors'])}):")
        for err in report["errors"]:
            print(f"  - {err}")
    print(f"\nSuccess: {'✓' if report['success'] else '✗'}")


if __name__ == "__main__":
    asyncio.run(main())
