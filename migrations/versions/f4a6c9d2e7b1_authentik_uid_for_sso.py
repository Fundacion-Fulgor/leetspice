"""Key single sign-on accounts by the Authentik user id.

Renames users.oidc_subject (added by d3f5a8b1c2e4, never used in production) to authentik_uid and
adds authentik_username.

Revision ID: f4a6c9d2e7b1
Revises: d3f5a8b1c2e4
Create Date: 2026-11-25 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision: str = "f4a6c9d2e7b1"
down_revision: str | None = "d3f5a8b1c2e4"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_oidc_subject", table_name="users")
    op.alter_column("users", "oidc_subject", new_column_name="authentik_uid")
    op.create_index("ix_users_authentik_uid", "users", ["authentik_uid"], unique=True)
    op.add_column("users", sa.Column("authentik_username", sa.String(length=150), nullable=True))
    # Accounts created by the unused OIDC login carry the old marker.
    op.execute("UPDATE users SET password_hash = '!sso' WHERE password_hash = '!oidc'")


def downgrade() -> None:
    op.drop_column("users", "authentik_username")
    op.drop_index("ix_users_authentik_uid", table_name="users")
    op.alter_column("users", "authentik_uid", new_column_name="oidc_subject")
    op.create_index("ix_users_oidc_subject", "users", ["oidc_subject"], unique=True)
