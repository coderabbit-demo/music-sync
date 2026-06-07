"""Tests for the auth API — run against an in-memory SQLite DB, no real OAuth."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.security import encrypt_token
from app.main import app
from app.models import Base, ProviderToken

# ── In-memory SQLite test database ───────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def db_session():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_token_row(session, provider: str) -> ProviderToken:
    expiry = datetime.now(tz=timezone.utc) + timedelta(hours=1)
    row = ProviderToken(
        provider=provider,
        access_token=encrypt_token("fake_access"),
        refresh_token=encrypt_token("fake_refresh"),
        token_expiry=expiry,
        scope="playlist-read-private",
    )
    session.add(row)
    return row


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_status_both_disconnected(client):
    resp = client.get("/api/music/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["spotify"]["connected"] is False
    assert data["ytmusic"]["connected"] is False


@pytest.mark.asyncio
async def test_status_one_connected(client, db_session):
    make_token_row(db_session, "spotify")
    await db_session.commit()

    resp = client.get("/api/music/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["spotify"]["connected"] is True
    assert data["ytmusic"]["connected"] is False


def test_connect_spotify_redirects(client):
    resp = client.get("/api/music/spotify/connect", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "accounts.spotify.com" in resp.headers["location"]
    assert "oauth_state" in resp.cookies


def test_connect_ytmusic_redirects(client):
    resp = client.get("/api/music/ytmusic/connect", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]


def test_callback_state_mismatch_returns_400(client):
    resp = client.get("/api/music/spotify/callback?code=abc&state=wrong_state")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_disconnect_provider(client, db_session):
    make_token_row(db_session, "spotify")
    await db_session.commit()

    resp = client.delete("/api/music/spotify")
    assert resp.status_code == 204

    status = client.get("/api/music/status").json()
    assert status["spotify"]["connected"] is False


@pytest.mark.asyncio
async def test_disconnect_not_connected_returns_404(client, db_session):
    resp = client.delete("/api/music/ytmusic")
    assert resp.status_code == 404


def test_disconnect_unknown_provider_returns_404(client):
    resp = client.delete("/api/music/apple")
    assert resp.status_code == 404
