import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.community import PostRequest, create_post, list_posts
from app.models.community_post import CommunityPost


def test_create_post_uses_repo_github_full_name(make_user, make_repo, fake_db):
    user = make_user()
    repo = make_repo(owner_id=user.id, github_full_name="pypa/sampleproject")
    fake_db.query.return_value.filter.return_value.first.return_value = repo
    # A real session's db.refresh() populates the column defaults (id,
    # created_at) after INSERT; simulate that since fake_db.refresh is a
    # no-op mock.
    fake_db.refresh.side_effect = lambda obj: (
        setattr(obj, "id", uuid.uuid4()),
        setattr(obj, "created_at", "2026-01-01T00:00:00"),
    )

    payload = PostRequest(content="  where is auth handled?  ")
    result = create_post(repo.id, payload, current_user=user, db=fake_db)

    saved_post = fake_db.add.call_args[0][0]
    assert isinstance(saved_post, CommunityPost)
    assert saved_post.github_full_name == "pypa/sampleproject"
    assert saved_post.author_id == user.id
    assert saved_post.content == "where is auth handled?"  # stripped
    fake_db.commit.assert_called_once()
    assert result.author_username == user.github_username


def test_create_post_404_when_repo_not_owned(make_user, fake_db):
    user = make_user()
    fake_db.query.return_value.filter.return_value.first.return_value = None

    payload = PostRequest(content="anything")
    with pytest.raises(HTTPException) as exc_info:
        create_post(uuid.uuid4(), payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 404


def test_create_post_422_on_whitespace_only_content(make_user, make_repo, fake_db):
    user = make_user()
    repo = make_repo(owner_id=user.id)
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    payload = PostRequest(content="   ")
    with pytest.raises(HTTPException) as exc_info:
        create_post(repo.id, payload, current_user=user, db=fake_db)

    assert exc_info.value.status_code == 422


def test_list_posts_returns_posts_joined_with_author(make_user, make_repo, fake_db):
    user = make_user()
    repo = make_repo(owner_id=user.id, github_full_name="pypa/sampleproject")
    fake_db.query.return_value.filter.return_value.first.return_value = repo

    other_user = make_user(github_username="octocat")
    fake_post = MagicMock(
        id=uuid.uuid4(), content="hello", created_at="2026-01-01T00:00:00",
    )
    fake_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        (fake_post, other_user)
    ]

    result = list_posts(repo.id, current_user=user, db=fake_db)

    assert len(result) == 1
    assert result[0].content == "hello"
    assert result[0].author_username == "octocat"
