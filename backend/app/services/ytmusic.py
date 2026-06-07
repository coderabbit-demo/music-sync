import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import ytmusicapi
from ytmusicapi import OAuthCredentials

from app.core.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YTMUSIC_SCOPE = "https://www.googleapis.com/auth/youtube"


def get_auth_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.ytmusic_redirect_uri,
        "response_type": "code",
        "scope": YTMUSIC_SCOPE,
        "access_type": "offline",
        "prompt": "consent",  # ensures refresh_token is always returned
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Exchange Google authorization code for token dict."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.ytmusic_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Use refresh_token to obtain a new access_token from Google."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()


def build_client(access_token: str, refresh_token: str, token_expiry: datetime) -> ytmusicapi.YTMusic:
    """Build an authenticated YTMusic client from stored token fields."""
    now = datetime.now(tz=timezone.utc)
    expires_in = max(0, int((token_expiry - now).total_seconds()))
    token_dict = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "scope": YTMUSIC_SCOPE,
        "expires_in": expires_in,
        "expires_at": token_expiry.timestamp(),
    }
    creds = OAuthCredentials(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    return ytmusicapi.YTMusic(auth=json.dumps(token_dict), oauth_credentials=creds)


def token_response_to_expiry(token_response: dict) -> datetime:
    """Convert Google token response to an aware UTC datetime."""
    expires_in = token_response.get("expires_in", 3600)
    return datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)


# ── Playlist operations ───────────────────────────────────────────────────────

def list_playlists(yt: ytmusicapi.YTMusic, limit: int = 50, offset: int = 0) -> dict:
    # ytmusicapi returns all playlists at once; we paginate in Python
    all_playlists = yt.get_library_playlists(limit=9999)
    page = all_playlists[offset : offset + limit]
    items = []
    for p in page:
        thumbnails = p.get("thumbnails") or []
        items.append({
            "id": p.get("playlistId", ""),
            "name": p.get("title", ""),
            "description": p.get("description") or None,
            "track_count": p.get("count") or 0,
            "thumbnail_url": thumbnails[-1]["url"] if thumbnails else None,
            "owner": None,
        })
    return {"items": items, "total": len(all_playlists), "limit": limit, "offset": offset}


def get_playlist_tracks(yt: ytmusicapi.YTMusic, playlist_id: str, limit: int = 100, offset: int = 0) -> dict:
    result = yt.get_playlist(playlist_id, limit=None)
    all_tracks = result.get("tracks", [])
    page = all_tracks[offset : offset + limit]
    items = []
    for track in page:
        if not track.get("videoId"):
            continue
        artists_raw = track.get("artists") or []
        album_raw = track.get("album") or {}
        duration_s = track.get("duration_seconds")
        items.append({
            "id": track["videoId"],
            "name": track.get("title", ""),
            "artists": [a["name"] for a in artists_raw if a.get("name")],
            "album": album_raw.get("name"),
            "duration_ms": duration_s * 1000 if duration_s else None,
            "isrc": None,
        })
    return {"items": items, "total": len(all_tracks), "limit": limit, "offset": offset}


def get_all_playlist_tracks(yt: ytmusicapi.YTMusic, playlist_id: str) -> list[dict]:
    """Fetch all tracks in a playlist."""
    result = yt.get_playlist(playlist_id, limit=None)
    items = []
    for track in result.get("tracks", []):
        if not track.get("videoId"):
            continue
        artists_raw = track.get("artists") or []
        album_raw = track.get("album") or {}
        duration_s = track.get("duration_seconds")
        items.append({
            "id": track["videoId"],
            "name": track.get("title", ""),
            "artists": [a["name"] for a in artists_raw if a.get("name")],
            "album": album_raw.get("name"),
            "duration_ms": duration_s * 1000 if duration_s else None,
            "isrc": None,
        })
    return items


def add_tracks(yt: ytmusicapi.YTMusic, playlist_id: str, video_ids: list[str]) -> None:
    """Add tracks to a YT Music playlist, batching at 50 per call."""
    for i in range(0, len(video_ids), 50):
        yt.add_playlist_items(playlist_id, video_ids[i : i + 50])


def search_tracks(yt: ytmusicapi.YTMusic, query: str, limit: int = 5) -> list[dict]:
    results = yt.search(query, filter="songs", limit=limit)
    tracks = []
    for r in results:
        artists_raw = r.get("artists") or []
        tracks.append({
            "id": r.get("videoId", ""),
            "name": r.get("title", ""),
            "artists": [a["name"] for a in artists_raw if a.get("name")],
        })
    return tracks


def get_playlist_name(yt: ytmusicapi.YTMusic, playlist_id: str) -> str:
    result = yt.get_playlist(playlist_id, limit=0)
    return result.get("title", "")
