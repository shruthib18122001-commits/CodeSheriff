"""
Query-time LLM helpers used by app/api/query.py:
  - embed_text:    turn the user's question into a vector
  - search_chunks: pgvector cosine-similarity search scoped to one repo
  - ask_codebase:  build a grounded prompt from retrieved chunks, ask Gemini
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.code_chunk import CodeChunk

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM = 768  # must match CodeChunk.embedding's pgvector column
CHAT_MODEL = "gemini-flash-latest"

_client: Optional[genai.Client] = None


def _gemini() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def embed_text(text: str) -> list[float]:
    response = _gemini().models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text or " ",
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
    )
    return response.embeddings[0].values


def search_chunks(db: Session, repo_id, query_embedding: list[float], top_k: int = 8) -> list[CodeChunk]:
    """Nearest neighbors by cosine distance (pgvector's `<=>` operator), scoped to one repo."""
    return (
        db.query(CodeChunk)
        .filter(CodeChunk.repo_id == repo_id, CodeChunk.embedding.isnot(None))
        .order_by(CodeChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
        .all()
    )


THINKING_LEVELS = ("off", "low", "medium", "high")


def _resolve_thinking_level(override: Optional[str]) -> str:
    level = (override or settings.gemini_thinking_level).lower()
    if level not in THINKING_LEVELS:
        raise ValueError(f"Invalid thinking level: {level!r}")
    return level


def _thinking_config(level: str) -> types.ThinkingConfig:
    # gemini-flash-latest thinks by default, and thinking tokens are drawn
    # from the same max_output_tokens budget as the visible answer -- with
    # thinking on and too little headroom, the budget gets silently eaten
    # by reasoning and the response truncates before any real output (e.g.
    # mid-JSON for the architecture-map prompt). "off" is the safe default
    # for that reason; callers requesting a real level must also budget
    # extra max_tokens headroom (see ask_codebase).
    if level == "off":
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level=level)


def _generation_config(max_tokens: int, thinking_level: Optional[str] = None) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        thinking_config=_thinking_config(_resolve_thinking_level(thinking_level)),
    )


def raw_completion(prompt: str, max_tokens: int = 2000) -> str:
    """
    Generic single-turn completion used by non-Q&A features (architecture
    map, drift detection) that need a free-form or JSON response from
    Gemini rather than the grounded Q&A flow in ask_codebase.
    """
    response = _gemini().models.generate_content(
        model=CHAT_MODEL,
        contents=prompt,
        config=_generation_config(max_tokens),
    )
    return (response.text or "").strip()


def ask_codebase(
    question: str,
    chunks: list[CodeChunk],
    thinking_level: Optional[str] = None,
    attachments: Optional[list[dict]] = None,
) -> dict:
    """
    Builds a prompt grounded in the retrieved chunks (each labeled with
    file path + line range) plus any user-supplied attachments (screenshots,
    log files, etc.) and asks Gemini to answer using that context. Returns
    {"answer": str, "sources": [...]}.
    """
    attachments = attachments or []

    if not chunks and not attachments:
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
        "Use the code excerpts below, plus any attached files or images, "
        "to answer. Cite specific files and line numbers where relevant. "
        "If there isn't enough information to answer confidently, say so "
        "instead of guessing.\n\n"
        f"Question: {question}\n\n"
        "Code excerpts:\n\n" + "\n\n".join(context_blocks)
    )

    try:
        resolved_level = _resolve_thinking_level(thinking_level)
        # Thinking tokens eat into max_output_tokens too, so give extra
        # headroom whenever thinking is actually on -- otherwise a "high"
        # answer to a meaty question can burn the whole budget on reasoning
        # and come back empty (see _thinking_config).
        max_tokens = 1500 if resolved_level == "off" else 3000

        contents: list = [prompt]
        for a in attachments:
            contents.append(types.Part.from_bytes(data=base64.b64decode(a["data"]), mime_type=a["mime_type"]))

        response = _gemini().models.generate_content(
            model=CHAT_MODEL,
            contents=contents,
            config=_generation_config(max_tokens, resolved_level),
        )
        answer = (response.text or "").strip()
        if not answer:
            answer = "The model returned an empty response. Please try again."
    except Exception:
        logger.exception("Gemini call failed for question=%r", question)
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
