import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.query import AskRequest, ask_question
from app.models.repo import IndexStatus


def test_ask_question_happy_path(make_user, make_repo, fake_db, monkeypatch):
    user = make_user(plan="pro", queries_this_month=5)
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.ready)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    fake_chunk = MagicMock(file_path="app.py", start_line=1, end_line=5, symbol_name="foo")
    monkeypatch.setattr("app.api.query.embed_text", lambda q: [0.1, 0.2])
    monkeypatch.setattr("app.api.query.search_chunks", lambda db, repo_id, emb, top_k=8: [fake_chunk])
    monkeypatch.setattr(
        "app.api.query.ask_codebase",
        lambda question, chunks: {
            "answer": "It's in app.py",
            "sources": [{"file_path": "app.py", "start_line": 1, "end_line": 5, "symbol_name": "foo"}],
        },
    )

    payload = AskRequest(repo_id=repo.id, question="Where is foo?")
    result = ask_question(payload, current_user=user, db=fake_db)

    assert result["answer"] == "It's in app.py"
    assert result["sources"][0]["file_path"] == "app.py"
    assert user.queries_this_month == 6  # usage incremented exactly once
    fake_db.add.assert_called_once()
    fake_db.commit.assert_called_once()


def test_ask_question_blocked_when_query_limit_reached(make_user, fake_db):
    user = make_user(plan="free", queries_this_month=50)
    payload = AskRequest(repo_id=uuid.uuid4(), question="anything")

    with pytest.raises(HTTPException) as exc_info:
        ask_question(payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 402


def test_ask_question_404_when_repo_not_owned_or_missing(make_user, fake_db):
    user = make_user(plan="pro")
    fake_db.query.return_value.filter.return_value.first.return_value = None

    payload = AskRequest(repo_id=uuid.uuid4(), question="anything")
    with pytest.raises(HTTPException) as exc_info:
        ask_question(payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 404


def test_ask_question_409_when_repo_still_indexing(make_user, make_repo, fake_db):
    user = make_user(plan="pro")
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.embedding)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    payload = AskRequest(repo_id=repo.id, question="anything")
    with pytest.raises(HTTPException) as exc_info:
        ask_question(payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 409


def test_ask_question_422_on_blank_question(make_user, make_repo, fake_db):
    user = make_user(plan="pro")
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.ready)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    payload = AskRequest(repo_id=repo.id, question="   ")
    with pytest.raises(HTTPException) as exc_info:
        ask_question(payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 422


def test_ask_question_persists_query_history(make_user, make_repo, fake_db, monkeypatch):
    user = make_user(plan="pro")
    repo = make_repo(owner_id=user.id, index_status=IndexStatus.ready)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    monkeypatch.setattr("app.api.query.embed_text", lambda q: [0.1])
    monkeypatch.setattr("app.api.query.search_chunks", lambda db, repo_id, emb, top_k=8: [])
    monkeypatch.setattr(
        "app.api.query.ask_codebase",
        lambda question, chunks: {"answer": "no relevant code found", "sources": []},
    )

    payload = AskRequest(repo_id=repo.id, question="Anything?")
    ask_question(payload, current_user=user, db=fake_db)

    saved_history = fake_db.add.call_args[0][0]
    assert saved_history.question == "Anything?"
    assert saved_history.answer == "no relevant code found"
    assert saved_history.user_id == user.id
    assert saved_history.repo_id == repo.id
    assert saved_history.sources == []
