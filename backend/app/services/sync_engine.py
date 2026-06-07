"""Core track matching and playlist sync logic.

Priority:
  1. ISRC exact match — only possible when target is Spotify (Spotify tracks carry ISRCs)
  2. Fuzzy match — rapidfuzz WRatio on title (60%) + artist (40%)
  3. Not found — logged, does not fail the job

Idempotency: before marking a track "added", the engine checks whether the
matched target-track ID already exists in the destination playlist.  If it
does, the track is marked "skipped" — nothing is written to the target.
"""

from dataclasses import dataclass, field
from typing import Generator

import spotipy
from rapidfuzz import fuzz

from app.core.config import settings
from app.models import PlaylistPair
from app.services import spotify as spotify_svc
from app.services import ytmusic as ytmusic_svc


@dataclass
class TrackInfo:
    id: str
    name: str
    artists: list[str]
    isrc: str | None = None


@dataclass
class TrackResult:
    source_provider: str
    source_track_id: str
    source_track_name: str
    source_artist: str | None
    source_isrc: str | None
    target_track_id: str | None
    target_track_name: str | None
    match_method: str | None      # "isrc" | "fuzzy" | "not_found"
    match_score: float | None
    status: str                   # "added" | "skipped" | "not_found" | "error"
    error: str | None = None


@dataclass
class SyncResult:
    tracks: list[TrackResult] = field(default_factory=list)
    tracks_matched: int = 0
    tracks_added: int = 0
    tracks_skipped: int = 0
    tracks_failed: int = 0
    error: str | None = None


def _fuzzy_score(s_name: str, s_artist: str, c_name: str, c_artist: str) -> float:
    title = fuzz.WRatio(s_name.lower(), c_name.lower())
    artist = fuzz.WRatio(s_artist.lower(), c_artist.lower()) if s_artist and c_artist else 0.0
    return title * 0.6 + artist * 0.4


def _match_in_ytmusic(yt_token: str, track: TrackInfo, threshold: int) -> tuple[str | None, str | None, str, float | None]:
    """Return (target_id, target_name, method, score)."""
    query = f"{track.artists[0] if track.artists else ''} {track.name}".strip()
    candidates = ytmusic_svc.search_tracks(yt_token, query, limit=5)
    best_id = best_name = None
    best_score = 0.0
    for c in candidates:
        score = _fuzzy_score(
            track.name,
            track.artists[0] if track.artists else "",
            c["name"],
            c["artists"][0] if c["artists"] else "",
        )
        if score > best_score:
            best_score, best_id, best_name = score, c["id"], c["name"]
    if best_score >= threshold and best_id:
        return best_id, best_name, "fuzzy", best_score
    return None, None, "not_found", best_score


def _match_in_spotify(sp: spotipy.Spotify, track: TrackInfo, threshold: int) -> tuple[str | None, str | None, str, float | None]:
    """Return (target_id, target_name, method, score)."""
    artist = track.artists[0] if track.artists else ""

    # ISRC exact match (highest confidence)
    if track.isrc:
        isrc_result = sp.search(f"isrc:{track.isrc}", type="track", limit=1)
        isrc_items = isrc_result.get("tracks", {}).get("items", [])
        if isrc_items:
            item = isrc_items[0]
            return item["id"], item.get("name"), "isrc", 100.0

    result = sp.search(f"{artist} {track.name}", type="track", limit=5)
    items = result.get("tracks", {}).get("items", [])
    best_id = best_name = None
    best_score = 0.0
    for item in items:
        c_name = item.get("name", "")
        c_artist = item.get("artists", [{}])[0].get("name", "") if item.get("artists") else ""
        score = _fuzzy_score(track.name, artist, c_name, c_artist)
        if score > best_score:
            best_score, best_id, best_name = score, item.get("id"), c_name
    if best_score >= threshold and best_id:
        return best_id, best_name, "fuzzy", best_score
    return None, None, "not_found", best_score


def iter_sync_direction(
    source: str,
    pair: PlaylistPair,
    sp: spotipy.Spotify,
    yt_token: str,
    threshold: int,
) -> Generator[TrackResult, None, None]:
    """Yield one TrackResult per source track.

    Idempotency: fetches existing target IDs up-front and marks already-present
    matches as "skipped" so they are never written to the destination twice.

    The caller is responsible for collecting "added" results and calling
    add_tracks once all tracks have been processed.
    """
    if source == "spotify":
        raw_sources = spotify_svc.get_all_playlist_tracks(sp, pair.spotify_playlist_id)
        existing_ids = {t["id"] for t in ytmusic_svc.get_all_playlist_tracks(yt_token, pair.ytmusic_playlist_id)}
    else:
        raw_sources = ytmusic_svc.get_all_playlist_tracks(yt_token, pair.ytmusic_playlist_id)
        existing_ids = {t["id"] for t in spotify_svc.get_all_playlist_tracks(sp, pair.spotify_playlist_id)}

    for t in raw_sources:
        track = TrackInfo(
            id=t["id"],
            name=t["name"],
            artists=t.get("artists", []),
            isrc=t.get("isrc"),
        )

        try:
            if source == "spotify":
                tid, tname, method, score = _match_in_ytmusic(yt_token, track, threshold)
            else:
                tid, tname, method, score = _match_in_spotify(sp, track, threshold)
        except Exception as exc:
            yield TrackResult(
                source_provider=source,
                source_track_id=track.id,
                source_track_name=track.name,
                source_artist=track.artists[0] if track.artists else None,
                source_isrc=track.isrc,
                target_track_id=None, target_track_name=None,
                match_method=None, match_score=None,
                status="error", error=str(exc),
            )
            continue

        if method == "not_found":
            status = "not_found"
        elif tid in existing_ids:
            status = "skipped"
        else:
            status = "added"

        yield TrackResult(
            source_provider=source,
            source_track_id=track.id,
            source_track_name=track.name,
            source_artist=track.artists[0] if track.artists else None,
            source_isrc=track.isrc,
            target_track_id=tid,
            target_track_name=tname,
            match_method=method,
            match_score=score,
            status=status,
        )


def run_sync(pair: PlaylistPair, sp: spotipy.Spotify, yt_token: str) -> SyncResult:
    """Execute the full sync for a playlist pair.  Synchronous; call from Celery task."""
    threshold = settings.track_match_threshold
    result = SyncResult()

    try:
        directions = []
        if pair.sync_direction in ("spotify_to_yt", "bidirectional"):
            directions.append("spotify")
        if pair.sync_direction in ("yt_to_spotify", "bidirectional"):
            directions.append("ytmusic")

        for direction in directions:
            to_add: list[str] = []
            for tr in iter_sync_direction(direction, pair, sp, yt_token, threshold):
                result.tracks.append(tr)
                if tr.status == "added" and tr.target_track_id:
                    to_add.append(tr.target_track_id)

            if to_add:
                if direction == "spotify":
                    ytmusic_svc.add_tracks(yt_token, pair.ytmusic_playlist_id, to_add)
                else:
                    spotify_svc.add_tracks(sp, pair.spotify_playlist_id, to_add)

        for tr in result.tracks:
            if tr.status == "added":
                result.tracks_matched += 1
                result.tracks_added += 1
            elif tr.status == "skipped":
                result.tracks_matched += 1
                result.tracks_skipped += 1
            elif tr.status in ("not_found", "error"):
                result.tracks_failed += 1

    except Exception as exc:
        result.error = str(exc)

    return result
