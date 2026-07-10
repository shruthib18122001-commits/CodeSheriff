"""
Full repo ingestion pipeline: clone -> parse -> embed.

Runs entirely inside the RQ worker process (see app/worker.py), never
inside a FastAPI request handler. `enqueue_ingestion` is the only thing
the API layer calls; everything else here executes on the worker.

State machine (persisted on Repo.index_status so the frontend can poll
GET /api/repos/{id}/status): pending -> cloning -> parsing -> embedding
-> ready, with a `failed` terminal state reachable from any step.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Optional

import git
from redis import Redis
from rq import Queue

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.code_chunk import CodeChunk
from app.models.repo import IndexStatus, Repo
from app.services.embedder import embed_repo_chunks

logger = logging.getLogger(__name__)

redis_conn = Redis.from_url(settings.redis_url)
ingestion_queue = Queue("ingestion", connection=redis_conn)

ALLOWED_EXTENSIONS = {".py", ".ts", ".tsx", ".js"}
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".venv", "venv", ".next", ".turbo", "coverage",
}
LOCK_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "composer.lock",
}
README_NAMES = {"README.md", "README.rst", "README.txt", "README"}
MAX_FILE_SIZE_BYTES = 500 * 1024  # 500KB, per spec

LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

# Node types that count as a "semantic unit" per language. Anything not
# captured by these falls back to a whole-file "module" chunk so nothing
# gets silently dropped (e.g. a constants-only file).
FUNCTION_NODE_TYPES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration", "method_definition", "function"},
    "typescript": {"function_declaration", "method_definition", "function_signature"},
    "tsx": {"function_declaration", "method_definition", "function_signature"},
}
CLASS_NODE_TYPES = {
    "python": {"class_definition"},
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration", "interface_declaration"},
    "tsx": {"class_declaration", "interface_declaration"},
}


def enqueue_ingestion(repo_id) -> None:
    """Called from app/api/repos.py right after a repo row is created."""
    ingestion_queue.enqueue(run_ingestion_pipeline, str(repo_id), job_timeout=1800)


def run_ingestion_pipeline(repo_id: str) -> None:
    """
    RQ job entry point. Must never raise — an unhandled exception here
    would crash the worker process and take down every other queued
    job with it. Every failure path instead sets index_status=failed
    and logs, so the frontend sees an explicit error state.
    """
    db = SessionLocal()
    tmpdir: Optional[str] = None
    try:
        repo_row = db.query(Repo).filter(Repo.id == repo_id).first()
        if repo_row is None:
            logger.warning("Ingestion job fired for missing repo_id=%s", repo_id)
            return

        tmpdir = tempfile.mkdtemp(prefix="codesheriff-")

        _set_status(db, repo_row, IndexStatus.cloning)
        clone_path = _clone_repo(repo_row.github_url, repo_row.default_branch, tmpdir)

        _set_status(db, repo_row, IndexStatus.parsing)
        chunk_dicts = _parse_repository(clone_path)

        db.query(CodeChunk).filter(CodeChunk.repo_id == repo_row.id).delete()
        db.commit()
        for c in chunk_dicts:
            db.add(CodeChunk(repo_id=repo_row.id, **c))
        db.commit()

        _set_status(db, repo_row, IndexStatus.embedding)
        embed_repo_chunks(db, repo_row.id)

        repo_row.last_indexed_commit_sha = _safe_head_sha(clone_path)
        _set_status(db, repo_row, IndexStatus.ready)

    except Exception:
        logger.exception("Ingestion failed for repo_id=%s", repo_id)
        _mark_failed(db, repo_id)
    finally:
        if tmpdir and os.path.exists(tmpdir):
            shutil.rmtree(tmpdir, onerror=_force_remove_readonly, ignore_errors=True)
        db.close()


def _mark_failed(db, repo_id: str) -> None:
    try:
        repo_row = db.query(Repo).filter(Repo.id == repo_id).first()
        if repo_row is not None:
            repo_row.index_status = IndexStatus.failed
            db.commit()
    except Exception:
        logger.exception("Could not persist failed status for repo_id=%s", repo_id)


def _set_status(db, repo_row: Repo, status: IndexStatus) -> None:
    repo_row.index_status = status
    db.commit()


def _force_remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _safe_head_sha(clone_path: str) -> Optional[str]:
    try:
        return git.Repo(clone_path).head.commit.hexsha
    except Exception:
        return None


def _clone_repo(github_url: str, branch: str, dest_dir: str) -> str:
    clone_path = os.path.join(dest_dir, "repo")
    git.Repo.clone_from(github_url, clone_path, branch=branch, depth=1)
    return clone_path


# --- Parsing ----------------------------------------------------------

def _parse_repository(root_dir: str) -> list[dict]:
    """Walk the clone, skip what we don't want, chunk what's left."""
    chunks: list[dict] = []
    root = Path(root_dir)

    readme_path = _find_readme(root)
    if readme_path is not None:
        try:
            chunks.append(_readme_chunk(root, readme_path))
        except Exception:
            logger.exception("Failed to read README at %s", readme_path)

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in LOCK_FILES:
            continue
        if path.suffix not in ALLOWED_EXTENSIONS:
            continue

        try:
            if path.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
            if _looks_binary(path):
                continue
            chunks.extend(_chunk_file(path, root))
        except Exception:
            # One malformed/unparseable file should never abort the
            # whole ingestion job.
            logger.exception("Failed to parse %s, skipping file", path)
            continue

    return chunks


def _looks_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(8192)
    except Exception:
        return True
    return b"\x00" in head


def _find_readme(root: Path) -> Optional[Path]:
    for name in README_NAMES:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def _readme_chunk(root: Path, readme_path: Path) -> dict:
    text = readme_path.read_text(encoding="utf-8", errors="replace")
    return {
        "file_path": str(readme_path.relative_to(root)),
        "chunk_type": "readme",
        "symbol_name": None,
        "start_line": 1,
        "end_line": max(text.count("\n") + 1, 1),
        "content": text,
    }


def _chunk_file(path: Path, root: Path) -> list[dict]:
    """
    Import tree_sitter_languages lazily so a missing/broken native
    grammar dependency only breaks ingestion, not the whole app.
    """
    from tree_sitter_languages import get_parser

    lang = LANGUAGE_BY_EXT[path.suffix]
    source = path.read_bytes()
    parser = get_parser(lang)
    tree = parser.parse(source)

    rel_path = str(path.relative_to(root))
    found: list[dict] = []
    _walk_node(
        tree.root_node,
        FUNCTION_NODE_TYPES[lang],
        CLASS_NODE_TYPES[lang],
        source,
        rel_path,
        found,
    )

    if not found:
        text = source.decode("utf-8", errors="replace")
        if text.strip():
            found.append({
                "file_path": rel_path,
                "chunk_type": "module",
                "symbol_name": None,
                "start_line": 1,
                "end_line": max(text.count("\n") + 1, 1),
                "content": text,
            })

    return found


def _walk_node(node, func_types, class_types, source: bytes, rel_path: str, out: list[dict], depth: int = 0) -> None:
    if depth > 60:  # guard against pathological trees
        return

    if node.type in func_types or node.type in class_types:
        chunk_type = "class" if node.type in class_types else "function"
        out.append({
            "file_path": rel_path,
            "chunk_type": chunk_type,
            "symbol_name": _extract_symbol_name(node, source),
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "content": source[node.start_byte:node.end_byte].decode("utf-8", errors="replace"),
        })
        if chunk_type == "function":
            # Don't descend into a function body looking for more
            # top-level chunks (nested closures aren't separately useful).
            return

    for child in node.children:
        _walk_node(child, func_types, class_types, source, rel_path, out, depth + 1)


def _extract_symbol_name(node, source: bytes) -> Optional[str]:
    for child in node.children:
        if child.type in ("identifier", "type_identifier", "property_identifier"):
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return None
