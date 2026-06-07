# Feature Spec: Provider Authentication

## Overview

The user connects their Spotify and YouTube Music accounts via OAuth2. Once connected, the app stores encrypted tokens and auto-refreshes them as needed. The user can disconnect a provider at any time, which deletes stored tokens.

---

## Scenarios

### Scenario: Connect Spotify for the first time

**Given** Spotify is not connected (no row in `provider_tokens` for `spotify`)  
**When** the user clicks "Connect Spotify" in the UI  
**Then** the browser redirects to Spotify's OAuth2 authorization URL  
**And** the URL includes scopes: `playlist-read-private playlist-read-collaborative playlist-modify-private playlist-modify-public`  
**And** the redirect URI is `SPOTIFY_REDIRECT_URI` from env  

**Given** the user approves access on Spotify  
**When** Spotify redirects to `/api/music/spotify/callback?code=<code>&state=<state>`  
**Then** the backend exchanges the code for access and refresh tokens  
**And** tokens are encrypted and upserted into `provider_tokens` for provider `spotify`  
**And** the browser is redirected to the frontend with `?connected=spotify`  

---

### Scenario: Connect YouTube Music for the first time

**Given** YouTube Music is not connected  
**When** the user clicks "Connect YouTube Music"  
**Then** the browser redirects to Google's OAuth2 authorization URL  
**And** the URL includes scopes: `https://www.googleapis.com/auth/youtube`  

**Given** the user approves access on Google  
**When** Google redirects to `/api/music/ytmusic/callback?code=<code>`  
**Then** the backend exchanges the code for access and refresh tokens via `ytmusicapi`  
**And** tokens are stored in `provider_tokens` for provider `ytmusic`  
**And** the browser is redirected to the frontend with `?connected=ytmusic`  

---

### Scenario: OAuth state mismatch (CSRF protection)

**Given** a callback arrives at `/api/music/spotify/callback`  
**When** the `state` parameter does not match the value stored in the session  
**Then** the backend returns HTTP 400  
**And** no token is stored  

---

### Scenario: Check connection status

**Given** Spotify is connected and YouTube Music is not  
**When** `GET /api/music/status` is called  
**Then** the response is:
```json
{
  "spotify": { "connected": true, "scope": "playlist-read-private ..." },
  "ytmusic": { "connected": false }
}
```

---

### Scenario: Token auto-refresh

**Given** the stored Spotify access token is expired  
**When** any API call is made to the Spotify service layer  
**Then** `spotipy` automatically refreshes the token using the refresh token  
**And** the new access token and expiry are updated in `provider_tokens`  

---

### Scenario: Disconnect a provider

**Given** Spotify is connected  
**When** `DELETE /api/music/spotify` is called  
**Then** the `provider_tokens` row for `spotify` is deleted  
**And** `GET /api/music/status` returns `"spotify": { "connected": false }`  
**And** any `playlist_pairs` that reference Spotify playlists are NOT automatically deleted (handled separately)  

---

### Scenario: Access playlist endpoint when provider not connected

**Given** Spotify is not connected  
**When** `GET /api/playlists/spotify` is called  
**Then** the response is HTTP 401 with body `{ "detail": "spotify not connected" }`  

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/music/spotify/connect` | Initiate Spotify OAuth (redirects to Spotify) |
| GET | `/api/music/spotify/callback` | Handle Spotify OAuth callback |
| GET | `/api/music/ytmusic/connect` | Initiate YT Music OAuth (redirects to Google) |
| GET | `/api/music/ytmusic/callback` | Handle YT Music OAuth callback |
| DELETE | `/api/music/{provider}` | Disconnect provider |
| GET | `/api/music/status` | Get connection status for all providers |

---

## State Management Notes

- OAuth `state` parameter (CSRF token) is stored in a server-side session cookie (signed, httponly) during the connect flow and validated on callback
- The session cookie is only used for the OAuth handshake, not for ongoing auth (single-user app needs no login)
