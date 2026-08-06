"""Add challenge verification versions.

Revision ID: 751b9fbe0e18
Revises: e2c4dde62c4d
Create Date: 2026-08-06 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "751b9fbe0e18"
down_revision: str | None = "e2c4dde62c4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "challenges",
        sa.Column("verification_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "submissions",
        sa.Column("verification_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_index(
        "ix_submissions_challenge_version_status_score",
        "submissions",
        ["challenge_id", "verification_version", "status", "score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_challenge_version_status_score", table_name="submissions")
    op.drop_column("submissions", "verification_version")
    op.drop_column("challenges", "verification_version")
