import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.code_chunk import CodeChunk
from app.models.query_history import QueryHistory
from app.models.repo import IndexStatus, Repo
from app.models.user import User
from app.services.billing import check_repo_limit
from app.services.ingestion import enqueue_ingestion, ingestion_queue
from app.services.llm import raw_completion

logger = logging.getLogger(__name__)
router = APIRouter()

redis_conn = Redis.from_url(settings.redis_url)
ARCHITECTURE_CACHE_TTL_SECONDS = 60 * 60  # 1 hour


class ConnectRepoRequest(BaseModel):
    github_full_name: str  # "owner/repo"
    github_url: str
    default_branch: str = "main"


class RepoResponse(BaseModel):
    id: uuid.UUID
    github_full_name: str
    index_status: str

    class Config:
        from_attributes = True


class StatusResponse(BaseModel):
    id: uuid.UUID
    index_status: str
    last_indexed_commit_sha: str | None = None


class ArchitectureNode(BaseModel):
    id: str
    label: str
    description: str = ""
    type: str = "module"


class ArchitectureEdge(BaseModel):
    source: str
    target: str
    label: str = ""


class ArchitectureResponse(BaseModel):
    nodes: list[ArchitectureNode]
    edges: list[ArchitectureEdge]


class DriftItem(BaseModel):
    description: str
    severity: str  # high | medium | low
    file: str | None = None


class DriftResponse(BaseModel):
    drifts: list[DriftItem]


def _get_owned_repo(repo_id: uuid.UUID, current_user: User, db: Session) -> Repo:
    repo = db.query(Repo).filter(Repo.id == repo_id, Repo.owner_id == current_user.id).first()
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


