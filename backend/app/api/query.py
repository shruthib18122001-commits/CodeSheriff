import base64
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.query_history import QueryHistory
from app.models.repo import IndexStatus, Repo
from app.models.user import User
from app.services.billing import check_query_limit
from app.services.llm import ask_codebase, embed_text, search_chunks

router = APIRouter()

# Comfortably under Gemini's ~20MB inline-request ceiling once base64 overhead
# (~4/3x) and the rest of the prompt are accounted for.
MAX_ATTACHMENTS_BYTES = 15 * 1024 * 1024


class Attachment(BaseModel):
    filename: str
    mime_type: str
    data: str  # base64-encoded file contents


class AskRequest(BaseModel):
    repo_id: uuid.UUID
    question: str
    # None = use the server-configured default (GEMINI_THINKING_LEVEL).
    thinking_level: Optional[Literal["low", "medium", "high"]] = None
    attachments: list[Attachment] = []


class SourceResponse(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    symbol_name: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceResponse]


@router.post("/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    1. Enforce the plan's monthly query limit.
    2. Verify the repo belongs to the caller and has finished indexing.
    3. Embed the question, retrieve the top-k relevant chunks, ask the LLM.
    4. Record usage (queries_this_month) and persist to query history.
    """
    check_query_limit(current_user)

    repo = (
        db.query(Repo)
        .filter(Repo.id == payload.repo_id, Repo.owner_id == current_user.id)
        .first()
    )
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    if repo.index_status != IndexStatus.ready:
        raise HTTPException(
            status_code=409,
            detail=f"Repo is not ready yet (status: {repo.index_status.value}). Try again once indexing completes.",
        )

    if not payload.question or not payload.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    total_bytes = 0
    for a in payload.attachments:
        try:
            total_bytes += len(base64.b64decode(a.data, validate=True))
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"Attachment '{a.filename}' is not valid base64 data")
    if total_bytes > MAX_ATTACHMENTS_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Attachments too large ({total_bytes // 1024}KB); limit is {MAX_ATTACHMENTS_BYTES // 1024}KB.",
        )

    query_embedding = embed_text(payload.question)
    chunks = search_chunks(db, repo.id, query_embedding, top_k=8)
    result = ask_codebase(
        payload.question,
        chunks,
        thinking_level=payload.thinking_level,
        attachments=[a.model_dump() for a in payload.attachments],
    )

    current_user.queries_this_month += 1

    history = QueryHistory(
        user_id=current_user.id,
        repo_id=repo.id,
        question=payload.question,
        answer=result["answer"],
        sources=result["sources"],
    )
    db.add(history)
    db.commit()

    return result
