"""create ballchasing_credentials and game_accounts

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ballchasing_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_encrypted", sa.String(length=512), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        # Si se borra el usuario, su credencial desaparece con el: no queda un token
        # huerfano en la base.
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_ballchasing_credentials_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_ballchasing_credentials"),
    )

    op.create_table(
        "game_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("platform_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_game_accounts_user", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_game_accounts"),
        # Una identidad de juego no puede aparecer dos veces para el mismo usuario.
        sa.UniqueConstraint("user_id", "platform", "platform_id", name="uq_game_accounts_identity"),
    )
    op.create_index("ix_game_accounts_user_id", "game_accounts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_game_accounts_user_id", table_name="game_accounts")
    op.drop_table("game_accounts")
    op.drop_table("ballchasing_credentials")
