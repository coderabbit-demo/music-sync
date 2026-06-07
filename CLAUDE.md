# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**music-sync** synchronizes playlists between Spotify and YouTube Music. Users authenticate to both providers via OAuth2, browse their playlists, and sync tracks between them. Background Celery workers keep playlist pairs in sync on a schedule.

Single-user application — runs locally via Docker Compose. No login system; the app is accessed directly and OAuth tokens are stored encrypted in the database.

## Development Commands

```bash
# Start all services (first run builds images)
docker compose up --build

# Start in background
docker compose up -d --build

# View logs
docker compose logs -f backend
docker compose logs -f worker

# Run backend tests
docker compose exec backend pytest

# Run a single test file
docker compose exec backend pytest tests/test_sync_engine.py

# Run a single test by name
docker compose exec backend pytest -k "test_fuzzy_match"

# Apply database migrations
docker compose exec backend alembic upgrade head

# Create a new migration after changing models
docker compose exec backend alembic revision --autogenerate -m "description"

# Open a psql shell
docker compose exec postgres psql -U postgres musicsync

# Frontend type-check
docker compose exec frontend npm run build
```

## Architecture

### Services (docker-compose.yml)

| Service | Image/Build | Role |
|---|---|---|
| `postgres` | postgres:16-alpine | Primary database |
| `redis` | redis:7-alpine | Celery broker + result backend |
| `backend` | `./backend` | FastAPI app on :8000 |
| `worker` | `./backend` | Celery worker (same image, different CMD) |
| `beat` | `./backend` | Celery beat scheduler (same image, different CMD) |
| `frontend` | `./frontend` | Vite dev server on :5173 |
| `nginx` | nginx:1.27-alpine | Reverse proxy on :80 — `/api/*` → backend, `/*` → frontend |

### Backend (`backend/app/`)

- **`core/config.py`** — all settings via `pydantic-settings`; reads from environment
- **`core/database.py`** — SQLAlchemy async engine + `AsyncSession` factory
- **`core/security.py`** — Fernet encryption for storing OAuth tokens at rest; signed session cookies for OAuth CSRF state
- **`models/`** — SQLAlchemy ORM models: `ProviderToken`, `PlaylistPair`, `SyncJob`, `SyncJobTrack`
- **`api/auth/`** — OAuth2 flows for Spotify (via `spotipy`) and YouTube Music (via `ytmusicapi`)
- **`api/playlists/`** — list playlists and tracks from either provider
- **`api/sync/`** — playlist pair CRUD, trigger sync jobs, poll status
- **`services/spotify.py`** — `spotipy` wrapper; handles token storage and auto-refresh
- **`services/ytmusic.py`** — `ytmusicapi` wrapper; handles Google OAuth token storage
- **`services/sync_engine.py`** — core track matching (ISRC → fuzzy via `rapidfuzz`) and playlist writing
- **`tasks/celery_app.py`** — Celery app + beat schedule (`scheduled_sync_all` every 15 min)
- **`tasks/sync_tasks.py`** — `run_sync(playlist_pair_id)` Celery task

### Track Matching Priority

1. ISRC exact match (Spotify provides ISRC; YT Music does not)
2. Fuzzy match: `rapidfuzz.fuzz.WRatio` on title (60%) + artist (40%), threshold configurable via `TRACK_MATCH_THRESHOLD` (default 85)
3. Not found — logged but does not fail the job

### Data Models

Four tables. No users table (single-user app):
- `provider_tokens` — one row per provider, tokens encrypted with Fernet
- `playlist_pairs` — linked Spotify↔YT Music playlists with sync direction and schedule
- `sync_jobs` — execution records (pending → running → completed/failed)
- `sync_job_tracks` — per-track match results within a job

### Specs (`specs/`)

Written before implementation (Spec Driven Development):
- `specs/openapi.yaml` — complete API contract (source of truth for all endpoints)
- `specs/data-models.md` — schema definitions
- `specs/features/*.md` — BDD scenarios for auth, playlists, sync, and background sync

## Environment Setup

Copy `.env.example` to `.env` and fill in:
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` — from Spotify Developer Dashboard
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — from Google Cloud Console (YouTube Data API v3 enabled)
- `TOKEN_ENCRYPTION_KEY` — generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `SECRET_KEY` — generate with: `python -c "import secrets; print(secrets.token_hex(32))"`

Both OAuth apps must have their redirect URIs set to `http://localhost/api/auth/{provider}/callback`.
