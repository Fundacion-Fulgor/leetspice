"""Add challenge catalog fields.

Revision ID: e2c4dde62c4d
Revises: 82b394120ac7
Create Date: 2026-08-05 12:38:48.798204
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2c4dde62c4d"
down_revision: str | None = "82b394120ac7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "challenges",
        sa.Column("category", sa.String(length=80), server_default="General", nullable=False),
    )
    op.add_column(
        "challenges",
        sa.Column("track", sa.String(length=80), server_default="General", nullable=False),
    )
    op.add_column(
        "challenges",
        sa.Column("difficulty", sa.String(length=50), server_default="medium", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("challenges", "difficulty")
    op.drop_column("challenges", "track")
    op.drop_column("challenges", "category")
