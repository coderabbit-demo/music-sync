from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth.schemas import AuthStatus, ProviderStatus
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_oauth_state, decrypt_token, encrypt_token, verify_oauth_state
from app.models import ProviderToken
from app.services import spotify as spotify_svc
from app.services import ytmusic as ytmusic_svc

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _upsert_token(
    db: AsyncSession,
    provider: str,
    access_token: str,
    refresh_token: str,
    expiry,
    scope: str | None,
) -> None:
    result = await db.execute(select(ProviderToken).where(ProviderToken.provider == provider))
    row = result.scalar_one_or_none()
    if row is None:
        row = ProviderToken(provider=provider)
        db.add(row)
    row.access_token = encrypt_token(access_token)
    row.refresh_token = encrypt_token(refresh_token)
    row.token_expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
    row.scope = scope
    await db.commit()


def _check_state(state: str) -> None:
    """Verify the OAuth state token signature and expiry."""
    try:
        verify_oauth_state(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status", response_model=AuthStatus)
async def get_auth_status(db: AsyncSession = Depends(get_db)) -> AuthStatus:
    rows = (await db.execute(select(ProviderToken))).scalars().all()
    tokens = {r.provider: r for r in rows}

    def _status(provider: str) -> ProviderStatus:
        if provider in tokens:
            return ProviderStatus(connected=True, scope=tokens[provider].scope)
        return ProviderStatus(connected=False)

    return AuthStatus(spotify=_status("spotify"), ytmusic=_status("ytmusic"))


# ── Spotify ───────────────────────────────────────────────────────────────────

@router.get("/spotify/connect")
async def connect_spotify() -> RedirectResponse:
    state = create_oauth_state({"provider": "spotify"})
    return RedirectResponse(spotify_svc.get_auth_url(state))


@router.get("/spotify/callback")
async def spotify_callback(
    db: AsyncSession = Depends(get_db),
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Spotify OAuth error: {error}")

    _check_state(state)

    try:
        token_info = spotify_svc.exchange_code(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    await _upsert_token(
        db,
        provider="spotify",
        access_token=token_info["access_token"],
        refresh_token=token_info["refresh_token"],
        expiry=spotify_svc.token_info_to_expiry(token_info),
        scope=token_info.get("scope"),
    )

    return RedirectResponse(f"{settings.frontend_url}/connect?connected=spotify")


# ── YouTube Music ─────────────────────────────────────────────────────────────

@router.get("/ytmusic/connect")
async def connect_ytmusic() -> RedirectResponse:
    state = create_oauth_state({"provider": "ytmusic"})
    return RedirectResponse(ytmusic_svc.get_auth_url(state))


@router.get("/ytmusic/callback")
async def ytmusic_callback(
    db: AsyncSession = Depends(get_db),
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    _check_state(state)

    try:
        token_response = await ytmusic_svc.exchange_code(code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}") from exc

    if "refresh_token" not in token_response:
        raise HTTPException(
            status_code=400,
            detail="No refresh_token received. Re-connect to force Google to re-issue one.",
        )

    await _upsert_token(
        db,
        provider="ytmusic",
        access_token=token_response["access_token"],
        refresh_token=token_response["refresh_token"],
        expiry=ytmusic_svc.token_response_to_expiry(token_response),
        scope=token_response.get("scope"),
    )

    return RedirectResponse(f"{settings.frontend_url}/connect?connected=ytmusic")


# ── Disconnect ────────────────────────────────────────────────────────────────

@router.delete("/{provider}", status_code=204)
async def disconnect_provider(provider: str, db: AsyncSession = Depends(get_db)) -> None:
    if provider not in ("spotify", "ytmusic"):
        raise HTTPException(status_code=404, detail="Unknown provider")

    result = await db.execute(select(ProviderToken).where(ProviderToken.provider == provider))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{provider} is not connected")

    await db.delete(row)
    await db.commit()

