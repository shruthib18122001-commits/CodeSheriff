import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.session import Base


class IndexStatus(str, enum.Enum):
    pending = "pending"
    cloning = "cloning"
    parsing = "parsing"
    embedding = "embedding"
    ready = "ready"
    failed = "failed"


class Repo(Base):
    __tablename__ = "repos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    github_full_name = Column(String, nullable=False)  # e.g. "shruthib/codesheriff"
    github_url = Column(String, nullable=False)
    default_branch = Column(String, default="main")

    # Tracks where this repo is in the ingestion pipeline. The frontend
    # polls this field to show progress (cloning -> parsing -> embedding -> ready).
    index_status = Column(Enum(IndexStatus), default=IndexStatus.pending)
    last_indexed_commit_sha = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
