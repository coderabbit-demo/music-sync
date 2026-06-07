import axios from "axios";

export interface Playlist {
  id: string;
  name: string;
  description?: string;
  track_count: number;
  thumbnail_url?: string;
  owner?: string;
}

export interface PlaylistPage {
  items: Playlist[];
  total: number;
  limit: number;
  offset: number;
}

export interface Track {
  id: string;
  name: string;
  artists: string[];
  album?: string;
  duration_ms?: number;
  isrc?: string;
}

export interface TrackPage {
  items: Track[];
  total: number;
  limit: number;
  offset: number;
}

type Provider = "spotify" | "ytmusic";

export const playlistsApi = {
  listPlaylists: (provider: Provider, limit = 50, offset = 0): Promise<PlaylistPage> =>
    axios
      .get<PlaylistPage>(`/api/playlists/${provider}`, { params: { limit, offset } })
      .then((r) => r.data),

  getPlaylistTracks: (provider: Provider, playlistId: string, limit = 100, offset = 0): Promise<TrackPage> =>
    axios
      .get<TrackPage>(`/api/playlists/${provider}/${playlistId}/tracks`, {
        params: { limit, offset },
      })
      .then((r) => r.data),
};
