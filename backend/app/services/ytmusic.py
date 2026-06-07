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
    token_dict = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "scope": YTMUSIC_SCOPE,
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
