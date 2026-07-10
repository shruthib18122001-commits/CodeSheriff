import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api import repos as repos_api
from app.api.repos import (
    ArchitectureResponse,
    ConnectRepoRequest,
    connect_repo,
    delete_repo,
    get_repo_architecture,
    get_repo_drift,
    get_repo_status,
    list_repos,
)
from app.models.repo import IndexStatus


def test_list_repos_returns_current_users_repos(make_user, fake_db):
    user = make_user()
    fake_db.query.return_value.filter.return_value.all.return_value = ["repo-a", "repo-b"]

    assert list_repos(current_user=user, db=fake_db) == ["repo-a", "repo-b"]


def test_connect_repo_happy_path(make_user, fake_db, monkeypatch):
    user = make_user(plan="free")
    fake_db.query.return_value.filter.return_value.count.return_value = 0
    fake_db.query.return_value.filter.return_value.first.return_value = None

    enqueue_mock = MagicMock()
    monkeypatch.setattr(repos_api, "enqueue_ingestion", enqueue_mock)

    payload = ConnectRepoRequest(
        github_full_name="octocat/hello-world", github_url="https://github.com/octocat/hello-world"
    )
    repo = connect_repo(payload, current_user=user, db=fake_db)

    assert repo.github_full_name == "octocat/hello-world"
    assert repo.index_status == IndexStatus.pending
    enqueue_mock.assert_called_once()
    fake_db.add.assert_called_once()


def test_connect_repo_blocked_over_plan_limit(make_user, fake_db):
    user = make_user(plan="free")
    fake_db.query.return_value.filter.return_value.count.return_value = 1  # free limit is 1

    payload = ConnectRepoRequest(
        github_full_name="octocat/hello-world", github_url="https://github.com/octocat/hello-world"
    )
    with pytest.raises(HTTPException) as exc_info:
        connect_repo(payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 402


def test_connect_repo_rejects_duplicate(make_user, fake_db):
    user = make_user(plan="pro")
    fake_db.query.return_value.filter.return_value.count.return_value = 0
    fake_db.query.return_value.filter.return_value.first.return_value = MagicMock()  # already connected

    payload = ConnectRepoRequest(
        github_full_name="octocat/hello-world", github_url="https://github.com/octocat/hello-world"
    )
    with pytest.raises(HTTPException) as exc_info:
        connect_repo(payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 409


def test_connect_repo_marks_failed_when_enqueue_raises(make_user, fake_db, monkeypatch):
    user = make_user(plan="pro")
    fake_db.query.return_value.filter.return_value.count.return_value = 0
    fake_db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(repos_api, "enqueue_ingestion", MagicMock(side_effect=RuntimeError("redis down")))

    payload = ConnectRepoRequest(
        github_full_name="octocat/hello-world", github_url="https://github.com/octocat/hello-world"
    )
    repo = connect_repo(payload, current_user=user, db=fake_db)

    # A Redis outage shouldn't 500 the request -- the repo row still exists,
    # just marked failed instead of pending.
    assert repo.index_status == IndexStatus.failed


def test_get_repo_status_for_owned_repo(make_user, make_repo, fake_db):
    user = make_user()
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.embedding)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    result = get_repo_status(repo.id, current_user=user, db=fake_db)

    assert result.index_status == "embedding"


def test_get_repo_status_404_when_not_owned(make_user, fake_db):
    user = make_user()
    fake_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_repo_status(uuid.uuid4(), current_user=user, db=fake_db)

    assert exc_info.value.status_code == 404


def test_get_repo_architecture_uses_cache_when_present(make_user, make_repo, fake_db, monkeypatch):
    user = make_user()
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.ready)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    fake_redis = MagicMock()
    fake_redis.get.return_value = json.dumps({"nodes": [], "edges": []})
    monkeypatch.setattr(repos_api, "redis_conn", fake_redis)

    raw_completion_mock = MagicMock()
    monkeypatch.setattr(repos_api, "raw_completion", raw_completion_mock)

    result = get_repo_architecture(repo.id, current_user=user, db=fake_db)

    assert result == {"nodes": [], "edges": []}
    raw_completion_mock.assert_not_called()  # cache hit must skip the LLM call


