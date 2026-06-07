import axios from "axios";

export interface PlaylistPair {
  id: number;
  spotify_playlist_id: string;
  spotify_playlist_name: string;
  ytmusic_playlist_id: string;
  ytmusic_playlist_name: string;
  sync_direction: "spotify_to_yt" | "yt_to_spotify" | "bidirectional";
  auto_sync: boolean;
  sync_interval_hours: number;
  last_synced_at?: string;
  created_at: string;
}

export interface SyncJob {
  id: number;
  playlist_pair_id: number;
  triggered_by: "manual" | "scheduler";
  status: "pending" | "running" | "completed" | "failed";
  tracks_matched: number;
  tracks_added: number;
  tracks_skipped: number;
  tracks_failed: number;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface SyncJobTrack {
  id: number;
  source_provider: string;
  source_track_name: string;
  source_artist?: string;
  target_track_name?: string;
  match_method?: string;
  match_score?: number;
  status: string;
  error?: string;
}

export interface SyncJobDetail extends SyncJob {
  tracks: SyncJobTrack[];
}

export interface CreatePairRequest {
  spotify_playlist_id: string;
  ytmusic_playlist_id: string;
  sync_direction?: "spotify_to_yt" | "yt_to_spotify" | "bidirectional";
}

export const syncApi = {
  listPairs: (): Promise<PlaylistPair[]> =>
    axios.get<PlaylistPair[]>("/api/sync/pairs").then((r) => r.data),

  createPair: (body: CreatePairRequest): Promise<PlaylistPair> =>
    axios.post<PlaylistPair>("/api/sync/pairs", body).then((r) => r.data),

  deletePair: (id: number): Promise<void> =>
    axios.delete(`/api/sync/pairs/${id}`).then(() => undefined),

  triggerSync: (pairId: number): Promise<{ job_id: number }> =>
    axios.post<{ job_id: number }>(`/api/sync/pairs/${pairId}/run`).then((r) => r.data),

  listJobs: (pairId: number, limit = 10): Promise<SyncJob[]> =>
    axios
      .get<SyncJob[]>(`/api/sync/pairs/${pairId}/jobs`, { params: { limit } })
      .then((r) => r.data),

  getJob: (jobId: number): Promise<SyncJobDetail> =>
    axios.get<SyncJobDetail>(`/api/sync/jobs/${jobId}`).then((r) => r.data),

  updateSchedule: (
    pairId: number,
    body: { auto_sync?: boolean; sync_interval_hours?: number }
  ): Promise<PlaylistPair> =>
    axios.patch<PlaylistPair>(`/api/sync/pairs/${pairId}/schedule`, body).then((r) => r.data),
};
