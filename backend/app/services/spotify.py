import json
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
