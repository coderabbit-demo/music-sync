# music-sync

Synchronize playlists between Spotify and YouTube Music. Connect both accounts via OAuth, browse playlists side-by-side, and sync tracks on demand or on a schedule.

## Features

- OAuth2 authentication for Spotify and YouTube Music
- Side-by-side playlist browser for both providers
- One-time sync: Spotify → YT Music, YT Music → Spotify, or bidirectional
- Track matching via ISRC (exact) then fuzzy title + artist scoring ([rapidfuzz](https://github.com/rapidfuzz/RapidFuzz))
- Background auto-sync on a configurable interval (Celery + Redis)
- Per-job history with per-track match results

## Requirements

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (v2)
- A Spotify Developer app
- A Google Cloud project with YouTube Data API v3 enabled

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/coderabbit-demo/music-sync.git
cd music-sync
```

### 2. Create a Spotify app

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Under **Edit Settings**, add the redirect URI:
   ```
   http://127.0.0.1:8000/api/music/spotify/callback
   ```
3. Note the **Client ID** and **Client Secret**.

### 3. Create a Google OAuth app

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create (or select) a project.
2. Enable the **YouTube Data API v3** under *APIs & Services → Library*.
3. Go to *APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID*.
4. Set the application type to **Web application** and add the authorized redirect URI:
   ```
   http://localhost/api/auth/ytmusic/callback
   ```
5. Note the **Client ID** and **Client Secret**.

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Variable | Description |
|---|---|
| `SPOTIFY_CLIENT_ID` | From the Spotify Developer Dashboard |
| `SPOTIFY_CLIENT_SECRET` | From the Spotify Developer Dashboard |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `TOKEN_ENCRYPTION_KEY` | Fernet key — generate with the command below |
| `SECRET_KEY` | Random secret for signing cookies — generate with the command below |

Generate the security keys:

```bash
# TOKEN_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Start the application

```bash
docker compose up --build
```

This starts seven services: `postgres`, `redis`, `backend`, `worker`, `beat`, `frontend`, and `nginx`.

### 6. Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

### 7. Open the app

Visit [http://localhost](http://localhost) in your browser.

1. Click **Connect Spotify** and complete the OAuth flow.
2. Click **Connect YouTube Music** and complete the OAuth flow.
3. Go to **Browse Playlists**, select one playlist from each provider, and click **Sync**.
4. The Sync Dashboard shows live job status and per-track results.
5. Enable **Auto-sync** on any pair to keep it in sync automatically.

## Architecture

```
nginx :80
  /api/*  → FastAPI backend :8000
  /*      → Vite frontend  :5173

PostgreSQL  — stores OAuth tokens (encrypted), playlist pairs, sync jobs
Redis       — Celery broker + result backend

Celery worker  — executes sync jobs
Celery beat    — fires scheduled_sync_all every 15 min
```

| Service | Role |
|---|---|
| `backend` | FastAPI — auth, playlist browsing, sync API |
| `worker` | Celery worker — runs track-matching and playlist writes |
| `beat` | Celery beat — triggers auto-sync on schedule |
| `frontend` | Vite / React — UI |
| `postgres` | Primary database |
| `redis` | Message broker and task result backend |
| `nginx` | Reverse proxy |

## Development

```bash
# View logs
docker compose logs -f backend
docker compose logs -f worker

# Run backend tests
docker compose exec backend pytest

# Run a single test file
docker compose exec backend pytest tests/test_sync_engine.py

# Apply migrations after changing models
docker compose exec backend alembic revision --autogenerate -m "description"
docker compose exec backend alembic upgrade head

# Open a psql shell
docker compose exec postgres psql -U postgres musicsync

# Frontend type-check
docker compose exec frontend npm run build
```

## Track matching

For each source track the engine tries in order:

1. **ISRC exact match** — Spotify tracks carry an ISRC; a direct `isrc:` search on the target provider is attempted first.
2. **Fuzzy match** — `rapidfuzz.fuzz.WRatio` on title (60%) + artist (40%). Accepted when score ≥ `TRACK_MATCH_THRESHOLD` (default 85).
3. **Not found** — logged per-track; does not fail the job.

## License

[MIT](LICENSE)