def test_get_repo_architecture_calls_llm_on_cache_miss(make_user, make_repo, fake_db, monkeypatch):
    user = make_user()
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.ready)
    fake_db.query.return_value.filter.return_value.first.return_value = repo
    fake_db.query.return_value.filter.return_value.all.return_value = [
        MagicMock(file_path="app.py", symbol_name="main", chunk_type="function", content="def main(): pass")
    ]

    fake_redis = MagicMock()
    fake_redis.get.return_value = None
    monkeypatch.setattr(repos_api, "redis_conn", fake_redis)

    llm_json = json.dumps(
        {"nodes": [{"id": "app", "label": "app.py", "description": "entrypoint", "type": "module"}], "edges": []}
    )
    monkeypatch.setattr(repos_api, "raw_completion", lambda prompt, max_tokens=3000: llm_json)

    result = get_repo_architecture(repo.id, current_user=user, db=fake_db)

    assert isinstance(result, ArchitectureResponse)
    assert result.nodes[0].id == "app"
    fake_redis.setex.assert_called_once()


def test_get_repo_architecture_409_when_not_ready(make_user, make_repo, fake_db):
    user = make_user()
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.parsing)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    with pytest.raises(HTTPException) as exc_info:
        get_repo_architecture(repo.id, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 409


def test_get_repo_drift_returns_empty_without_readme(make_user, make_repo, fake_db):
    user = make_user()
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.ready)
    # First .first() call resolves the owned repo, second resolves the
    # (missing) README chunk lookup.
    fake_db.query.return_value.filter.return_value.first.side_effect = [repo, None]

    result = get_repo_drift(repo.id, current_user=user, db=fake_db)

    assert result.drifts == []


def test_get_repo_drift_flags_mismatches(make_user, make_repo, fake_db, monkeypatch):
    user = make_user()
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.ready)
    readme_chunk = MagicMock(content="# Project\nUses PostgreSQL and Redis.")
    fake_db.query.return_value.filter.return_value.first.side_effect = [repo, readme_chunk]
    fake_db.query.return_value.filter.return_value.all.return_value = [
        MagicMock(file_path="app.py", chunk_type="function", symbol_name="main")
    ]

    drift_json = json.dumps(
        {"drifts": [{"description": "README mentions Redis but no Redis client code found", "severity": "medium", "file": None}]}
    )
    monkeypatch.setattr(repos_api, "raw_completion", lambda prompt, max_tokens=2000: drift_json)

    result = get_repo_drift(repo.id, current_user=user, db=fake_db)

    assert len(result.drifts) == 1
    assert result.drifts[0].severity == "medium"


def test_delete_repo_removes_chunks_history_and_cancels_jobs(make_user, make_repo, fake_db, monkeypatch):
    user = make_user()
    repo = make_repo(owner_id=user.id)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    fake_queue = MagicMock()
    fake_queue.jobs = []
    monkeypatch.setattr(repos_api, "ingestion_queue", fake_queue)

    fake_redis = MagicMock()
    monkeypatch.setattr(repos_api, "redis_conn", fake_redis)

    result = delete_repo(repo.id, current_user=user, db=fake_db)

    assert result == {"detail": "Repo deleted"}
    fake_db.delete.assert_called_once_with(repo)
    fake_db.commit.assert_called_once()
    fake_redis.delete.assert_called_once()


def test_delete_repo_cancels_matching_pending_jobs(make_user, make_repo, fake_db, monkeypatch):
    user = make_user()
    repo = make_repo(owner_id=user.id)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    matching_job = MagicMock(args=[str(repo.id)])
    other_job = MagicMock(args=[str(uuid.uuid4())])
    fake_queue = MagicMock()
    fake_queue.jobs = [matching_job, other_job]
    monkeypatch.setattr(repos_api, "ingestion_queue", fake_queue)
    monkeypatch.setattr(repos_api, "redis_conn", MagicMock())

    delete_repo(repo.id, current_user=user, db=fake_db)

    matching_job.cancel.assert_called_once()
    matching_job.delete.assert_called_once()
    other_job.cancel.assert_not_called()
