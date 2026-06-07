# Feature Spec: Background Sync

## Overview

Playlist pairs can be configured to sync automatically on a recurring schedule. Celery beat dispatches `scheduled_sync_all` periodically; that task finds all pairs due for sync and enqueues individual `run_sync` tasks for each.

---

## Scenarios

### Scenario: Enable auto-sync on a pair

**Given** playlist pair `42` exists with `auto_sync = false`  
**When** `PATCH /api/sync/pairs/42/schedule` is called with:
```json
{
  "auto_sync": true,
  "sync_interval_hours": 6
}
```
**Then** the pair is updated: `auto_sync = true`, `sync_interval_hours = 6`  
**And** the response is HTTP 200 with the updated pair object  

---

### Scenario: Disable auto-sync

**Given** playlist pair `42` has `auto_sync = true`  
**When** `PATCH /api/sync/pairs/42/schedule` is called with `{ "auto_sync": false }`  
**Then** `auto_sync = false` is saved  
**And** no further background jobs are enqueued for this pair  

---

### Scenario: Scheduler dispatches due jobs

**Given** celery beat runs `scheduled_sync_all` every 15 minutes  
**And** pair `42` has `auto_sync = true`, `sync_interval_hours = 6`  
**And** `last_synced_at` is more than 6 hours ago (or null)  
**When** `scheduled_sync_all` executes  
**Then** a `run_sync` Celery task is enqueued for pair `42`  
**And** `triggered_by = scheduler` is recorded on the resulting `sync_jobs` row  

---

### Scenario: Scheduler skips pair with a running job

**Given** pair `42` already has a `sync_jobs` row with `status = running`  
**When** `scheduled_sync_all` checks pair `42`  
**Then** no new task is enqueued for pair `42` (deduplication)  

---

### Scenario: Scheduler skips pair not yet due

**Given** pair `42` has `sync_interval_hours = 24`  
**And** `last_synced_at` is 3 hours ago  
**When** `scheduled_sync_all` executes  
**Then** pair `42` is not enqueued  

---

### Scenario: last_synced_at is updated after completion

**Given** a background sync job for pair `42` completes successfully  
**When** the Celery task finishes and sets `sync_jobs.status = completed`  
**Then** `playlist_pairs.last_synced_at` is updated to the completion timestamp  

---

### Scenario: Failed background job does not block future runs

**Given** the last sync job for pair `42` has `status = failed`  
**And** the pair is due for sync again  
**When** `scheduled_sync_all` executes  
**Then** a new `run_sync` task is enqueued (failed status does not count as "running")  

---

### Scenario: Interval validation

**When** `PATCH /api/sync/pairs/{id}/schedule` is called with `sync_interval_hours = 0`  
**Then** the response is HTTP 422 with a validation error  
**And** valid range is 1–168 (hourly to weekly)  

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| PATCH | `/api/sync/pairs/{id}/schedule` | Update auto-sync settings for a pair |

### Request body
```json
{
  "auto_sync": true,
  "sync_interval_hours": 6
}
```
Both fields are optional; only provided fields are updated.

---

## Celery Task Architecture

```
celery-beat (container: beat)
  └── runs every 15 min: scheduled_sync_all
        └── queries DB: SELECT * FROM playlist_pairs
                        WHERE auto_sync = true
                        AND (last_synced_at IS NULL
                             OR last_synced_at + sync_interval_hours < now())
        └── for each due pair (no running job):
              enqueue: run_sync(playlist_pair_id, triggered_by="scheduler")

celery-worker (container: worker)
  └── run_sync(playlist_pair_id, triggered_by)
        1. Create sync_job row (status=running)
        2. Fetch source playlist tracks
        3. For each track: match + add via sync_engine
        4. Update sync_job (status=completed/failed, counts)
        5. Update playlist_pairs.last_synced_at
```

**Broker:** Redis (`REDIS_URL`)  
**Result backend:** Redis  
**Concurrency:** Worker defaults to `min(4, cpu_count)` processes; configurable via `CELERY_CONCURRENCY` env var  
**Task timeout:** 30 minutes (`task_soft_time_limit = 1800`) — large playlists may take time due to API rate limits
