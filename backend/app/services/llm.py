"""
Query-time LLM helpers used by app/api/query.py:
  - embed_text:    turn the user's question into a vector
  - search_chunks: pgvector cosine-similarity search scoped to one repo
  - ask_codebase:  build a grounded prompt from retrieved chunks, ask Claude
"""
from __future__ import annotations

import logging
from typing import Optional

from anthropic import Anthropic
from openai import OpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "claude-sonnet-4-6"

_openai_client: Optional[OpenAI] = None
_anthropic_client: Optional[Anthropic] = None


def _openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def _anthropic() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


def embed_text(text: str) -> list[float]:
    response = _openai().embeddings.create(model=EMBEDDING_MODEL, input=text or " ")
    return response.data[0].embedding


def search_chunks(db: Session, repo_id, query_embedding: list[float], top_k: int = 8) -> list[CodeChunk]:
    """Nearest neighbors by cosine distance (pgvector's `<=>` operator), scoped to one repo."""
    return (
        db.query(CodeChunk)
        .filter(CodeChunk.repo_id == repo_id, CodeChunk.embedding.isnot(None))
        .order_by(CodeChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
        .all()
    )


def raw_completion(prompt: str, max_tokens: int = 2000) -> str:
    """
    Generic single-turn completion used by non-Q&A features (architecture
    map, drift detection) that need a free-form or JSON response from
    Claude rather than the grounded Q&A flow in ask_codebase.
    """
    response = _anthropic().messages.create(
        model=CHAT_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()


def ask_codebase(question: str, chunks: list[CodeChunk]) -> dict:
    """
    Builds a prompt grounded in the retrieved chunks (each labeled with
    file path + line range) and asks Claude to answer using only that
    context. Returns {"answer": str, "sources": [...]}.
    """
    if not chunks:
        return {
            "answer": (
                "I couldn't find any indexed code relevant to this question. "
                "Try rephrasing, or confirm the repo has finished indexing."
            ),
            "sources": [],
        }

    context_blocks = []
    for c in chunks:
        label = f"{c.file_path} (lines {c.start_line}-{c.end_line})"
        if c.symbol_name:
            label += f" — {c.chunk_type} `{c.symbol_name}`"
        context_blocks.append(f"### {label}\n```\n{c.content}\n```")

    prompt = (
        "You are a senior engineer answering questions about a codebase. "
        "Use ONLY the code excerpts below to answer. Cite specific files "
        "and line numbers in your answer where relevant. If the excerpts "
        "don't contain enough information to answer confidently, say so "
        "instead of guessing.\n\n"
        f"Question: {question}\n\n"
        "Code excerpts:\n\n" + "\n\n".join(context_blocks)
    )

    try:
        response = _anthropic().messages.create(
            model=CHAT_MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        if not answer:
            answer = "The model returned an empty response. Please try again."
    except Exception:
        logger.exception("Anthropic call failed for question=%r", question)
        answer = "The AI service is temporarily unavailable. Please try again shortly."

    sources = [
        {
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "symbol_name": c.symbol_name,
        }
        for c in chunks
    ]
    return {"answer": answer, "sources": sources}
