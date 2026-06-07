"""Shared FastAPI dependencies that build authenticated provider clients."""

from datetime import datetime, timedelta, timezone

import spotipy
import ytmusicapi
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.dependencies import require_spotify_token, require_ytmusic_token
from app.core.database import get_db
from app.core.security import decrypt_token, encrypt_token
from app.models import ProviderToken
from app.services import spotify as spotify_svc
from app.services import ytmusic as ytmusic_svc


async def get_spotify_client(
    token_row: ProviderToken = Depends(require_spotify_token),
    db: AsyncSession = Depends(get_db),
) -> spotipy.Spotify:
    token_info = {
        "access_token": decrypt_token(token_row.access_token),
        "refresh_token": decrypt_token(token_row.refresh_token),
        "expires_at": token_row.token_expiry.timestamp(),
        "token_type": "Bearer",
    }
    fresh, refreshed = spotify_svc.refresh_if_needed(token_info)
    if refreshed:
        token_row.access_token = encrypt_token(fresh["access_token"])
        token_row.token_expiry = spotify_svc.token_info_to_expiry(fresh)
        await db.commit()
    return spotify_svc.build_client(fresh)


async def get_ytmusic_client(
    token_row: ProviderToken = Depends(require_ytmusic_token),
    db: AsyncSession = Depends(get_db),
) -> ytmusicapi.YTMusic:
    access = decrypt_token(token_row.access_token)
    refresh = decrypt_token(token_row.refresh_token)

    # Proactively refresh if expiring within 5 minutes
    if token_row.token_expiry - timedelta(minutes=5) <= datetime.now(tz=timezone.utc):
        token_response = await ytmusic_svc.refresh_access_token(refresh)
        access = token_response["access_token"]
        token_row.access_token = encrypt_token(access)
        token_row.token_expiry = ytmusic_svc.token_response_to_expiry(token_response)
        await db.commit()

    return ytmusic_svc.build_client(access, refresh, token_row.token_expiry)
