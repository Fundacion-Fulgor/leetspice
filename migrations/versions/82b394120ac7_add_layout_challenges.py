"""add layout challenges

Revision ID: 82b394120ac7
Revises: 5affc65b65db
Create Date: 2026-08-04 15:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "82b394120ac7"
down_revision: str | None = "5affc65b65db"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "challenges",
        sa.Column(
            "submission_kind", sa.String(length=30), nullable=False, server_default="netlist"
        ),
    )
    op.add_column(
        "challenges",
        sa.Column("judge_backend", sa.String(length=80), nullable=False, server_default="cace"),
    )
    op.add_column(
        "challenges", sa.Column("submission_config", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column(
        "challenges", sa.Column("judge_config", sa.JSON(), nullable=False, server_default="{}")
    )
    op.add_column("challenges", sa.Column("fixture_path", sa.String(length=255), nullable=True))
    op.add_column(
        "challenges", sa.Column("assets", sa.JSON(), nullable=False, server_default="[]")
    )

    op.add_column(
        "submissions",
        sa.Column(
            "submission_kind", sa.String(length=30), nullable=False, server_default="netlist"
        ),
    )
    op.add_column("submissions", sa.Column("payload_binary", sa.LargeBinary(), nullable=True))
    op.add_column(
        "submissions", sa.Column("original_filename", sa.String(length=255), nullable=True)
    )
    op.add_column("submissions", sa.Column("media_type", sa.String(length=120), nullable=True))
    op.add_column(
        "submissions", sa.Column("payload_size", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("submissions", sa.Column("payload_sha256", sa.String(length=64), nullable=True))
    op.alter_column("submissions", "netlist", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM submissions WHERE submission_kind != 'netlist'")
    op.alter_column("submissions", "netlist", existing_type=sa.Text(), nullable=False)
    for column in (
        "payload_sha256",
        "payload_size",
        "media_type",
        "original_filename",
        "payload_binary",
        "submission_kind",
    ):
        op.drop_column("submissions", column)
    for column in (
        "assets",
        "fixture_path",
        "judge_config",
        "submission_config",
        "judge_backend",
        "submission_kind",
    ):
        op.drop_column("challenges", column)
