import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.community_post import CommunityPost
from app.models.repo import Repo
from app.models.user import User

router = APIRouter()

MAX_POST_LENGTH = 2000


class PostRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_POST_LENGTH)


class PostResponse(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime
    author_username: str
    author_avatar_url: str | None = None


def _get_owned_repo(repo_id: uuid.UUID, current_user: User, db: Session) -> Repo:
    repo = db.query(Repo).filter(Repo.id == repo_id, Repo.owner_id == current_user.id).first()
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


@router.get("/{repo_id}/posts", response_model=list[PostResponse])
def list_posts(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Posts are keyed by github_full_name, not repo_id, so everyone who has
    this same GitHub repo connected -- regardless of their own separate
    Repo row -- sees and posts into one shared thread.
    """
    repo = _get_owned_repo(repo_id, current_user, db)
    rows = (
        db.query(CommunityPost, User)
        .join(User, User.id == CommunityPost.author_id)
        .filter(CommunityPost.github_full_name == repo.github_full_name)
        .order_by(CommunityPost.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        PostResponse(
            id=post.id,
            content=post.content,
            created_at=post.created_at,
            author_username=author.github_username,
            author_avatar_url=author.avatar_url,
        )
        for post, author in rows
    ]


@router.post("/{repo_id}/posts", response_model=PostResponse)
def create_post(
    repo_id: uuid.UUID,
    payload: PostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.content.strip():
        raise HTTPException(status_code=422, detail="Post content cannot be blank")

    repo = _get_owned_repo(repo_id, current_user, db)

    post = CommunityPost(
        author_id=current_user.id,
        github_full_name=repo.github_full_name,
        content=payload.content.strip(),
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    return PostResponse(
        id=post.id,
        content=post.content,
        created_at=post.created_at,
        author_username=current_user.github_username,
        author_avatar_url=current_user.avatar_url,
    )
