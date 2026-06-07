# Data Models

Single-user application — no user account table or session system. OAuth tokens are stored as one row per provider.

---

## provider_tokens

Stores encrypted OAuth credentials for each connected music provider.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, autoincrement | |
| provider | VARCHAR(20) | NOT NULL, UNIQUE | `spotify` or `ytmusic` |
| access_token | TEXT | NOT NULL | Fernet-encrypted |
| refresh_token | TEXT | NOT NULL | Fernet-encrypted |
| token_expiry | TIMESTAMP | NOT NULL | UTC expiry of access token |
| scope | TEXT | | Space-separated OAuth scopes granted |
| created_at | TIMESTAMP | NOT NULL, default now() | |
| updated_at | TIMESTAMP | NOT NULL, default now() | Updated on each token refresh |

**Constraints:**
- `provider` is UNIQUE — only one connected account per provider at a time
- Tokens are encrypted at rest using Fernet (symmetric AES-128-CBC + HMAC); the key is `TOKEN_ENCRYPTION_KEY` from env

---

## playlist_pairs

A user-created link between a Spotify playlist and a YouTube Music playlist, with sync direction and schedule.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, autoincrement | |
| spotify_playlist_id | VARCHAR(100) | NOT NULL | Spotify playlist ID (base-62) |
| spotify_playlist_name | VARCHAR(500) | NOT NULL | Display name at time of pairing |
| ytmusic_playlist_id | VARCHAR(100) | NOT NULL | YT Music playlist ID |
| ytmusic_playlist_name | VARCHAR(500) | NOT NULL | Display name at time of pairing |
| sync_direction | VARCHAR(20) | NOT NULL | `spotify_to_yt`, `yt_to_spotify`, or `bidirectional` |
| auto_sync | BOOLEAN | NOT NULL, default false | Whether background sync is active |
| sync_interval_hours | INTEGER | NOT NULL, default 24 | How often to auto-sync (1–168) |
| last_synced_at | TIMESTAMP | nullable | UTC time of last completed sync |
| created_at | TIMESTAMP | NOT NULL, default now() | |

**Constraints:**
- `(spotify_playlist_id, ytmusic_playlist_id)` UNIQUE — a pair can only be linked once
- `sync_interval_hours` must be between 1 and 168 (1 week)

---

## sync_jobs

Execution record for each sync run, whether triggered manually or by the scheduler.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, autoincrement | |
| playlist_pair_id | INTEGER | FK → playlist_pairs.id, NOT NULL | |
| triggered_by | VARCHAR(20) | NOT NULL | `manual` or `scheduler` |
| status | VARCHAR(20) | NOT NULL, default `pending` | `pending`, `running`, `completed`, `failed` |
| tracks_matched | INTEGER | default 0 | Tracks successfully matched in target provider |
| tracks_added | INTEGER | default 0 | Tracks newly added to target playlist |
| tracks_skipped | INTEGER | default 0 | Tracks already present (skipped duplicates) |
| tracks_failed | INTEGER | default 0 | Tracks that could not be matched or added |
| error_message | TEXT | nullable | Top-level error if job failed entirely |
| started_at | TIMESTAMP | nullable | |
| completed_at | TIMESTAMP | nullable | |
| created_at | TIMESTAMP | NOT NULL, default now() | |

**Status transitions:**
```
pending → running → completed
                 → failed
```

**Constraints:**
- At most one `running` job per `playlist_pair_id` at a time (enforced in application layer before enqueueing)

---

## sync_job_tracks

Per-track result row within a sync job. One row per source track processed.

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, autoincrement | |
| sync_job_id | INTEGER | FK → sync_jobs.id, NOT NULL | |
| source_provider | VARCHAR(20) | NOT NULL | `spotify` or `ytmusic` |
| source_track_id | VARCHAR(200) | NOT NULL | Provider-specific track/video ID |
| source_track_name | VARCHAR(500) | NOT NULL | Track title |
| source_artist | VARCHAR(500) | | Primary artist name |
| source_isrc | VARCHAR(20) | nullable | ISRC code if available (Spotify provides this) |
| target_track_id | VARCHAR(200) | nullable | Matched track ID in target provider |
| target_track_name | VARCHAR(500) | nullable | Matched track title |
| match_method | VARCHAR(20) | nullable | `isrc`, `fuzzy`, or `not_found` |
| match_score | FLOAT | nullable | rapidfuzz WRatio score (0–100); null for ISRC matches |
| status | VARCHAR(20) | NOT NULL | `added`, `skipped`, `not_found`, `error` |
| error | TEXT | nullable | Error detail if status = `error` |

---

## Indexes

```sql
CREATE INDEX idx_sync_jobs_pair_id ON sync_jobs(playlist_pair_id);
CREATE INDEX idx_sync_jobs_status ON sync_jobs(status);
CREATE INDEX idx_sync_job_tracks_job_id ON sync_job_tracks(sync_job_id);
```
