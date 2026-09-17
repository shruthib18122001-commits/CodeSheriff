"""community posts

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-17

Adds community_posts: a per-GitHub-repo discussion thread (keyed by
github_full_name, not repos.id) so users who each independently connected
the same underlying GitHub repo land in one shared thread.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "community_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("github_full_name", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_community_posts_author_id", "community_posts", ["author_id"])
    op.create_index("ix_community_posts_github_full_name", "community_posts", ["github_full_name"])


def downgrade() -> None:
    op.drop_table("community_posts")
