"""Pydantic models for the knowledge base."""

from pydantic import BaseModel, Field
from datetime import date, datetime
from enum import Enum


class SourceType(str, Enum):
    API_DATA = "api_data"
    REPORT = "report"
    LAW = "law"
    FRAMEWORK = "framework"
    OWN_RESEARCH = "own_research"
    SECTOR_MONITOR = "sector_monitor"
    NEWS = "news"


class KnowledgeCategory(str, Enum):
    ARBEIDSMARKT = "arbeidsmarkt"
    SECTORKENNIS = "sectorkennis"
    REGELGEVING = "regelgeving"
    INTERVENTIES = "interventies"
    INTERNATIONAAL = "internationaal"
    BUSINESS_CASE = "business_case"
    ADVIESFRAMEWORKS = "adviesframeworks"


class KnowledgeDocument(BaseModel):
    """A document in the knowledge base."""

    source_name: str
    source_url: str | None = None
    source_type: SourceType
    category: KnowledgeCategory
    layer: int = Field(ge=1, le=7)
    sector: list[str] | None = None
    title: str
    content: str
    metadata: dict = Field(default_factory=dict)
    source_date: date | None = None
    expires_at: datetime | None = None


class KnowledgeDocumentDB(KnowledgeDocument):
    """Document as stored in the database."""

    id: str
    is_current: bool = True
    content_hash: str | None = None
    fetched_at: datetime
    created_at: datetime
    updated_at: datetime


class KnowledgeChunk(BaseModel):
    """A chunk of a document with its embedding."""

    document_id: str
    chunk_index: int
    chunk_text: str
    embedding: list[float]
    metadata: dict = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    """A chunk returned from vector search, with similarity score."""

    id: str
    document_id: str
    chunk_text: str
    chunk_index: int
    similarity: float
    source_name: str
    source_url: str | None = None
    source_type: str
    category: str
    layer: int
    sector: list[str] | None = None
    source_date: date | None = None
    metadata: dict = Field(default_factory=dict)


class Citation(BaseModel):
    """A source citation for grounding AI responses."""

    source_name: str
    source_url: str | None = None
    source_date: date | None = None
    relevance: float = 0.0
    excerpt: str | None = None
