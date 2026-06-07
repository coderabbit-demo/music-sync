"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "provider_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=False),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", name="uq_provider_tokens_provider"),
        sa.CheckConstraint("provider IN ('spotify', 'ytmusic')", name="ck_provider_token_provider"),
    )

    op.create_table(
        "playlist_pairs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("spotify_playlist_id", sa.String(100), nullable=False),
        sa.Column("spotify_playlist_name", sa.String(500), nullable=False),
        sa.Column("ytmusic_playlist_id", sa.String(100), nullable=False),
        sa.Column("ytmusic_playlist_name", sa.String(500), nullable=False),
        sa.Column("sync_direction", sa.String(20), nullable=False, server_default="spotify_to_yt"),
        sa.Column("auto_sync", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sync_interval_hours", sa.Integer, nullable=False, server_default="24"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("spotify_playlist_id", "ytmusic_playlist_id", name="uq_playlist_pair"),
        sa.CheckConstraint(
            "sync_direction IN ('spotify_to_yt', 'yt_to_spotify', 'bidirectional')",
            name="ck_playlist_pair_direction",
        ),
        sa.CheckConstraint("sync_interval_hours BETWEEN 1 AND 168", name="ck_playlist_pair_interval"),
    )

    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "playlist_pair_id",
            sa.Integer,
            sa.ForeignKey("playlist_pairs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("tracks_matched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tracks_added", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tracks_skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tracks_failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("triggered_by IN ('manual', 'scheduler')", name="ck_sync_job_triggered_by"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')", name="ck_sync_job_status"
        ),
    )
    op.create_index("idx_sync_jobs_pair_id", "sync_jobs", ["playlist_pair_id"])
    op.create_index("idx_sync_jobs_status", "sync_jobs", ["status"])

    op.create_table(
        "sync_job_tracks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "sync_job_id",
            sa.Integer,
            sa.ForeignKey("sync_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_provider", sa.String(20), nullable=False),
        sa.Column("source_track_id", sa.String(200), nullable=False),
        sa.Column("source_track_name", sa.String(500), nullable=False),
        sa.Column("source_artist", sa.String(500), nullable=True),
        sa.Column("source_isrc", sa.String(20), nullable=True),
        sa.Column("target_track_id", sa.String(200), nullable=True),
        sa.Column("target_track_name", sa.String(500), nullable=True),
        sa.Column("match_method", sa.String(20), nullable=True),
        sa.Column("match_score", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.CheckConstraint(
            "source_provider IN ('spotify', 'ytmusic')", name="ck_sync_job_track_provider"
        ),
        sa.CheckConstraint(
            "match_method IS NULL OR match_method IN ('isrc', 'fuzzy', 'not_found')",
            name="ck_sync_job_track_method",
        ),
        sa.CheckConstraint(
            "status IN ('added', 'skipped', 'not_found', 'error')", name="ck_sync_job_track_status"
        ),
    )
    op.create_index("idx_sync_job_tracks_job_id", "sync_job_tracks", ["sync_job_id"])


def downgrade() -> None:
    op.drop_table("sync_job_tracks")
    op.drop_table("sync_jobs")
    op.drop_table("playlist_pairs")
    op.drop_table("provider_tokens")
