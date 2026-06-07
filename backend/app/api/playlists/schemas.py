from pydantic import BaseModel


class Playlist(BaseModel):
    id: str
    name: str
    description: str | None = None
    track_count: int
    thumbnail_url: str | None = None
    owner: str | None = None


class PlaylistPage(BaseModel):
    items: list[Playlist]
    total: int
    limit: int
    offset: int


class Track(BaseModel):
    id: str
    name: str
    artists: list[str]
    album: str | None = None
    duration_ms: int | None = None
    isrc: str | None = None


class TrackPage(BaseModel):
    items: list[Track]
    total: int
    limit: int
    offset: int
