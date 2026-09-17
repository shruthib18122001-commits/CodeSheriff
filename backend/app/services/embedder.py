"""
Batch-embeds CodeChunk rows for a repo, then builds the pgvector HNSW
index. Called from ingestion.py after parsing completes. The index is
deliberately created AFTER embeddings are populated -- building it
against an empty/partial column is wasted work that gets redone as
rows fill in, per the project's ingestion-order constraint.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import sqlalchemy
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM = 768  # must match CodeChunk.embedding's pgvector column
BATCH_SIZE = 100

# The free tier allows very few embed_content requests per minute; a repo
# with more than one batch's worth of chunks reliably hits 429s otherwise.
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RETRY_DELAY_SECONDS = 30

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
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
    # The embeddings API rejects empty strings; blank chunks (rare, but
    # possible for near-empty files) get a single space.
    safe_texts = [t if t and t.strip() else " " for t in texts]
    client = _get_client()
    config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)

    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = client.models.embed_content(model=EMBEDDING_MODEL, contents=safe_texts, config=config)
            return [item.values for item in response.embeddings]
        except genai_errors.ClientError as e:
            if e.code != 429 or attempt == MAX_RATE_LIMIT_RETRIES:
                raise
            delay = _retry_delay_seconds(e) or DEFAULT_RETRY_DELAY_SECONDS
            logger.warning(
                "Gemini embedding rate-limited, retrying in %ss (attempt %d/%d)",
                delay, attempt, MAX_RATE_LIMIT_RETRIES,
            )
            time.sleep(delay)


def _retry_delay_seconds(error: genai_errors.ClientError) -> Optional[float]:
    """Pulls the server-suggested retry delay (e.g. "38s") out of a 429's details, if present."""
    try:
        for detail in error.details.get("error", {}).get("details", []):
            if detail.get("@type", "").endswith("RetryInfo"):
                return float(detail["retryDelay"].rstrip("s"))
    except (AttributeError, KeyError, ValueError, TypeError):
        pass
    return None


def _create_hnsw_index(db: Session) -> None:
    db.execute(
        sqlalchemy.text(
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding "
            "ON code_chunks USING hnsw (embedding vector_cosine_ops)"
        )
    )
    db.commit()
