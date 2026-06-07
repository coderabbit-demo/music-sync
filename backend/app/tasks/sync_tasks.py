import asyncio
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_token, encrypt_token
from app.models import PlaylistPair, ProviderToken, SyncJob, SyncJobTrack
from app.services import spotify as spotify_svc
from app.services import ytmusic as ytmusic_svc
from app.services.sync_engine import run_sync
from app.tasks.celery_app import celery_app


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
        from datetime import timedelta
        if yt_row.token_expiry - timedelta(minutes=5) <= datetime.now(tz=timezone.utc):
            token_resp = await ytmusic_svc.refresh_access_token(yt_refresh)
            yt_access = token_resp["access_token"]
            yt_row.access_token = encrypt_token(yt_access)
            yt_row.token_expiry = ytmusic_svc.token_response_to_expiry(token_resp)

        sp = spotify_svc.build_client(fresh_sp)
        yt = ytmusic_svc.build_client(yt_access, yt_refresh, yt_row.token_expiry)

        # Mark job as running
        job.status = "running"
        job.started_at = datetime.now(tz=timezone.utc)
        await db.commit()

        # Run sync engine (synchronous — spotipy/ytmusicapi are not async)
        sync_result = run_sync(pair, sp, yt)

        # Persist track results
        for tr in sync_result.tracks:
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

        # Update job summary
        job.tracks_matched = sync_result.tracks_matched
        job.tracks_added = sync_result.tracks_added
        job.tracks_skipped = sync_result.tracks_skipped
        job.tracks_failed = sync_result.tracks_failed
        job.status = "failed" if sync_result.error else "completed"
        job.error_message = sync_result.error
        job.completed_at = datetime.now(tz=timezone.utc)

        if not sync_result.error:
            pair.last_synced_at = job.completed_at

        await db.commit()


# ── Scheduled sync (celery beat) ──────────────────────────────────────────────

@celery_app.task
def scheduled_sync_all() -> None:
    asyncio.run(_do_scheduled_sync())


async def _do_scheduled_sync() -> None:
    from datetime import timedelta
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
