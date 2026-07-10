import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.repo import IndexStatus


@pytest.fixture
def make_user():
    """
    Plain SimpleNamespace instead of a real User() ORM instance -- these
    tests call route/service functions directly (bypassing FastAPI's DI
    and any real DB session), so all we need is an object with the
    attributes those functions read/mutate.
    """

    def _make(plan: str = "free", queries_this_month: int = 0, **overrides):
        defaults = dict(
            id=uuid.uuid4(),
            github_id="12345",
            github_username="octocat",
            email="octocat@example.com",
            avatar_url=None,
            plan=plan,
            stripe_customer_id=None,
            queries_this_month=queries_this_month,
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make


@pytest.fixture
def make_repo():
    def _make(owner_id=None, index_status: IndexStatus = IndexStatus.ready, **overrides):
        defaults = dict(
            id=uuid.uuid4(),
            owner_id=owner_id or uuid.uuid4(),
            github_full_name="octocat/hello-world",
            github_url="https://github.com/octocat/hello-world",
            default_branch="main",
            index_status=index_status,
            last_indexed_commit_sha=None,
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    return _make


@pytest.fixture
def fake_db():
    """
    Stands in for a SQLAlchemy Session. Configure the `.query(...)` chain
    per test, e.g.:
        fake_db.query.return_value.filter.return_value.first.return_value = repo
    """
    return MagicMock()
