from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ProviderToken


async def require_spotify_token(db: AsyncSession = Depends(get_db)) -> ProviderToken:
    result = await db.execute(select(ProviderToken).where(ProviderToken.provider == "spotify"))
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=401, detail="spotify not connected")
    return token


async def require_ytmusic_token(db: AsyncSession = Depends(get_db)) -> ProviderToken:
    result = await db.execute(select(ProviderToken).where(ProviderToken.provider == "ytmusic"))
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status_code=401, detail="ytmusic not connected")
    return token
