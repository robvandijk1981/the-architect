"""Base collector class — all collectors inherit from this."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import structlog

from app.models.knowledge import KnowledgeDocument, SourceType, KnowledgeCategory

logger = structlog.get_logger()


class BaseCollector(ABC):
    """Abstract base for all data collectors."""

    name: str = "base"
    description: str = ""
    source_type: SourceType = SourceType.API_DATA
    category: KnowledgeCategory = KnowledgeCategory.ARBEIDSMARKT
    layer: int = 1
    default_expiry_days: int = 30

    @abstractmethod
    async def collect(self) -> list[KnowledgeDocument]:
        """
        Fetch data from the source and return KnowledgeDocument objects.
        Each collector must implement this method.
        """
        ...

    def make_document(
        self,
        title: str,
        content: str,
        source_url: str | None = None,
        sector: list[str] | None = None,
        source_date: datetime | None = None,
        metadata: dict | None = None,
        expiry_days: int | None = None,
    ) -> KnowledgeDocument:
        """Helper to create a KnowledgeDocument with standard fields."""
        return KnowledgeDocument(
            source_name=self.name,
            source_url=source_url,
            source_type=self.source_type,
            category=self.category,
            layer=self.layer,
            sector=sector,
            title=title,
            content=content,
            metadata=metadata or {},
            source_date=source_date.date() if source_date else datetime.now().date(),
            expires_at=datetime.now() + timedelta(days=expiry_days or self.default_expiry_days),
        )

    async def safe_collect(self) -> list[KnowledgeDocument]:
        """Wrapper with error handling and logging."""
        try:
            logger.info("collector_started", collector=self.name)
            docs = await self.collect()
            logger.info("collector_completed", collector=self.name, documents=len(docs))
            return docs
        except Exception as e:
            logger.error("collector_failed", collector=self.name, error=str(e))
            return []
