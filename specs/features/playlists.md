# Feature Spec: Playlist Browsing

## Overview

After connecting providers, the user can view their playlists from Spotify and YouTube Music side-by-side. They can browse tracks within any playlist before initiating a sync.

---

## Scenarios

### Scenario: List Spotify playlists

**Given** Spotify is connected  
**When** `GET /api/playlists/spotify` is called  
**Then** the response is HTTP 200 with a list of the user's Spotify playlists  
**And** each playlist includes: `id`, `name`, `description`, `track_count`, `thumbnail_url`, `owner`  
**And** playlists are ordered by most recently modified (as returned by Spotify API)  

---

### Scenario: List YouTube Music playlists

**Given** YouTube Music is connected  
**When** `GET /api/playlists/ytmusic` is called  
**Then** the response is HTTP 200 with a list of the user's YT Music playlists  
**And** each playlist includes: `id`, `name`, `description`, `track_count`, `thumbnail_url`  
**And** the "Liked Music" playlist is included if accessible  

---

### Scenario: Pagination for large playlist libraries

**Given** a user has more than 50 playlists on Spotify  
**When** `GET /api/playlists/spotify?limit=50&offset=50` is called  
**Then** the response includes the next page of playlists  
**And** the response includes `total`, `limit`, `offset` fields for the client to paginate  

---

### Scenario: Get tracks in a Spotify playlist

**Given** Spotify is connected and playlist `<id>` exists  
**When** `GET /api/playlists/spotify/<id>/tracks` is called  
**Then** the response includes all tracks in the playlist  
**And** each track includes: `id`, `name`, `artists` (list), `album`, `duration_ms`, `isrc` (if available)  

---

### Scenario: Get tracks in a YouTube Music playlist

**Given** YouTube Music is connected and playlist `<id>` exists  
**When** `GET /api/playlists/ytmusic/<id>/tracks` is called  
**Then** the response includes all tracks in the playlist  
**And** each track includes: `id` (videoId), `name`, `artists` (list), `album`, `duration_ms`  
**And** `isrc` is omitted (not available from YT Music)  

---

### Scenario: Track list is paginated for large playlists

**Given** a playlist has more than 100 tracks  
**When** `GET /api/playlists/spotify/<id>/tracks?limit=100&offset=100` is called  
**Then** the second page of tracks is returned  

---

### Scenario: Provider not connected

**Given** Spotify is not connected  
**When** `GET /api/playlists/spotify` is called  
**Then** the response is HTTP 401 with `{ "detail": "spotify not connected" }`  

---

### Scenario: Playlist not found

**Given** Spotify is connected  
**When** `GET /api/playlists/spotify/nonexistent_id/tracks` is called  
**Then** the response is HTTP 404 with `{ "detail": "playlist not found" }`  

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/playlists/{provider}` | List playlists for a provider |
| GET | `/api/playlists/{provider}/{playlist_id}/tracks` | Get tracks in a playlist |

### Query Parameters

`GET /api/playlists/{provider}`
- `limit` (int, default 50, max 100)
- `offset` (int, default 0)

`GET /api/playlists/{provider}/{id}/tracks`
- `limit` (int, default 100, max 500)
- `offset` (int, default 0)

---

## Response Schemas

### Playlist object
```json
{
  "id": "37i9dQZF1DXcBWIGoYBM5M",
  "name": "Today's Top Hits",
  "description": "...",
  "track_count": 50,
  "thumbnail_url": "https://...",
  "owner": "spotify"
}
```

### Track object
```json
{
  "id": "4uLU6hMCjMI75M1A2tKUQC",
  "name": "Never Gonna Give You Up",
  "artists": ["Rick Astley"],
  "album": "Whenever You Need Somebody",
  "duration_ms": 213573,
  "isrc": "GBARL8800183"
}
```
