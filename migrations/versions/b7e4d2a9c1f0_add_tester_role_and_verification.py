"""Add tester role, test submissions, and challenge verification workflow.

Revision ID: b7e4d2a9c1f0
Revises: a1b2c3d4e5f6
Create Date: 2026-11-03 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4d2a9c1f0"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

USER_COLUMNS = ("created_by_id", "claimed_by_id", "verified_by_id")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_tester", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "submissions",
        sa.Column("is_test", sa.Boolean(), server_default="false", nullable=False),
    )
    for column in USER_COLUMNS:
        op.add_column("challenges", sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_challenges_{column}_users", "challenges", "users", [column], ["id"]
        )
    op.add_column(
        "challenges",
        sa.Column(
            "verification_status",
            sa.String(length=20),
            server_default="unverified",
            nullable=False,
        ),
    )
    op.add_column("challenges", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    op.add_column("challenges", sa.Column("verified_at", sa.DateTime(timezone=True)))
    op.add_column("challenges", sa.Column("verified_version", sa.Integer()))
    op.add_column("challenges", sa.Column("verification_notes", sa.Text()))


def downgrade() -> None:
    for column in ("verification_notes", "verified_version", "verified_at", "claimed_at"):
        op.drop_column("challenges", column)
    op.drop_column("challenges", "verification_status")
    for column in reversed(USER_COLUMNS):
        op.drop_constraint(f"fk_challenges_{column}_users", "challenges", type_="foreignkey")
        op.drop_column("challenges", column)
    op.drop_column("submissions", "is_test")
    op.drop_column("users", "is_tester")
