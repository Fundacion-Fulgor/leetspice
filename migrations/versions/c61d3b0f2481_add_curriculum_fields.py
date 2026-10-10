"""Add curriculum metadata to challenges.

Revision ID: c61d3b0f2481
Revises: 751b9fbe0e18
Create Date: 2026-08-07 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c61d3b0f2481"
down_revision: str | None = "751b9fbe0e18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "challenges", sa.Column("is_ranked", sa.Boolean(), server_default="true", nullable=False)
    )
    op.add_column(
        "challenges",
        sa.Column("curriculum_order", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "challenges", sa.Column("prerequisites", sa.JSON(), server_default="[]", nullable=False)
    )
    op.add_column(
        "challenges", sa.Column("retired_slugs", sa.JSON(), server_default="[]", nullable=False)
    )


def downgrade() -> None:
    op.drop_column("challenges", "retired_slugs")
    op.drop_column("challenges", "prerequisites")
    op.drop_column("challenges", "curriculum_order")
    op.drop_column("challenges", "is_ranked")
