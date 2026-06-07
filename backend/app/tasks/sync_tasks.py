import asyncio
from datetime import datetime, timedelta, timezone

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import decrypt_token, encrypt_token
from app.models import PlaylistPair, ProviderToken, SyncJob, SyncJobTrack
from app.services import spotify as spotify_svc
from app.services import ytmusic as ytmusic_svc
from app.services.sync_engine import iter_sync_direction
from app.tasks.celery_app import celery_app

# NullPool is required for asyncio.run() in Celery prefork workers.
# A regular pool caches asyncpg connections bound to a specific event loop.
# Each asyncio.run() creates and then closes a new loop, so the next task finds
# pool connections "attached to a different loop" and raises RuntimeError.
# NullPool creates and destroys a connection per session context — no caching.
_engine = create_async_engine(settings.database_url, poolclass=NullPool)
AsyncSessionLocal = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

# ── One-time sync ─────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def run_sync_task(self, job_id: int) -> None:
    asyncio.run(_do_run_sync(job_id))


async def _do_run_sync(job_id: int) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(SyncJob, job_id)
        if not job:
            return

        pair = await db.get(PlaylistPair, job.playlist_pair_id)
        if not pair:
            job.status = "failed"
            job.error_message = "Playlist pair not found"
            await db.commit()
            return

        # Load provider tokens
        sp_row = (await db.execute(
            select(ProviderToken).where(ProviderToken.provider == "spotify")
        )).scalar_one_or_none()
        yt_row = (await db.execute(
            select(ProviderToken).where(ProviderToken.provider == "ytmusic")
        )).scalar_one_or_none()

        if not sp_row or not yt_row:
            job.status = "failed"
            job.error_message = "One or more provider tokens are missing"
            await db.commit()
            return

        # Build Spotify client (refresh if needed)
        sp_token_info = {
            "access_token": decrypt_token(sp_row.access_token),
            "refresh_token": decrypt_token(sp_row.refresh_token),
            "expires_at": sp_row.token_expiry.timestamp(),
            "token_type": "Bearer",
        }
        fresh_sp, sp_refreshed = spotify_svc.refresh_if_needed(sp_token_info)
        if sp_refreshed:
            sp_row.access_token = encrypt_token(fresh_sp["access_token"])
            sp_row.token_expiry = spotify_svc.token_info_to_expiry(fresh_sp)

        # Build YTMusic client (refresh if needed)
        yt_access = decrypt_token(yt_row.access_token)
        yt_refresh = decrypt_token(yt_row.refresh_token)
        if yt_row.token_expiry - timedelta(minutes=5) <= datetime.now(tz=timezone.utc):
            token_resp = await ytmusic_svc.refresh_access_token(yt_refresh)
            yt_access = token_resp["access_token"]
            yt_row.access_token = encrypt_token(yt_access)
            yt_row.token_expiry = ytmusic_svc.token_response_to_expiry(token_resp)

        sp = spotify_svc.build_client(fresh_sp)

        # Mark job as running
        job.status = "running"
        job.started_at = datetime.now(tz=timezone.utc)
        await db.commit()

        try:
            directions = []
            if pair.sync_direction in ("spotify_to_yt", "bidirectional"):
                directions.append("spotify")
            if pair.sync_direction in ("yt_to_spotify", "bidirectional"):
                directions.append("ytmusic")

            threshold = settings.track_match_threshold
            tracks_added = tracks_skipped = tracks_failed = 0

            for direction in directions:
                to_add: list[str] = []

                for tr in iter_sync_direction(direction, pair, sp, yt_access, threshold):
                    # Commit each track immediately so the UI can poll live progress
                    db.add(SyncJobTrack(
                        sync_job_id=job.id,
                        source_provider=tr.source_provider,
                        source_track_id=tr.source_track_id,
                        source_track_name=tr.source_track_name,
                        source_artist=tr.source_artist,
                        source_isrc=tr.source_isrc,
                        target_track_id=tr.target_track_id,
                        target_track_name=tr.target_track_name,
                        match_method=tr.match_method,
                        match_score=tr.match_score,
                        status=tr.status,
                        error=tr.error,
                    ))
                    await db.commit()

                    if tr.status == "added" and tr.target_track_id:
                        to_add.append(tr.target_track_id)
                        tracks_added += 1
                    elif tr.status == "skipped":
                        tracks_skipped += 1
                    elif tr.status in ("not_found", "error"):
                        tracks_failed += 1

                # Batch-add all matched tracks to the target playlist
                if to_add:
                    if direction == "spotify":
                        ytmusic_svc.add_tracks(yt_access, pair.ytmusic_playlist_id, to_add)
                    else:
                        spotify_svc.add_tracks(sp, pair.spotify_playlist_id, to_add)

            job.tracks_matched = tracks_added + tracks_skipped
            job.tracks_added = tracks_added
            job.tracks_skipped = tracks_skipped
            job.tracks_failed = tracks_failed
            job.status = "completed"
            job.completed_at = datetime.now(tz=timezone.utc)
            pair.last_synced_at = job.completed_at

        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.completed_at = datetime.now(tz=timezone.utc)

        await db.commit()


# ── Scheduled sync (celery beat) ──────────────────────────────────────────────

@celery_app.task
def scheduled_sync_all() -> None:
    asyncio.run(_do_scheduled_sync())


async def _do_scheduled_sync() -> None:
    now = datetime.now(tz=timezone.utc)

    async with AsyncSessionLocal() as db:
        pairs = (await db.execute(
            select(PlaylistPair).where(PlaylistPair.auto_sync == True)  # noqa: E712
        )).scalars().all()

        for pair in pairs:
            # Check if due
            if pair.last_synced_at is not None:
                next_due = pair.last_synced_at + timedelta(hours=pair.sync_interval_hours)
                if now < next_due:
                    continue

            # Skip if already running
            running = (await db.execute(
                select(SyncJob).where(
                    SyncJob.playlist_pair_id == pair.id,
                    SyncJob.status == "running",
                )
            )).scalar_one_or_none()
            if running:
                continue

            # Create job and enqueue
            job = SyncJob(
                playlist_pair_id=pair.id,
                triggered_by="scheduler",
                status="pending",
            )
            db.add(job)
            await db.flush()  # get job.id before commit
            await db.commit()

            run_sync_task.delay(job.id)
