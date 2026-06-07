"""YouTube Music service using the official YouTube Data API v3.

All playlist operations go to https://www.googleapis.com/youtube/v3/
with the stored OAuth Bearer token.  No ytmusicapi / InnerTube calls.
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import redis as redis_lib

from app.core.config import settings

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YTMUSIC_SCOPE = "https://www.googleapis.com/auth/youtube"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# ── Redis search cache ────────────────────────────────────────────────────────

_redis: redis_lib.Redis | None = None  # type: ignore[type-arg]


def _get_redis() -> redis_lib.Redis | None:  # type: ignore[type-arg]
    """Return a lazily-initialised Redis client, or None if unavailable."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        client = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _redis = client
        return _redis
    except Exception:
        logger.warning("Redis unavailable — YouTube search cache disabled")
        return None


def _search_cache_key(query: str) -> str:
    digest = hashlib.sha256(query.strip().lower().encode()).hexdigest()
    return f"yt:search:{digest}"


# ── Auth ──────────────────────────────────────────────────────────────────────

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


def token_response_to_expiry(token_response: dict) -> datetime:
    """Convert Google token response to an aware UTC datetime."""
    expires_in = token_response.get("expires_in", 3600)
    return datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)


# ── Internal HTTP helpers ─────────────────────────────────────────────────────

def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _yt_get(access_token: str, endpoint: str, **params: object) -> dict:
    """GET a YouTube Data API v3 endpoint.

    Retries up to settings.yt_search_max_retries times on 429 responses using
    exponential backoff (2 s, 4 s, 8 s …).  All other HTTP errors raise
    immediately.
    """
    last_exc: httpx.HTTPStatusError | None = None
    for attempt in range(settings.yt_search_max_retries + 1):
        try:
            with httpx.Client() as client:
                resp = client.get(
                    f"{YOUTUBE_API_BASE}/{endpoint}",
                    headers=_headers(access_token),
                    params={k: v for k, v in params.items() if v is not None},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise
            last_exc = exc
            if attempt < settings.yt_search_max_retries:
                wait = 2 ** (attempt + 1)   # 2, 4, 8 seconds
                logger.warning(
                    "YouTube API 429 on %s (attempt %d/%d) — retrying in %ds",
                    endpoint, attempt + 1, settings.yt_search_max_retries, wait,
                )
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def _yt_post(access_token: str, endpoint: str, body: dict, **params: object) -> dict:
    with httpx.Client() as client:
        resp = client.post(
            f"{YOUTUBE_API_BASE}/{endpoint}",
            headers=_headers(access_token),
            params={k: v for k, v in params.items() if v is not None},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


def _fetch_all_pages(access_token: str, endpoint: str, **params: object) -> tuple[list, int]:
    """Fetch every page of a list endpoint. Returns (items, totalResults)."""
    all_items: list = []
    total = 0
    page_token: str | None = None
    while True:
        p = dict(params)
        if page_token:
            p["pageToken"] = page_token
        data = _yt_get(access_token, endpoint, **p)
        total = data.get("pageInfo", {}).get("totalResults", total)
        all_items.extend(data.get("items", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return all_items, total


def _parse_playlist_item(item: dict) -> dict | None:
    snippet = item.get("snippet", {})
    video_id = (
        snippet.get("resourceId", {}).get("videoId")
        or item.get("contentDetails", {}).get("videoId")
    )
    if not video_id:
        return None
    # videoOwnerChannelTitle is the video uploader (usually the artist on official channels)
    channel = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or ""
    return {
        "id": video_id,
        "name": snippet.get("title", ""),
        "artists": [channel] if channel else [],
        "album": None,
        "duration_ms": None,
        "isrc": None,
    }


# ── Playlist operations ───────────────────────────────────────────────────────

def list_playlists(access_token: str, limit: int = 50, offset: int = 0) -> dict:
    all_playlists, total = _fetch_all_pages(
        access_token, "playlists",
        part="snippet,contentDetails",
        mine="true",
        maxResults=50,
    )
    page = all_playlists[offset : offset + limit]
    items = []
    for p in page:
        snippet = p.get("snippet", {})
        thumbnails = snippet.get("thumbnails", {})
        thumb_url = None
        for size in ("maxres", "high", "medium", "default"):
            if size in thumbnails:
                thumb_url = thumbnails[size]["url"]
                break
        items.append({
            "id": p["id"],
            "name": snippet.get("title", ""),
            "description": snippet.get("description") or None,
            "track_count": p.get("contentDetails", {}).get("itemCount", 0),
            "thumbnail_url": thumb_url,
            "owner": None,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_playlist_tracks(access_token: str, playlist_id: str, limit: int = 100, offset: int = 0) -> dict:
    all_items, total = _fetch_all_pages(
        access_token, "playlistItems",
        part="snippet,contentDetails",
        playlistId=playlist_id,
        maxResults=50,
    )
    page = all_items[offset : offset + limit]
    items = [t for item in page if (t := _parse_playlist_item(item))]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_all_playlist_tracks(access_token: str, playlist_id: str) -> list[dict]:
    """Fetch every track in a playlist."""
    all_items, _ = _fetch_all_pages(
        access_token, "playlistItems",
        part="snippet,contentDetails",
        playlistId=playlist_id,
        maxResults=50,
    )
    return [t for item in all_items if (t := _parse_playlist_item(item))]


def add_tracks(access_token: str, playlist_id: str, video_ids: list[str]) -> None:
    """Add video IDs to a YouTube playlist (one insert per video)."""
    for video_id in video_ids:
        _yt_post(
            access_token,
            "playlistItems",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
            part="snippet",
        )


def search_tracks(access_token: str, query: str, limit: int = 5) -> list[dict]:
    """Search YouTube for videos matching query. Returns list of track dicts.

    Results are cached in Redis (TTL: settings.yt_search_cache_ttl, default 7 days)
    to avoid burning quota units on repeated syncs of the same playlist.
    A throttle delay is applied before each live API call to prevent burst 429s.
    """
    cache_key = _search_cache_key(query)
    rc = _get_redis()

    if rc is not None:
        try:
            cached = rc.get(cache_key)
            if cached is not None:
                logger.debug("yt:search cache hit — %s", query)
                return json.loads(cached)
        except Exception:
            logger.warning("Redis read error for %s — falling through to API", cache_key)

    # Throttle only fires for live API calls (cache hits skip straight to return above)
    time.sleep(settings.yt_search_throttle_delay)

    data = _yt_get(
        access_token,
        "search",
        part="snippet",
        q=query,
        type="video",
        maxResults=limit,
    )
    tracks = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        channel = snippet.get("channelTitle", "")
        tracks.append({
            "id": video_id,
            "name": snippet.get("title", ""),
            "artists": [channel] if channel else [],
        })

    if rc is not None:
        try:
            rc.setex(cache_key, settings.yt_search_cache_ttl, json.dumps(tracks))
            logger.debug("yt:search cached — %s (TTL=%ds)", query, settings.yt_search_cache_ttl)
        except Exception:
            logger.warning("Redis write error for %s", cache_key)

    return tracks


def get_playlist_name(access_token: str, playlist_id: str) -> str:
    data = _yt_get(access_token, "playlists", part="snippet", id=playlist_id)
    items = data.get("items", [])
    return items[0].get("snippet", {}).get("title", "") if items else ""
