from datetime import datetime

from pydantic import BaseModel, field_validator


class PlaylistPairOut(BaseModel):
    id: int
    spotify_playlist_id: str
    spotify_playlist_name: str
    ytmusic_playlist_id: str
    ytmusic_playlist_name: str
    sync_direction: str
    auto_sync: bool
    sync_interval_hours: int
    last_synced_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreatePlaylistPairRequest(BaseModel):
    spotify_playlist_id: str
    ytmusic_playlist_id: str
    sync_direction: str = "spotify_to_yt"

    @field_validator("sync_direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        allowed = {"spotify_to_yt", "yt_to_spotify", "bidirectional"}
        if v not in allowed:
            raise ValueError(f"sync_direction must be one of {allowed}")
        return v


class UpdateScheduleRequest(BaseModel):
    auto_sync: bool | None = None
    sync_interval_hours: int | None = None

    @field_validator("sync_interval_hours")
    @classmethod
    def validate_interval(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 168):
            raise ValueError("sync_interval_hours must be between 1 and 168")
        return v


class SyncJobOut(BaseModel):
    id: int
    playlist_pair_id: int
    triggered_by: str
    status: str
    tracks_matched: int
    tracks_added: int
    tracks_skipped: int
    tracks_failed: int
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncJobTrackOut(BaseModel):
    id: int
    source_provider: str
    source_track_id: str
    source_track_name: str
    source_artist: str | None = None
    source_isrc: str | None = None
    target_track_id: str | None = None
    target_track_name: str | None = None
    match_method: str | None = None
    match_score: float | None = None
    status: str
    error: str | None = None

    model_config = {"from_attributes": True}


class SyncJobDetailOut(SyncJobOut):
    tracks: list[SyncJobTrackOut]
