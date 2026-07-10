import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_id = Column(String, unique=True, nullable=False, index=True)
    github_username = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)
    avatar_url = Column(String, nullable=True)

    # SaaS plan fields. Plan determines repo + query limits, enforced
    # in app/services/billing.py before any query is processed.
    plan = Column(String, default="free")  # free | pro | team
    stripe_customer_id = Column(String, nullable=True)
    queries_this_month = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
