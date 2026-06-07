"""Unit tests for the sync engine — all provider calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest

from app.models import PlaylistPair
from app.services.sync_engine import (
    TrackInfo,
    _fuzzy_score,
    _match_in_spotify,
    _match_in_ytmusic,
    run_sync,
)


def _make_pair(direction="spotify_to_yt") -> PlaylistPair:
    pair = PlaylistPair()
    pair.spotify_playlist_id = "sp_abc"
    pair.ytmusic_playlist_id = "yt_xyz"
    pair.sync_direction = direction
    return pair


def _make_sp_track(tid="t1", name="Never Gonna Give You Up", artist="Rick Astley", isrc="GBARL8800183"):
    return {"id": tid, "name": name, "artists": [artist], "album": "Album", "duration_ms": 213000, "isrc": isrc}


def _make_yt_track(vid="v1", name="Never Gonna Give You Up", artist="Rick Astley"):
    return {"id": vid, "name": name, "artists": [artist], "album": "Album", "duration_ms": 213000, "isrc": None}


# ── Fuzzy score ───────────────────────────────────────────────────────────────

def test_exact_match_scores_high():
    score = _fuzzy_score("Never Gonna Give You Up", "Rick Astley", "Never Gonna Give You Up", "Rick Astley")
    assert score >= 95


def test_partial_artist_match_scores_lower():
    exact = _fuzzy_score("Track", "Artist A", "Track", "Artist A")
    partial = _fuzzy_score("Track", "Artist A", "Track", "Artist B")
    assert exact > partial


def test_completely_different_scores_low():
    score = _fuzzy_score("Never Gonna Give You Up", "Rick Astley", "Bohemian Rhapsody", "Queen")
    assert score < 50


# ── Match in YTMusic ──────────────────────────────────────────────────────────

def test_match_in_ytmusic_finds_good_match():
    yt = MagicMock()
    yt.search.return_value = [
        {"id": "v1", "name": "Never Gonna Give You Up", "artists": ["Rick Astley"]}
    ]
    track = TrackInfo("t1", "Never Gonna Give You Up", ["Rick Astley"])
    tid, tname, method, score = _match_in_ytmusic(yt, track, threshold=85)
    assert tid == "v1"
    assert method == "fuzzy"
    assert score >= 85


def test_match_in_ytmusic_returns_not_found_below_threshold():
    yt = MagicMock()
    yt.search.return_value = [
        {"id": "v2", "name": "Completely Different Song", "artists": ["Other Artist"]}
    ]
    track = TrackInfo("t1", "Never Gonna Give You Up", ["Rick Astley"])
    tid, tname, method, score = _match_in_ytmusic(yt, track, threshold=85)
    assert tid is None
    assert method == "not_found"


def test_match_in_ytmusic_no_results():
    yt = MagicMock()
    yt.search.return_value = []
    track = TrackInfo("t1", "Some Track", ["Some Artist"])
    tid, _, method, _ = _match_in_ytmusic(yt, track, threshold=85)
    assert tid is None
    assert method == "not_found"


# ── Match in Spotify ──────────────────────────────────────────────────────────

def test_match_in_spotify_finds_match():
    sp = MagicMock()
    sp.search.return_value = {
        "tracks": {
            "items": [{"id": "sp1", "name": "Never Gonna Give You Up", "artists": [{"name": "Rick Astley"}]}]
        }
    }
    track = TrackInfo("v1", "Never Gonna Give You Up", ["Rick Astley"])
    tid, tname, method, score = _match_in_spotify(sp, track, threshold=85)
    assert tid == "sp1"
    assert score >= 85


# ── Full sync ─────────────────────────────────────────────────────────────────

def test_run_sync_adds_new_tracks():
    sp = MagicMock()
    yt = MagicMock()

    source_tracks = [_make_sp_track("t1")]
    existing_yt_tracks: list = []  # target is empty
    yt_search_results = [{"id": "v1", "name": "Never Gonna Give You Up", "artists": ["Rick Astley"]}]

    with (
        patch("app.services.sync_engine.spotify_svc.get_all_playlist_tracks", return_value=source_tracks),
        patch("app.services.sync_engine.ytmusic_svc.get_all_playlist_tracks", return_value=existing_yt_tracks),
        patch("app.services.sync_engine.ytmusic_svc.search_tracks", return_value=yt_search_results),
        patch("app.services.sync_engine.ytmusic_svc.add_tracks") as mock_add,
    ):
        result = run_sync(_make_pair("spotify_to_yt"), sp, yt)

    assert result.tracks_added == 1
    assert result.tracks_skipped == 0
    assert result.tracks_failed == 0
    mock_add.assert_called_once()


def test_run_sync_skips_existing_tracks():
    sp = MagicMock()
    yt = MagicMock()

    source_tracks = [_make_sp_track("t1")]
    existing_yt_tracks = [_make_yt_track("v1")]  # already present
    yt_search_results = [{"id": "v1", "name": "Never Gonna Give You Up", "artists": ["Rick Astley"]}]

    with (
        patch("app.services.sync_engine.spotify_svc.get_all_playlist_tracks", return_value=source_tracks),
        patch("app.services.sync_engine.ytmusic_svc.get_all_playlist_tracks", return_value=existing_yt_tracks),
        patch("app.services.sync_engine.ytmusic_svc.search_tracks", return_value=yt_search_results),
        patch("app.services.sync_engine.ytmusic_svc.add_tracks") as mock_add,
    ):
        result = run_sync(_make_pair("spotify_to_yt"), sp, yt)

    assert result.tracks_skipped == 1
    assert result.tracks_added == 0
    mock_add.assert_not_called()


def test_run_sync_records_not_found():
    sp = MagicMock()
    yt = MagicMock()

    source_tracks = [_make_sp_track("t1", name="Very Obscure Track")]

    with (
        patch("app.services.sync_engine.spotify_svc.get_all_playlist_tracks", return_value=source_tracks),
        patch("app.services.sync_engine.ytmusic_svc.get_all_playlist_tracks", return_value=[]),
        patch("app.services.sync_engine.ytmusic_svc.search_tracks", return_value=[]),
        patch("app.services.sync_engine.ytmusic_svc.add_tracks"),
    ):
        result = run_sync(_make_pair("spotify_to_yt"), sp, yt)

    assert result.tracks_failed == 1
    assert result.tracks[0].status == "not_found"
