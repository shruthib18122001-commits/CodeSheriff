"""
Batch-embeds CodeChunk rows for a repo, then builds the pgvector HNSW
index. Called from ingestion.py after parsing completes. The index is
deliberately created AFTER embeddings are populated -- building it
against an empty/partial column is wasted work that gets redone as
rows fill in, per the project's ingestion-order constraint.
"""
from __future__ import annotations

import logging
from typing import Optional

import sqlalchemy
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def embed_repo_chunks(db: Session, repo_id) -> None:
    """
    Embeds every CodeChunk row for repo_id where embedding IS NULL, in
    batches of BATCH_SIZE, committing after each batch so partial
    progress survives a mid-run crash. Then (re)builds the HNSW index.
    """
    pending = (
        db.query(CodeChunk)
        .filter(CodeChunk.repo_id == repo_id, CodeChunk.embedding.is_(None))
        .all()
    )
    if not pending:
        return

    for i in range(0, len(pending), BATCH_SIZE):
        batch = pending[i : i + BATCH_SIZE]
        try:
            vectors = _embed_batch([c.content for c in batch])
        except Exception:
            logger.exception(
                "Embedding batch failed (chunks %d-%d of repo %s); skipping batch",
                i, i + len(batch), repo_id,
            )
            continue
        for chunk, vector in zip(batch, vectors):
            chunk.embedding = vector
        db.commit()

    _create_hnsw_index(db)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    # The OpenAI embeddings API rejects empty strings; blank chunks
    # (rare, but possible for near-empty files) get a single space.
    safe_texts = [t if t and t.strip() else " " for t in texts]
    client = _get_client()
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=safe_texts)
    return [item.embedding for item in response.data]


def _create_hnsw_index(db: Session) -> None:
    db.execute(
        sqlalchemy.text(
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding "
            "ON code_chunks USING hnsw (embedding vector_cosine_ops)"
        )
    )
    db.commit()
