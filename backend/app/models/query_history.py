import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.session import Base


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False, index=True)

    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources = Column(JSONB, nullable=False, default=list)  # [{file_path, start_line, end_line, symbol_name}]

    created_at = Column(DateTime, default=datetime.utcnow)
