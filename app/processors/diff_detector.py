"""Diff detector — compare new data with previous versions to detect changes."""

import hashlib
import structlog

from app.core.database import fetch_one

logger = structlog.get_logger()


class DiffDetector:
    """Detects significant changes between old and new versions of documents."""

    async def has_changed(self, source_name: str, title: str, new_content: str) -> bool:
        """Check if content has changed compared to the stored version."""
        new_hash = hashlib.sha256(new_content.encode()).hexdigest()

        result = await fetch_one(
            """SELECT content_hash FROM knowledge_documents
               WHERE source_name = $1 AND title = $2 AND is_current = true
               LIMIT 1""",
            source_name, title,
        )

        if not result:
            return True  # New document

        return result.get("content_hash") != new_hash

    async def detect_contradictions(
        self, new_content: str, sector: str | None = None
    ) -> list[dict]:
        """
        Detect potential contradictions between new data and existing knowledge.

        This is a placeholder for a more sophisticated contradiction detection
        system that could use Claude to compare claims.
        """
        # TODO: Implement Claude-based contradiction detection
        logger.info("contradiction_check", sector=sector)
        return []
