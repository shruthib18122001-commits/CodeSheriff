import pytest
from fastapi import HTTPException

from app.services.billing import (
    PLAN_QUERY_LIMITS,
    PLAN_REPO_LIMITS,
    check_query_limit,
    check_repo_limit,
)


@pytest.mark.parametrize("plan", ["free", "pro"])
def test_check_repo_limit_blocks_at_boundary(make_user, fake_db, plan):
    limit = PLAN_REPO_LIMITS[plan]
    user = make_user(plan=plan)
    fake_db.query.return_value.filter.return_value.count.return_value = limit

    with pytest.raises(HTTPException) as exc_info:
        check_repo_limit(user, fake_db)

    assert exc_info.value.status_code == 402


@pytest.mark.parametrize("plan", ["free", "pro"])
def test_check_repo_limit_allows_just_below_boundary(make_user, fake_db, plan):
    limit = PLAN_REPO_LIMITS[plan]
    user = make_user(plan=plan)
    fake_db.query.return_value.filter.return_value.count.return_value = limit - 1

    check_repo_limit(user, fake_db)  # should not raise


def test_check_repo_limit_team_plan_has_no_cap(make_user, fake_db):
    user = make_user(plan="team")
    fake_db.query.return_value.filter.return_value.count.return_value = 10_000

    check_repo_limit(user, fake_db)  # should not raise -- team is unlimited


@pytest.mark.parametrize("plan", ["free", "pro", "team"])
def test_check_query_limit_blocks_at_boundary(make_user, plan):
    limit = PLAN_QUERY_LIMITS[plan]
    user = make_user(plan=plan, queries_this_month=limit)

    with pytest.raises(HTTPException) as exc_info:
        check_query_limit(user)

    assert exc_info.value.status_code == 402


@pytest.mark.parametrize("plan", ["free", "pro", "team"])
def test_check_query_limit_allows_just_below_boundary(make_user, plan):
    limit = PLAN_QUERY_LIMITS[plan]
    user = make_user(plan=plan, queries_this_month=limit - 1)

    check_query_limit(user)  # should not raise


def test_check_query_limit_unknown_plan_falls_back_to_free_limit(make_user):
    user = make_user(plan="not-a-real-plan", queries_this_month=PLAN_QUERY_LIMITS["free"])

    with pytest.raises(HTTPException):
        check_query_limit(user)


def test_query_limit_check_has_a_time_of_check_to_time_of_use_gap(make_user):
    """
    check_query_limit is a point-in-time read with no row lock, so two
    concurrent requests that both read queries_this_month=49 (limit 50)
    can both pass the check and both increment afterwards -- landing at
    51, one over the plan limit. This test documents that gap rather
    than "fixing" it in Python: true atomicity needs a DB-level
    `UPDATE ... SET queries_this_month = queries_this_month + 1 WHERE
    queries_this_month < :limit` (or a row-level lock), not a
    read-then-write in the request handler.
    """
    limit = PLAN_QUERY_LIMITS["free"]
    request_a_view = make_user(plan="free", queries_this_month=limit - 1)
    request_b_view = make_user(plan="free", queries_this_month=limit - 1)

    # Both "concurrent" requests observe the same pre-increment count and
    # both pass the limit check.
    check_query_limit(request_a_view)
    check_query_limit(request_b_view)

    request_a_view.queries_this_month += 1
    request_b_view.queries_this_month += 1

    # If these two views were the same underlying row, the true count
    # would now be one over the limit despite every individual check passing.
    assert request_a_view.queries_this_month == limit
    assert request_b_view.queries_this_month == limit
