from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlaylistPair(Base):
    __tablename__ = "playlist_pairs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    spotify_playlist_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    spotify_playlist_name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    ytmusic_playlist_id: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    ytmusic_playlist_name: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    sync_direction: Mapped[str] = mapped_column(sa.String(20), nullable=False, default="spotify_to_yt")
    auto_sync: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    sync_interval_hours: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=24)
    last_synced_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    __table_args__ = (
        sa.UniqueConstraint("spotify_playlist_id", "ytmusic_playlist_id", name="uq_playlist_pair"),
        sa.CheckConstraint(
            "sync_direction IN ('spotify_to_yt', 'yt_to_spotify', 'bidirectional')",
            name="ck_playlist_pair_direction",
        ),
        sa.CheckConstraint(
            "sync_interval_hours BETWEEN 1 AND 168",
            name="ck_playlist_pair_interval",
        ),
    )
