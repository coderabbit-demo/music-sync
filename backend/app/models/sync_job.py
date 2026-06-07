from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    playlist_pair_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("playlist_pairs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    triggered_by: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="pending", index=True)
    tracks_matched: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    tracks_added: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    tracks_skipped: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    tracks_failed: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    tracks: Mapped[list["SyncJobTrack"]] = relationship(
        "SyncJobTrack", back_populates="job", cascade="all, delete-orphan", lazy="select"
    )

    __table_args__ = (
        sa.CheckConstraint(
            "triggered_by IN ('manual', 'scheduler')",
            name="ck_sync_job_triggered_by",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_sync_job_status",
        ),
    )


class SyncJobTrack(Base):
    __tablename__ = "sync_job_tracks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    sync_job_id: Mapped[int] = mapped_column(
        sa.Integer, sa.ForeignKey("sync_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_provider: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    source_track_id: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    source_track_name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    source_artist: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    source_isrc: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    target_track_id: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    target_track_name: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    match_method: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    match_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    job: Mapped["SyncJob"] = relationship("SyncJob", back_populates="tracks")

    __table_args__ = (
        sa.CheckConstraint(
            "source_provider IN ('spotify', 'ytmusic')",
            name="ck_sync_job_track_provider",
        ),
        sa.CheckConstraint(
            "match_method IS NULL OR match_method IN ('isrc', 'fuzzy', 'not_found')",
            name="ck_sync_job_track_method",
        ),
        sa.CheckConstraint(
            "status IN ('added', 'skipped', 'not_found', 'error')",
            name="ck_sync_job_track_status",
        ),
    )
