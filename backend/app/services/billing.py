from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.repo import Repo
from app.models.user import User

# Plan limits referenced from the pricing table we designed:
# free -> 1 repo / 50 queries, pro -> 5 repos / 500 queries, team -> unlimited repos / 2000 queries
PLAN_REPO_LIMITS = {"free": 1, "pro": 5, "team": None}  # None = unlimited
PLAN_QUERY_LIMITS = {"free": 50, "pro": 500, "team": 2000}


def check_repo_limit(user: User, db: Session) -> None:
    limit = PLAN_REPO_LIMITS.get(user.plan, 1)
    if limit is None:
        return

    current_count = db.query(Repo).filter(Repo.owner_id == user.id).count()
    if current_count >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Repo limit reached for '{user.plan}' plan ({limit} repos). Upgrade to add more.",
        )


def check_query_limit(user: User) -> None:
    limit = PLAN_QUERY_LIMITS.get(user.plan, 50)
    if user.queries_this_month >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Monthly query limit reached for '{user.plan}' plan ({limit} queries). Upgrade for more.",
        )
