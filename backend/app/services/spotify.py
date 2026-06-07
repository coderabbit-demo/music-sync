from datetime import datetime, timezone

import spotipy
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from app.core.config import settings

SPOTIFY_SCOPES = (
    "playlist-read-private "
    "playlist-read-collaborative "
    "playlist-modify-private "
    "playlist-modify-public"
)


def _make_auth_manager(state: str | None = None, token_info: dict | None = None) -> SpotifyOAuth:
    if token_info is not None and "scope" not in token_info:
        token_info = {**token_info, "scope": SPOTIFY_SCOPES}
    return SpotifyOAuth(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        scope=SPOTIFY_SCOPES,
        state=state,
        show_dialog=True,
        cache_handler=MemoryCacheHandler(token_info=token_info),
    )


def get_auth_url(state: str) -> str:
    return _make_auth_manager(state=state).get_authorize_url()


def exchange_code(code: str) -> dict:
    """Exchange authorization code for token dict.  Synchronous (spotipy is not async)."""
    mgr = _make_auth_manager()
    token = mgr.get_access_token(code, as_dict=True, check_cache=False)
    return token


def refresh_if_needed(token_info: dict) -> tuple[dict, bool]:
    """Return (token_info, was_refreshed).  Refreshes when < 60 s remain."""
    mgr = _make_auth_manager(token_info=token_info)
    fresh = mgr.validate_token(token_info)
    if fresh is None:
        return token_info, False
    refreshed = fresh["access_token"] != token_info["access_token"]
    return fresh, refreshed


def build_client(token_info: dict) -> spotipy.Spotify:
    mgr = _make_auth_manager(token_info=token_info)
    return spotipy.Spotify(auth_manager=mgr)


def token_info_to_expiry(token_info: dict) -> datetime:
    """Convert spotipy's expires_at (Unix float) to an aware UTC datetime."""
    return datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc)


# ── Playlist operations ───────────────────────────────────────────────────────

def list_playlists(sp: spotipy.Spotify, limit: int = 50, offset: int = 0) -> dict:
    result = sp.current_user_playlists(limit=limit, offset=offset)
    items = []
    for p in result.get("items", []):
        images = p.get("images") or []
        # Feb 2026 API: the tracks ref sub-object was renamed "tracks" → "items"
        tracks_ref = p.get("items") or p.get("tracks") or {}
        items.append({
            "id": p["id"],
            "name": p["name"],
            "description": p.get("description") or None,
            "track_count": tracks_ref.get("total", 0) if isinstance(tracks_ref, dict) else 0,
            "thumbnail_url": images[0]["url"] if images else None,
            "owner": p.get("owner", {}).get("display_name"),
        })
    return {"items": items, "total": result.get("total", 0), "limit": limit, "offset": offset}


def get_playlist_tracks(sp: spotipy.Spotify, playlist_id: str, limit: int = 100, offset: int = 0) -> dict:
    # Feb 2026 API: inner field renamed "track" → "item"; request both to stay safe
    fields = "items(item(id,name,artists(name),album(name),duration_ms,external_ids)),total"
    result = sp.playlist_items(playlist_id, limit=limit, offset=offset, fields=fields)
    items = []
    for item in result.get("items", []):
        # "item" is the new field name (Feb 2026); fall back to "track" for older spotipy responses
        track = item.get("item") or item.get("track")
        if not track or not track.get("id"):
            continue  # skip local/unavailable tracks
        items.append({
            "id": track["id"],
            "name": track["name"],
            "artists": [a["name"] for a in track.get("artists", [])],
            "album": track.get("album", {}).get("name"),
            "duration_ms": track.get("duration_ms"),
            "isrc": track.get("external_ids", {}).get("isrc"),
        })
    return {"items": items, "total": result.get("total", 0), "limit": limit, "offset": offset}


def get_all_playlist_tracks(sp: spotipy.Spotify, playlist_id: str) -> list[dict]:
    """Fetch all tracks in a playlist, auto-paginating."""
    all_tracks: list[dict] = []
    offset = 0
    while True:
        page = get_playlist_tracks(sp, playlist_id, limit=100, offset=offset)
        all_tracks.extend(page["items"])
        if offset + 100 >= page["total"]:
            break
        offset += 100
    return all_tracks


def add_tracks(sp: spotipy.Spotify, playlist_id: str, track_ids: list[str]) -> None:
    """Add tracks to a Spotify playlist, batching at 100 per call."""
    for i in range(0, len(track_ids), 100):
        uris = [f"spotify:track:{tid}" for tid in track_ids[i : i + 100]]
        sp.playlist_add_items(playlist_id, uris)


def get_playlist_name(sp: spotipy.Spotify, playlist_id: str) -> str:
    return sp.playlist(playlist_id, fields="name")["name"]
