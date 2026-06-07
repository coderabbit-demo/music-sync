"""Smoke tests: verify models define the expected tables and columns."""

from app.models import Base, PlaylistPair, ProviderToken, SyncJob, SyncJobTrack


def test_all_tables_registered():
    table_names = set(Base.metadata.tables.keys())
    assert table_names == {"provider_tokens", "playlist_pairs", "sync_jobs", "sync_job_tracks"}


def test_provider_token_columns():
    cols = {c.name for c in ProviderToken.__table__.columns}
    assert {"id", "provider", "access_token", "refresh_token", "token_expiry"} <= cols


def test_playlist_pair_columns():
    cols = {c.name for c in PlaylistPair.__table__.columns}
    assert {"spotify_playlist_id", "ytmusic_playlist_id", "sync_direction", "auto_sync"} <= cols


def test_sync_job_columns():
    cols = {c.name for c in SyncJob.__table__.columns}
    assert {"status", "triggered_by", "tracks_matched", "tracks_added"} <= cols


def test_sync_job_track_columns():
    cols = {c.name for c in SyncJobTrack.__table__.columns}
    assert {"source_track_id", "match_method", "match_score", "status"} <= cols
