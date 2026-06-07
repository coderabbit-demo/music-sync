from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import spotipy
import ytmusicapi

from app.api.dependencies import get_spotify_client, get_ytmusic_client
from app.api.sync.schemas import (
    CreatePlaylistPairRequest,
    PlaylistPairOut,
    SyncJobDetailOut,
    SyncJobOut,
    UpdateScheduleRequest,
)
from app.core.database import get_db
from app.models import PlaylistPair, SyncJob, SyncJobTrack
from app.services import spotify as spotify_svc
from app.services import ytmusic as ytmusic_svc
from app.tasks.sync_tasks import run_sync_task

router = APIRouter()


# ── Playlist pairs ────────────────────────────────────────────────────────────

@router.get("/pairs", response_model=list[PlaylistPairOut])
async def list_pairs(db: AsyncSession = Depends(get_db)) -> list[PlaylistPair]:
    result = await db.execute(select(PlaylistPair).order_by(PlaylistPair.created_at.desc()))
    return result.scalars().all()


@router.post("/pairs", response_model=PlaylistPairOut, status_code=201)
async def create_pair(
    body: CreatePlaylistPairRequest,
    db: AsyncSession = Depends(get_db),
    sp: spotipy.Spotify = Depends(get_spotify_client),
    yt: ytmusicapi.YTMusic = Depends(get_ytmusic_client),
) -> PlaylistPair:
    # Check for duplicate
    existing = (await db.execute(
        select(PlaylistPair).where(
            PlaylistPair.spotify_playlist_id == body.spotify_playlist_id,
            PlaylistPair.ytmusic_playlist_id == body.ytmusic_playlist_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="playlist pair already exists")

    # Fetch display names from providers (sync calls — acceptable for one-time setup)
    try:
        sp_name = spotify_svc.get_playlist_name(sp, body.spotify_playlist_id)
    except Exception:
        sp_name = body.spotify_playlist_id

    try:
        yt_name = ytmusic_svc.get_playlist_name(yt, body.ytmusic_playlist_id)
    except Exception:
        yt_name = body.ytmusic_playlist_id

    pair = PlaylistPair(
        spotify_playlist_id=body.spotify_playlist_id,
        spotify_playlist_name=sp_name,
        ytmusic_playlist_id=body.ytmusic_playlist_id,
        ytmusic_playlist_name=yt_name,
        sync_direction=body.sync_direction,
    )
    db.add(pair)
    await db.commit()
    await db.refresh(pair)
    return pair


@router.delete("/pairs/{pair_id}", status_code=204)
async def delete_pair(pair_id: int, db: AsyncSession = Depends(get_db)) -> None:
    pair = await db.get(PlaylistPair, pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="playlist pair not found")
    await db.delete(pair)
    await db.commit()


# ── Schedule ──────────────────────────────────────────────────────────────────

@router.patch("/pairs/{pair_id}/schedule", response_model=PlaylistPairOut)
async def update_schedule(
    pair_id: int,
    body: UpdateScheduleRequest,
    db: AsyncSession = Depends(get_db),
) -> PlaylistPair:
    pair = await db.get(PlaylistPair, pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="playlist pair not found")
    if body.auto_sync is not None:
        pair.auto_sync = body.auto_sync
    if body.sync_interval_hours is not None:
        pair.sync_interval_hours = body.sync_interval_hours
    await db.commit()
    await db.refresh(pair)
    return pair


# ── Sync jobs ─────────────────────────────────────────────────────────────────

@router.post("/pairs/{pair_id}/run", status_code=202)
async def trigger_sync(pair_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    pair = await db.get(PlaylistPair, pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="playlist pair not found")

    # Reject if already running
    running = (await db.execute(
        select(SyncJob).where(
            SyncJob.playlist_pair_id == pair_id,
            SyncJob.status == "running",
        )
    )).scalar_one_or_none()
    if running:
        raise HTTPException(status_code=409, detail="a sync job is already running for this pair")

    job = SyncJob(playlist_pair_id=pair_id, triggered_by="manual", status="pending")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    run_sync_task.delay(job.id)
    return {"job_id": job.id}


@router.get("/pairs/{pair_id}/jobs", response_model=list[SyncJobOut])
async def list_jobs(
    pair_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[SyncJob]:
    pair = await db.get(PlaylistPair, pair_id)
    if not pair:
        raise HTTPException(status_code=404, detail="playlist pair not found")

    result = await db.execute(
        select(SyncJob)
        .where(SyncJob.playlist_pair_id == pair_id)
        .order_by(SyncJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=SyncJobDetailOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)) -> SyncJob:
    job = await db.get(SyncJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="sync job not found")

    # Eagerly load tracks
    await db.refresh(job, ["tracks"])
    return job
