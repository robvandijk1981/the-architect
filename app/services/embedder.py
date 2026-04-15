"""Embedding pipeline — chunk documents and generate Voyage AI embeddings."""

import hashlib
import json
import re
from datetime import datetime

import voyageai
import structlog

from app.core.config import get_settings
from app.core.database import get_connection, fetch_all, vector_search as db_vector_search
from app.models.knowledge import KnowledgeDocument, KnowledgeChunk

logger = structlog.get_logger()


class EmbeddingService:
    """Handles document chunking and Voyage AI embedding generation."""

    def __init__(self):
        settings = get_settings()
        self.client = voyageai.Client(api_key=settings.voyage_api_key)
        self.model = settings.embedding_model
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap
        self.dimensions = settings.embedding_dimensions

    # ============================================
    # Public API
    # ============================================

    async def embed_query(self, query: str) -> list[float]:
        """Embed a search query (uses query-specific embedding)."""
        result = self.client.embed(
            texts=[query],
            model=self.model,
            input_type="query",
        )
        return result.embeddings[0]

    async def process_document(self, doc: KnowledgeDocument) -> tuple[str, list[KnowledgeChunk]]:
        """
        Full pipeline: store document → chunk → embed → store chunks.
        Returns (document_id, chunks).
        """
        content_hash = self._hash_content(doc.content)

        async with get_connection() as conn:
            # Check if document already exists with same content
            existing = await conn.fetchrow(
                """SELECT id, content_hash FROM knowledge_documents
                   WHERE source_name = $1 AND title = $2 AND is_current = true""",
                doc.source_name, doc.title,
            )

            if existing and existing["content_hash"] == content_hash:
                logger.info("document_unchanged", source=doc.source_name, title=doc.title)
                return str(existing["id"]), []

            # If exists with different content, mark old as not current
            if existing:
                old_id = existing["id"]
                await conn.execute(
                    "UPDATE knowledge_documents SET is_current = false WHERE id = $1", old_id
                )
                await conn.execute(
                    "DELETE FROM knowledge_embeddings WHERE document_id = $1", old_id
                )
                logger.info("document_superseded", old_id=str(old_id), source=doc.source_name)

            # Insert new document
            row = await conn.fetchrow(
                """INSERT INTO knowledge_documents
                   (source_name, source_url, source_type, category, layer, sector,
                    title, content, metadata, source_date, expires_at, content_hash, is_current)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, true)
                   RETURNING id""",
                doc.source_name,
                doc.source_url,
                doc.source_type.value,
                doc.category.value,
                doc.layer,
                doc.sector,
                doc.title,
                doc.content,
                json.dumps(doc.metadata),
                doc.source_date,
                doc.expires_at,
                content_hash,
            )
            document_id = str(row["id"])

            # Chunk and embed
            chunks = self._smart_chunk(doc.content, doc.source_type.value)
            if not chunks:
                logger.warning("no_chunks_generated", document_id=document_id)
                return document_id, []

            embeddings = self._embed_batch(chunks)

            # Store chunks with embeddings
            knowledge_chunks = []
            for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_meta = {
                    "source": doc.source_name,
                    "date": doc.source_date.isoformat() if doc.source_date else None,
                    "sector": doc.sector,
                    "layer": doc.layer,
                    "category": doc.category.value,
                }
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                await conn.execute(
                    """INSERT INTO knowledge_embeddings
                       (document_id, chunk_index, chunk_text, embedding, metadata)
                       VALUES ($1::uuid, $2, $3, $4::vector(1024), $5)""",
                    row["id"], i, chunk_text, embedding_str, json.dumps(chunk_meta),
                )
                knowledge_chunks.append(KnowledgeChunk(
                    document_id=document_id,
                    chunk_index=i,
                    chunk_text=chunk_text,
                    embedding=embedding,
                    metadata=chunk_meta,
                ))

            # Log to changelog
            await conn.execute(
                """INSERT INTO knowledge_changelog (action, document_id, summary, source_job, details)
                   VALUES ($1, $2::uuid, $3, $4, $5)""",
                "added" if not existing else "updated",
                row["id"],
                f"{doc.source_name}: {doc.title} ({len(chunks)} chunks)",
                "embedding_pipeline",
                json.dumps({"chunks": len(chunks), "content_length": len(doc.content)}),
            )

        logger.info(
            "document_processed",
            document_id=document_id,
            source=doc.source_name,
            chunks=len(chunks),
        )
        return document_id, knowledge_chunks

    async def search(
        self,
        query: str,
        match_count: int = 10,
        sector: str | None = None,
        layer: int | None = None,
        category: str | None = None,
        threshold: float = 0.7,
    ) -> list[dict]:
        """Search the knowledge base using semantic similarity."""
        query_embedding = await self.embed_query(query)
        return await db_vector_search(
            query_embedding=query_embedding,
            match_count=match_count,
            filter_sector=sector,
            filter_layer=layer,
            filter_category=category,
            similarity_threshold=threshold,
        )

    async def hybrid_search(
        self,
        query: str,
        match_count: int = 10,
        sector: str | None = None,
        layer: int | None = None,
        category: str | None = None,
        threshold: float = 0.30,
        alpha: float = 0.7,
    ) -> list[dict]:
        """
        Hybrid retrieval: dense (cosine) + BM25 (ts_rank) combined.

        Phase 4c. Calls the hybrid_search_chunks() SQL function from
        migration 007 (must be installed first via
        POST /admin/install-hybrid-search).

        Args:
            query: User query (used both for embedding and BM25 lexical match).
            match_count: Number of chunks to return after blending.
            sector / layer / category: Optional metadata filters.
            threshold: Minimum dense similarity to consider a candidate (0.30).
            alpha: Weight of dense score in the blend. 1.0 = pure dense
                   (= regular search), 0.0 = pure BM25, 0.7 = strong dense
                   with BM25 boost (default).

        Returns:
            List of chunk dicts with `similarity`, `bm25_score`, and
            `hybrid_score` populated. Sorted desc by hybrid_score.

        Falls back to dense-only `search()` if the SQL function is missing
        (e.g. migration not yet applied).
        """
        query_embedding = await self.embed_query(query)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        try:
            rows = await fetch_all(
                """SELECT * FROM hybrid_search_chunks(
                       $1, $2::vector(1024), $3, $4, $5, $6, $7, $8
                   )""",
                query,
                embedding_str,
                match_count,
                threshold,
                alpha,
                sector,
                layer,
                category,
            )
            logger.info(
                "hybrid_search_executed",
                query_len=len(query),
                returned=len(rows),
                alpha=alpha,
                threshold=threshold,
                sector=sector,
            )
            return rows
        except Exception as e:
            logger.warning(
                "hybrid_search_failed_fallback_to_dense",
                error=str(e),
                hint="install hybrid_search_chunks via POST /admin/install-hybrid-search",
            )
            return await db_vector_search(
                query_embedding=query_embedding,
                match_count=match_count,
                filter_sector=sector,
                filter_layer=layer,
                filter_category=category,
                similarity_threshold=threshold,
            )

    async def rerank_chunks(
        self,
        query: str,
        chunks: list[dict],
        top_k: int = 10,
        model: str = "rerank-2",
    ) -> list[dict]:
        """
        Rerank retrieved chunks using Voyage rerank-2 for improved precision.
        Returns top_k chunks enriched with rerank_score, sorted desc by relevance.
        Falls back to original order (truncated to top_k) if rerank fails.
        """
        if not chunks:
            return []

        documents = [c.get("chunk_text", "") for c in chunks]
        try:
            result = self.client.rerank(
                query=query,
                documents=documents,
                model=model,
                top_k=min(top_k, len(chunks)),
            )
        except Exception as e:
            logger.warning(
                "rerank_failed_fallback_to_original",
                error=str(e),
                chunks=len(chunks),
            )
            return chunks[:top_k]

        reranked = []
        for r in result.results:
            chunk = dict(chunks[r.index])
            chunk["rerank_score"] = r.relevance_score
            reranked.append(chunk)

        logger.info(
            "chunks_reranked",
            model=model,
            input_chunks=len(chunks),
            output_chunks=len(reranked),
            top_rerank_score=reranked[0].get("rerank_score") if reranked else None,
        )
        return reranked

    # ============================================
    # Chunking Strategies
    # ============================================

    def _smart_chunk(self, text: str, source_type: str) -> list[str]:
        """
        Smart chunking based on document type:
        - api_data: per table/dataset (don't split small datasets)
        - report: per section/paragraph
        - law: per article
        - framework: per concept
        - own_research: per organization/section
        """
        if source_type == "api_data":
            return self._chunk_structured_data(text)
        elif source_type == "law":
            return self._chunk_by_articles(text)
        else:
            return self._chunk_by_paragraphs(text)

    def _chunk_by_paragraphs(self, text: str) -> list[str]:
        """Default chunking: split on paragraph boundaries, respecting size limits."""
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # If paragraph itself is too large, split it
                if len(para) > self.chunk_size:
                    chunks.extend(self._split_large_text(para))
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk.strip())

        return [c for c in chunks if len(c) > 20]  # skip tiny fragments

    def _chunk_structured_data(self, text: str) -> list[str]:
        """For API/statistical data: keep tables together, split large datasets."""
        sections = re.split(r'\n(?=#{1,3}\s)', text)
        chunks = []

        for section in sections:
            section = section.strip()
            if not section:
                continue
            if len(section) <= self.chunk_size * 2:
                chunks.append(section)
            else:
                chunks.extend(self._chunk_by_paragraphs(section))

        return [c for c in chunks if len(c) > 20]

    def _chunk_by_articles(self, text: str) -> list[str]:
        """For legal text: split on article boundaries."""
        articles = re.split(r'\n(?=(?:Artikel|Art\.)\s+\d+)', text)
        chunks = []

        for article in articles:
            article = article.strip()
            if not article:
                continue
            if len(article) <= self.chunk_size * 2:
                chunks.append(article)
            else:
                chunks.extend(self._chunk_by_paragraphs(article))

        return [c for c in chunks if len(c) > 20]

    def _split_large_text(self, text: str) -> list[str]:
        """Split oversized text with overlap."""
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk_words = words[i:i + self.chunk_size // 5]  # rough word count
            chunks.append(" ".join(chunk_words))
            i += (self.chunk_size // 5) - (self.chunk_overlap // 5)
        return chunks

    # ============================================
    # Embedding
    # ============================================

    def _embed_batch(self, texts: list[str], batch_size: int = 128) -> list[list[float]]:
        """Embed texts in batches (Voyage AI limit)."""
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            result = self.client.embed(
                texts=batch,
                model=self.model,
                input_type="document",
            )
            all_embeddings.extend(result.embeddings)
            logger.debug("batch_embedded", batch_num=i // batch_size + 1, size=len(batch))

        return all_embeddings

    # ============================================
    # Helpers
    # ============================================

    @staticmethod
    def _hash_content(content: str) -> str:
        """SHA-256 hash for diff detection."""
        return hashlib.sha256(content.encode()).hexdigest()
