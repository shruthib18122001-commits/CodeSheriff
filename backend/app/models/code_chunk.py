import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

from app.db.session import Base

# models/text-embedding-004 (Gemini) produces 768-dim vectors. If you swap
# embedding models later, this dimension must match or the column needs migrating.
EMBEDDING_DIM = 768


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False, index=True)

    file_path = Column(String, nullable=False)
    chunk_type = Column(String, nullable=False)  # function | class | module | other
    symbol_name = Column(String, nullable=True)   # e.g. function or class name
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)

    content = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
