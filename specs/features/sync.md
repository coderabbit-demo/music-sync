# Feature Spec: One-Time Playlist Sync

## Overview

The user links a Spotify playlist to a YouTube Music playlist (a "playlist pair"), then triggers a one-time sync. The sync engine matches tracks from the source provider and adds them to the target playlist. The user can watch job progress in real time.

---

## Scenarios

### Scenario: Create a playlist pair

**Given** both providers are connected  
**And** `spotify_playlist_id` and `ytmusic_playlist_id` are valid  
**When** `POST /api/sync/pairs` is called with:
```json
{
  "spotify_playlist_id": "37i9dQZF1DXcBWIGoYBM5M",
  "ytmusic_playlist_id": "PLrEnWoR732-BHrPp_Pm8_VleD68f9s14z",
  "sync_direction": "spotify_to_yt"
}
```
**Then** a new row is created in `playlist_pairs`  
**And** `spotify_playlist_name` and `ytmusic_playlist_name` are fetched from the respective providers and stored  
**And** the response is HTTP 201 with the full playlist pair object  

---

### Scenario: Prevent duplicate pairs

**Given** a pair with the same `spotify_playlist_id` and `ytmusic_playlist_id` already exists  
**When** `POST /api/sync/pairs` is called with the same IDs  
**Then** the response is HTTP 409 with `{ "detail": "playlist pair already exists" }`  

---

### Scenario: Trigger one-time sync

**Given** a playlist pair with id `42` exists  
**And** no sync job for this pair is currently `running`  
**When** `POST /api/sync/pairs/42/run` is called  
**Then** a new `sync_jobs` row is created with `status = pending`, `triggered_by = manual`  
**And** a Celery task `run_sync` is enqueued with the job id  
**And** the response is HTTP 202 with `{ "job_id": 7 }`  

---

### Scenario: Prevent concurrent sync runs

**Given** a sync job for pair `42` is currently in `running` status  
**When** `POST /api/sync/pairs/42/run` is called  
**Then** the response is HTTP 409 with `{ "detail": "a sync job is already running for this pair" }`  

---

### Scenario: Sync engine — ISRC match

**Given** the source track has ISRC `GBARL8800183`  
**When** the sync engine searches the target provider by ISRC  
**And** a matching track is found  
**Then** the track is added to the target playlist  
**And** `sync_job_tracks.match_method = isrc`, `status = added`  

---

### Scenario: Sync engine — fuzzy match

**Given** the source track has no ISRC, or ISRC search yields no result  
**When** the sync engine searches by `"{artist} {title}"` query string  
**And** the best candidate has `rapidfuzz.fuzz.WRatio` score ≥ `TRACK_MATCH_THRESHOLD` (default 85)  
**Then** the track is added to the target playlist  
**And** `sync_job_tracks.match_method = fuzzy`, `match_score` is recorded  

---

### Scenario: Sync engine — track not found

**Given** ISRC search finds nothing  
**And** the best fuzzy candidate scores below `TRACK_MATCH_THRESHOLD`  
**Then** the track is recorded with `match_method = not_found`, `status = not_found`  
**And** the sync job continues processing remaining tracks (not_found does not fail the job)  

---

### Scenario: Sync engine — skip already-present tracks

**Given** a track is already in the target playlist  
**When** the sync engine processes that track  
**Then** `sync_job_tracks.status = skipped`  
**And** `sync_jobs.tracks_skipped` is incremented  
**And** the track is NOT added again (no duplicates)  

---

### Scenario: Bidirectional sync

**Given** a pair with `sync_direction = bidirectional`  
**When** `POST /api/sync/pairs/{id}/run` is called  
**Then** two passes are executed: Spotify→YT, then YT→Spotify  
**And** tracks already present in either direction are skipped  

---

### Scenario: Poll sync job status

**Given** sync job id `7` is `running`  
**When** `GET /api/sync/jobs/7` is called  
**Then** the response includes:
```json
{
  "id": 7,
  "status": "running",
  "tracks_matched": 32,
  "tracks_added": 28,
  "tracks_skipped": 4,
  "tracks_failed": 0,
  "started_at": "2026-06-07T12:00:00Z",
  "completed_at": null
}
```

---

### Scenario: Job history for a pair

**Given** pair `42` has had 3 sync runs  
**When** `GET /api/sync/pairs/42/jobs` is called  
**Then** the response lists all 3 jobs ordered by `created_at` descending  

---

### Scenario: Delete a playlist pair

**Given** pair `42` exists  
**When** `DELETE /api/sync/pairs/42` is called  
**Then** the pair is deleted  
**And** all associated `sync_jobs` and `sync_job_tracks` rows are cascade-deleted  
**And** no tracks are removed from either provider's actual playlists  

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/sync/pairs` | List all playlist pairs |
| POST | `/api/sync/pairs` | Create a playlist pair |
| DELETE | `/api/sync/pairs/{id}` | Delete a playlist pair |
| POST | `/api/sync/pairs/{id}/run` | Trigger one-time sync |
| GET | `/api/sync/pairs/{id}/jobs` | List sync job history for a pair |
| GET | `/api/sync/jobs/{job_id}` | Get sync job status and track details |

---

## Track Matching Algorithm (ordered priority)

```
1. If source track has ISRC:
     search target provider by ISRC
     if found → match_method=isrc, add to playlist

2. If no ISRC or ISRC not found:
     query = "{primary_artist} {track_title}"
     fetch top 5 candidates from target provider search
     for each candidate:
       score = rapidfuzz.fuzz.WRatio(source_title, candidate_title) * 0.6
             + rapidfuzz.fuzz.WRatio(source_artist, candidate_artist) * 0.4
     best = max(candidates, key=score)
     if best.score >= TRACK_MATCH_THRESHOLD:
       match_method=fuzzy, match_score=best.score, add to playlist

3. If no match found:
     match_method=not_found, status=not_found
```
