"""replays, player_stats y cola de sincronizacion

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 09:44:36.086307
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `users.firebase_uid` es UNIQUE, y Postgres ya indexa las columnas UNIQUE:
    # este indice de la migracion 0001 sobraba.
    op.drop_index(op.f("ix_users_firebase_uid"), table_name="users")

    # este indice de la migracion 0001 sobraba.

    op.create_table(
        "replays",
        sa.Column("ballchasing_id", sa.String(length=36), nullable=False),
        sa.Column("played_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rocket_league_id", sa.String(length=64), nullable=True),
        sa.Column("playlist_id", sa.String(length=64), nullable=False),
        sa.Column("playlist_name", sa.String(length=64), nullable=True),
        sa.Column("map_code", sa.String(length=64), nullable=True),
        sa.Column("map_name", sa.String(length=64), nullable=True),
        sa.Column("team_size", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("play_duration", sa.Integer(), nullable=True),
        sa.Column("overtime", sa.Boolean(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("season_type", sa.String(length=32), nullable=True),
        sa.Column("blue_goals", sa.Integer(), nullable=True),
        sa.Column("orange_goals", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("ballchasing_id"),
    )
    op.create_index(op.f("ix_replays_played_at"), "replays", ["played_at"], unique=False)
    op.create_index(op.f("ix_replays_playlist_id"), "replays", ["playlist_id"], unique=False)
    op.create_table(
        "player_stats",
        sa.Column("replay_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("platform_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=True),
        sa.Column("team", sa.String(length=8), nullable=True),
        sa.Column("mvp", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("goals", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("shots", sa.Integer(), nullable=True),
        sa.Column("goals_against", sa.Integer(), nullable=True),
        sa.Column("shots_against", sa.Integer(), nullable=True),
        sa.Column("shooting_percentage", sa.Float(), nullable=True),
        sa.Column("bpm", sa.Integer(), nullable=True),
        sa.Column("avg_amount", sa.Float(), nullable=True),
        sa.Column("percent_zero_boost", sa.Float(), nullable=True),
        sa.Column("percent_full_boost", sa.Float(), nullable=True),
        sa.Column("amount_stolen", sa.Integer(), nullable=True),
        sa.Column("avg_speed", sa.Integer(), nullable=True),
        sa.Column("percent_supersonic_speed", sa.Float(), nullable=True),
        sa.Column("percent_ground", sa.Float(), nullable=True),
        sa.Column("percent_low_air", sa.Float(), nullable=True),
        sa.Column("percent_high_air", sa.Float(), nullable=True),
        sa.Column("percent_defensive_third", sa.Float(), nullable=True),
        sa.Column("percent_offensive_third", sa.Float(), nullable=True),
        sa.Column("percent_behind_ball", sa.Float(), nullable=True),
        sa.Column("percent_most_back", sa.Float(), nullable=True),
        sa.Column("percent_most_forward", sa.Float(), nullable=True),
        sa.Column("demos_inflicted", sa.Integer(), nullable=True),
        sa.Column("demos_taken", sa.Integer(), nullable=True),
        sa.Column("epic_saves", sa.Integer(), nullable=True),
        sa.Column("clears", sa.Integer(), nullable=True),
        sa.Column("centers", sa.Integer(), nullable=True),
        sa.Column("aerial_hits", sa.Integer(), nullable=True),
        sa.Column("first_touches", sa.Integer(), nullable=True),
        sa.Column("flip_resets", sa.Integer(), nullable=True),
        sa.Column("demos_inflicted_def_half", sa.Integer(), nullable=True),
        sa.Column("demos_inflicted_off_half", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["replay_id"], ["replays.ballchasing_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("replay_id", "platform", "platform_id"),
    )
    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "run_after",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("replays_nuevos", sa.Integer(), nullable=False),
        sa.Column("replays_omitidos", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sync_jobs_status"), "sync_jobs", ["status"], unique=False)
    op.create_index(
        "ix_sync_jobs_status_run_after", "sync_jobs", ["status", "run_after"], unique=False
    )
    op.create_index("ix_sync_jobs_user_id", "sync_jobs", ["user_id"], unique=False)
    op.create_table(
        "sync_state",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_replay_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_replays", sa.Integer(), nullable=False),
        sa.Column("auto_sync", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "user_replays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("replay_id", sa.String(length=36), nullable=False),
        sa.Column("game_account_id", sa.Uuid(), nullable=False),
        sa.Column("team", sa.String(length=8), nullable=False),
        sa.Column("result", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(["game_account_id"], ["game_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replay_id"], ["replays.ballchasing_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "replay_id", name="uq_user_replays_user_replay"),
    )
    op.create_index("ix_user_replays_user_id", "user_replays", ["user_id"], unique=False)


def downgrade() -> None:
    op.create_index(op.f("ix_users_firebase_uid"), "users", ["firebase_uid"], unique=False)

    op.drop_index("ix_user_replays_user_id", table_name="user_replays")
    op.drop_table("user_replays")
    op.drop_table("sync_state")
    op.drop_index("ix_sync_jobs_user_id", table_name="sync_jobs")
    op.drop_index("ix_sync_jobs_status_run_after", table_name="sync_jobs")
    op.drop_index(op.f("ix_sync_jobs_status"), table_name="sync_jobs")
    op.drop_table("sync_jobs")
    op.drop_table("player_stats")
    op.drop_index(op.f("ix_replays_playlist_id"), table_name="replays")
    op.drop_index(op.f("ix_replays_played_at"), table_name="replays")
    op.drop_table("replays")
