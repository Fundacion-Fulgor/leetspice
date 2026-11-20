"""Add OIDC subject to users.

Revision ID: d3f5a8b1c2e4
Revises: b7e4d2a9c1f0
Create Date: 2026-11-20 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision: str = "d3f5a8b1c2e4"
down_revision: str | None = "b7e4d2a9c1f0"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("oidc_subject", sa.String(length=255), nullable=True))
    op.create_index("ix_users_oidc_subject", "users", ["oidc_subject"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_oidc_subject", table_name="users")
    op.drop_column("users", "oidc_subject")
