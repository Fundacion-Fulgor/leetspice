"""Add is_admin column to users table.

Revision ID: a1b2c3d4e5f6
Revises: c61d3b0f2481
Create Date: 2026-08-10 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c61d3b0f2481"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "is_admin")
