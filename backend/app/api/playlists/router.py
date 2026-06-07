from fastapi import APIRouter, Depends, HTTPException, Query
import spotipy
import ytmusicapi

from app.api.dependencies import get_spotify_client, get_ytmusic_client
from app.api.playlists.schemas import PlaylistPage, TrackPage
from app.services import spotify as spotify_svc
from app.services import ytmusic as ytmusic_svc

router = APIRouter()


@router.get("/spotify", response_model=PlaylistPage)
def list_spotify_playlists(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sp: spotipy.Spotify = Depends(get_spotify_client),
) -> PlaylistPage:
    data = spotify_svc.list_playlists(sp, limit=limit, offset=offset)
    return PlaylistPage(**data)


@router.get("/ytmusic", response_model=PlaylistPage)
def list_ytmusic_playlists(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    yt: ytmusicapi.YTMusic = Depends(get_ytmusic_client),
) -> PlaylistPage:
    data = ytmusic_svc.list_playlists(yt, limit=limit, offset=offset)
    return PlaylistPage(**data)


@router.get("/spotify/{playlist_id}/tracks", response_model=TrackPage)
def get_spotify_tracks(
    playlist_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sp: spotipy.Spotify = Depends(get_spotify_client),
) -> TrackPage:
    try:
        data = spotify_svc.get_playlist_tracks(sp, playlist_id, limit=limit, offset=offset)
    except spotipy.SpotifyException as exc:
        if exc.http_status == 404:
            raise HTTPException(status_code=404, detail="playlist not found")
        raise
    return TrackPage(**data)


@router.get("/ytmusic/{playlist_id}/tracks", response_model=TrackPage)
def get_ytmusic_tracks(
    playlist_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    yt: ytmusicapi.YTMusic = Depends(get_ytmusic_client),
) -> TrackPage:
    try:
        data = ytmusic_svc.get_playlist_tracks(yt, playlist_id, limit=limit, offset=offset)
    except Exception as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="playlist not found")
        raise
    return TrackPage(**data)