def _parse_json_response(text: str) -> dict:
    """Claude sometimes wraps JSON in ```json fences despite instructions -- strip them."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail="AI service returned an unparseable response") from e


@router.get("", response_model=list[RepoResponse])
def list_repos(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Repo).filter(Repo.owner_id == current_user.id).all()


@router.post("", response_model=RepoResponse)
def connect_repo(
    payload: ConnectRepoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Registers a new repo and enqueues ingestion as a background job. The
    request handler never clones/parses/embeds anything itself -- that
    all happens in the RQ worker process (app/worker.py, app/services/ingestion.py).
    """
    check_repo_limit(current_user, db)

    existing = (
        db.query(Repo)
        .filter(Repo.owner_id == current_user.id, Repo.github_full_name == payload.github_full_name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Repo already connected")

    repo = Repo(
        owner_id=current_user.id,
        github_full_name=payload.github_full_name,
        github_url=payload.github_url,
        default_branch=payload.default_branch,
        index_status=IndexStatus.pending,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    try:
        enqueue_ingestion(repo.id)
    except Exception:
        # Redis being down shouldn't prevent the repo row from being
        # created -- surface it as a failed index rather than a 500.
        logger.exception("Failed to enqueue ingestion for repo_id=%s", repo.id)
        repo.index_status = IndexStatus.failed
        db.commit()

    return repo


@router.get("/{repo_id}/status", response_model=StatusResponse)
def get_repo_status(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Polled by the frontend every ~3s while a repo is indexing."""
    repo = _get_owned_repo(repo_id, current_user, db)
    return StatusResponse(
        id=repo.id,
        index_status=repo.index_status.value,
        last_indexed_commit_sha=repo.last_indexed_commit_sha,
    )


@router.get("/{repo_id}/architecture", response_model=ArchitectureResponse)
def get_repo_architecture(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns a module dependency graph. Cached in Redis for an hour
    since it's an expensive LLM call over the whole codebase and the
    result rarely changes between requests in that window.
    """
    repo = _get_owned_repo(repo_id, current_user, db)
    if repo.index_status != IndexStatus.ready:
        raise HTTPException(status_code=409, detail="Repo is not indexed yet")

    cache_key = f"arch:{repo_id}"
    cached = redis_conn.get(cache_key)
    if cached:
        return json.loads(cached)

    chunks = (
        db.query(CodeChunk)
        .filter(CodeChunk.repo_id == repo.id, CodeChunk.chunk_type != "readme")
        .all()
    )
    if not chunks:
        return ArchitectureResponse(nodes=[], edges=[])

    by_file: dict[str, list[CodeChunk]] = {}
    for c in chunks:
        by_file.setdefault(c.file_path, []).append(c)

    summary_parts = []
    for file_path, file_chunks in by_file.items():
        symbols = ", ".join(c.symbol_name for c in file_chunks if c.symbol_name) or "(no named symbols)"
        summary_parts.append(f"## {file_path}\nSymbols: {symbols}\n")
        # Include a small sample of actual code per file to ground the analysis,
        # without shipping the entire codebase into the prompt.
        for c in file_chunks[:3]:
            summary_parts.append(f"```\n{c.content[:800]}\n```")

    prompt = (
        "Analyze this codebase. Return ONLY a JSON object with two arrays: "
        "`nodes` (each with `id`, `label`, `description`, `type`) and `edges` "
        "(each with `source`, `target`, `label`). Identify main modules and "
        "their dependencies.\n\n" + "\n".join(summary_parts)
    )

    raw = raw_completion(prompt, max_tokens=3000)
    parsed = _parse_json_response(raw)
    result = ArchitectureResponse(
        nodes=[ArchitectureNode(**n) for n in parsed.get("nodes", [])],
        edges=[ArchitectureEdge(**e) for e in parsed.get("edges", [])],
    )

    redis_conn.setex(cache_key, ARCHITECTURE_CACHE_TTL_SECONDS, result.model_dump_json())
    return result


@router.get("/{repo_id}/drift", response_model=DriftResponse)
def get_repo_drift(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compares README claims against actual code structure, flags mismatches."""
    repo = _get_owned_repo(repo_id, current_user, db)
    if repo.index_status != IndexStatus.ready:
        raise HTTPException(status_code=409, detail="Repo is not indexed yet")

    readme_chunk = (
        db.query(CodeChunk)
        .filter(CodeChunk.repo_id == repo.id, CodeChunk.chunk_type == "readme")
        .first()
    )
    if readme_chunk is None:
        return DriftResponse(drifts=[])

    code_chunks = (
        db.query(CodeChunk)
        .filter(CodeChunk.repo_id == repo.id, CodeChunk.chunk_type != "readme")
        .all()
    )
    structure_summary = "\n".join(
        f"- {c.file_path}: {c.chunk_type} {c.symbol_name or ''}".strip()
        for c in code_chunks[:300]  # cap prompt size for very large repos
    )

    prompt = (
        "Here is the README and actual code structure. Identify mismatches "
        "where the README claims something not reflected in the code. "
        "Return JSON: {drifts: [{description, severity: high|medium|low, file}]}\n\n"
        f"## README\n{readme_chunk.content[:6000]}\n\n"
        f"## Actual code structure\n{structure_summary}"
    )

    raw = raw_completion(prompt, max_tokens=2000)
    parsed = _parse_json_response(raw)
    return DriftResponse(drifts=[DriftItem(**d) for d in parsed.get("drifts", [])])


@router.delete("/{repo_id}")
def delete_repo(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes the repo, all its chunks/history, and cancels any queued ingestion job."""
    repo = _get_owned_repo(repo_id, current_user, db)

    _cancel_pending_jobs(repo_id)

    db.query(QueryHistory).filter(QueryHistory.repo_id == repo.id).delete()
    db.query(CodeChunk).filter(CodeChunk.repo_id == repo.id).delete()
    redis_conn.delete(f"arch:{repo_id}")
    db.delete(repo)
    db.commit()

    return {"detail": "Repo deleted"}


def _cancel_pending_jobs(repo_id: uuid.UUID) -> None:
    try:
        for job in ingestion_queue.jobs:
            if job.args and str(job.args[0]) == str(repo_id):
                job.cancel()
                job.delete()
    except Exception:
        logger.exception("Failed to cancel pending ingestion jobs for repo_id=%s", repo_id)
