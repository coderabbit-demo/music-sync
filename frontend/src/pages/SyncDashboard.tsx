import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { syncApi, type PlaylistPair, type SyncJob, type SyncJobDetail, type SyncJobTrack } from "../api/sync";

export default function SyncDashboardPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const preselect = location.state as {
    spotify_playlist_id?: string;
    ytmusic_playlist_id?: string;
    spotify_playlist_name?: string;
    ytmusic_playlist_name?: string;
  } | null;

  const { data: pairs = [], isLoading } = useQuery({
    queryKey: ["pairs"],
    queryFn: syncApi.listPairs,
    refetchInterval: 5000,
  });

  const autoCreateFired = useRef(false);

  const createMutation = useMutation({
    mutationFn: syncApi.createPair,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pairs"] }),
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) queryClient.invalidateQueries({ queryKey: ["pairs"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: syncApi.deletePair,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pairs"] }),
  });

  useEffect(() => {
    if (preselect?.spotify_playlist_id && preselect?.ytmusic_playlist_id && !autoCreateFired.current) {
      autoCreateFired.current = true;
      createMutation.mutate({
        spotify_playlist_id: preselect.spotify_playlist_id,
        ytmusic_playlist_id: preselect.ytmusic_playlist_id,
        sync_direction: "spotify_to_yt",
      });
      navigate("/sync", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Sync Dashboard</h1>
        <button style={styles.navBtn} onClick={() => navigate("/playlists")}>
          ← Browse Playlists
        </button>
      </header>

      {createMutation.isError && (
        <div style={styles.errorBanner}>
          {(createMutation.error as Error)?.message ?? "Failed to create pair"}
        </div>
      )}

      {isLoading && <p style={styles.muted}>Loading pairs…</p>}
      {!isLoading && pairs.length === 0 && (
        <div style={styles.empty}>
          <p>No playlist pairs yet.</p>
          <button style={styles.addBtn} onClick={() => navigate("/playlists")}>
            Browse Playlists to Create a Pair
          </button>
        </div>
      )}

      <div style={styles.pairList}>
        {pairs.map((pair) => (
          <PairCard
            key={pair.id}
            pair={pair}
            onDelete={() => deleteMutation.mutate(pair.id)}
            onRefresh={() => queryClient.invalidateQueries({ queryKey: ["pairs"] })}
          />
        ))}
      </div>
    </div>
  );
}

// ── Pair card ─────────────────────────────────────────────────────────────────

function PairCard({ pair, onDelete, onRefresh }: { pair: PlaylistPair; onDelete: () => void; onRefresh: () => void }) {
  const queryClient = useQueryClient();
  const [showHistory, setShowHistory] = useState(false);
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [pollingJobId, setPollingJobId] = useState<number | null>(null);

  const syncMutation = useMutation({
    mutationFn: () => syncApi.triggerSync(pair.id),
    onSuccess: ({ job_id }) => {
      setPollingJobId(job_id);
      queryClient.invalidateQueries({ queryKey: ["jobs", pair.id] });
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: (body: { auto_sync?: boolean; sync_interval_hours?: number }) =>
      syncApi.updateSchedule(pair.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pairs"] });
      onRefresh();
    },
  });

  // Poll the active job including its tracks until it finishes
  const { data: activeJob } = useQuery<SyncJobDetail>({
    queryKey: ["job", pollingJobId],
    queryFn: () => syncApi.getJob(pollingJobId!),
    enabled: pollingJobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "running" || status === "pending" ? 2000 : false;
    },
  });

  useEffect(() => {
    if (activeJob && activeJob.status !== "running" && activeJob.status !== "pending") {
      setPollingJobId(null);
      queryClient.invalidateQueries({ queryKey: ["jobs", pair.id] });
      queryClient.invalidateQueries({ queryKey: ["pairs"] });
    }
  }, [activeJob?.status]);

  const { data: jobs = [] } = useQuery({
    queryKey: ["jobs", pair.id],
    queryFn: () => syncApi.listJobs(pair.id, 10),
    enabled: showHistory,
  });

  const dirLabel: Record<string, string> = {
    spotify_to_yt: "Spotify → YT Music",
    yt_to_spotify: "YT Music → Spotify",
    bidirectional: "↔ Bidirectional",
  };

  const isBusy = syncMutation.isPending || activeJob?.status === "running" || activeJob?.status === "pending";
  const isActive = isBusy || (activeJob?.status === "completed" || activeJob?.status === "failed");

  return (
    <div style={styles.card}>
      {/* Header row */}
      <div style={styles.cardTop}>
        <div style={styles.cardNames}>
          <span style={styles.spotifyTag}>Spotify</span>
          <strong>{pair.spotify_playlist_name}</strong>
          <span style={styles.dirChip}>{dirLabel[pair.sync_direction]}</span>
          <span style={styles.ytTag}>YT Music</span>
          <strong>{pair.ytmusic_playlist_name}</strong>
        </div>
        <button style={styles.deleteBtn} onClick={onDelete} title="Remove pair">✕</button>
      </div>

      {/* Last synced */}
      <div style={styles.cardMeta}>
        {pair.last_synced_at
          ? <span style={styles.muted}>Last synced: {new Date(pair.last_synced_at).toLocaleString()}</span>
          : <span style={styles.muted}>Never synced</span>}
      </div>

      {/* Active job status banner */}
      {isActive && activeJob && (
        <div style={{ ...styles.statusBanner, background: statusBg(activeJob.status) }}>
          {activeJob.status === "running" || activeJob.status === "pending" ? (
            <span>⟳ Syncing… {activeJob.tracks.length} track{activeJob.tracks.length !== 1 ? "s" : ""} processed</span>
          ) : activeJob.status === "completed" ? (
            <span>✓ Done — {activeJob.tracks_added} added, {activeJob.tracks_skipped} already in sync, {activeJob.tracks_failed} not found</span>
          ) : (
            <span>✗ Failed: {activeJob.error_message ?? "unknown error"}</span>
          )}
        </div>
      )}

      {/* Live track list — shown while job is active */}
      {isActive && activeJob && activeJob.tracks.length > 0 && (
        <TrackList
          tracks={activeJob.tracks}
          isRunning={activeJob.status === "running" || activeJob.status === "pending"}
        />
      )}

      {/* Action buttons */}
      <div style={styles.cardActions}>
        <button
          style={{ ...styles.btn, background: "#333", color: "#fff", opacity: isBusy ? 0.6 : 1 }}
          onClick={() => syncMutation.mutate()}
          disabled={isBusy}
        >
          {isBusy ? "Syncing…" : "Sync Now"}
        </button>
        <button
          style={{ ...styles.btn, background: "#f0f0f0" }}
          onClick={() => setShowHistory((v) => !v)}
        >
          {showHistory ? "Hide History" : "History"}
        </button>
      </div>

      {/* Schedule controls */}
      <div style={styles.scheduleRow}>
        <label style={styles.switchLabel}>
          <input
            type="checkbox"
            checked={pair.auto_sync}
            onChange={(e) => scheduleMutation.mutate({ auto_sync: e.target.checked })}
          />
          Auto-sync every
        </label>
        <select
          value={pair.sync_interval_hours}
          disabled={!pair.auto_sync}
          onChange={(e) => scheduleMutation.mutate({ sync_interval_hours: Number(e.target.value) })}
          style={styles.select}
        >
          {[1, 3, 6, 12, 24, 48, 72, 168].map((h) => (
            <option key={h} value={h}>{h < 24 ? `${h}h` : `${h / 24}d`}</option>
          ))}
        </select>
      </div>

      {/* Job history */}
      {showHistory && (
        <div style={styles.historySection}>
          {jobs.length === 0 && <p style={styles.muted}>No sync history yet.</p>}
          {jobs.map((job) => (
            <HistoryJobRow
              key={job.id}
              job={job}
              expanded={expandedJobId === job.id}
              onToggle={() => setExpandedJobId((id) => (id === job.id ? null : job.id))}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── History job row with expandable track details ─────────────────────────────

function HistoryJobRow({ job, expanded, onToggle }: { job: SyncJob; expanded: boolean; onToggle: () => void }) {
  const { data: detail } = useQuery<SyncJobDetail>({
    queryKey: ["job", job.id],
    queryFn: () => syncApi.getJob(job.id),
    enabled: expanded,
  });

  return (
    <div style={styles.historyJobBlock}>
      <div style={styles.historyJobRow} onClick={onToggle}>
        <span style={{ ...styles.statusDot, background: statusColor(job.status) }} />
        <span style={styles.muted}>{new Date(job.created_at).toLocaleString()}</span>
        <span>{job.triggered_by === "scheduler" ? "Auto" : "Manual"}</span>
        <span>
          {job.tracks_added} added / {job.tracks_skipped} skipped / {job.tracks_failed} not found
        </span>
        <span style={styles.expandToggle}>{expanded ? "▲" : "▼"}</span>
      </div>
      {expanded && (
        detail
          ? <TrackList tracks={detail.tracks} isRunning={false} />
          : <p style={{ ...styles.muted, padding: "0.5rem 0" }}>Loading…</p>
      )}
    </div>
  );
}

// ── Track list ────────────────────────────────────────────────────────────────

function TrackList({ tracks, isRunning }: { tracks: SyncJobTrack[]; isRunning: boolean }) {
  return (
    <div style={styles.trackListWrapper}>
      <div style={styles.trackListHeader}>
        <span style={styles.trackListTitle}>Tracks</span>
        <span style={styles.muted}>{tracks.length} processed</span>
      </div>
      <div style={styles.trackScroll}>
        {tracks.map((track, i) => (
          <TrackRow
            key={track.id}
            track={track}
            index={i}
            isCurrent={isRunning && i === tracks.length - 1}
          />
        ))}
        {isRunning && (
          <div style={styles.trackRowPending}>
            <span style={styles.pendingDot} />
            <span style={{ ...styles.muted, fontStyle: "italic" }}>Processing next track…</span>
          </div>
        )}
      </div>
    </div>
  );
}

function TrackRow({ track, index, isCurrent }: { track: SyncJobTrack; index: number; isCurrent: boolean }) {
  const dirLabel = track.source_provider === "spotify"
    ? { from: "Spotify", to: "YT Music", fromColor: "#1DB954", toColor: "#FF0000" }
    : { from: "YT Music", to: "Spotify", fromColor: "#FF0000", toColor: "#1DB954" };

  const statusInfo = trackStatusInfo(track.status);

  return (
    <div style={{
      ...styles.trackRow,
      background: isCurrent ? "#fffbea" : "transparent",
      borderLeft: isCurrent ? "3px solid #f5a623" : "3px solid transparent",
    }}>
      <span style={styles.trackIndex}>{index + 1}</span>

      {/* Source info */}
      <div style={styles.trackSource}>
        <span style={{ ...styles.providerTag, color: dirLabel.fromColor }}>
          {dirLabel.from}
        </span>
        <span style={styles.trackName}>{track.source_track_name}</span>
        {track.source_artist && (
          <span style={styles.trackArtist}>{track.source_artist}</span>
        )}
      </div>

      {/* Direction arrow */}
      <span style={{ ...styles.trackArrow, color: dirLabel.toColor }}>→</span>
      <span style={{ ...styles.providerTag, color: dirLabel.toColor, marginRight: "0.4rem" }}>
        {dirLabel.to}
      </span>

      {/* Match result */}
      <div style={styles.trackTarget}>
        {track.target_track_name && (
          <span style={styles.targetName}>{track.target_track_name}</span>
        )}
        {track.match_method && track.match_method !== "not_found" && (
          <span style={styles.matchMethod}>
            {track.match_method === "isrc" ? "ISRC" : `fuzzy ${track.match_score != null ? Math.round(track.match_score) + "%" : ""}`}
          </span>
        )}
      </div>

      {/* Status badge */}
      <span style={{ ...styles.statusBadge, background: statusInfo.bg, color: statusInfo.color }}>
        {statusInfo.label}
      </span>

      {/* Error detail */}
      {track.error && (
        <span style={styles.trackError} title={track.error}>⚠</span>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function trackStatusInfo(status: string) {
  switch (status) {
    case "added":    return { label: "added",    bg: "#e8f5e9", color: "#2e7d32" };
    case "skipped":  return { label: "in sync",  bg: "#f5f5f5", color: "#757575" };
    case "not_found":return { label: "not found",bg: "#fff3e0", color: "#e65100" };
    case "error":    return { label: "error",    bg: "#ffebee", color: "#c62828" };
    default:         return { label: status,     bg: "#f5f5f5", color: "#888"    };
  }
}

function statusBg(status: string): string {
  return { completed: "#e8f5e9", failed: "#ffebee", running: "#fff8e1", pending: "#fff8e1" }[status] ?? "#f5f5f5";
}

function statusColor(status: string): string {
  return { completed: "#4caf50", failed: "#f44336", running: "#ff9800", pending: "#ff9800" }[status] ?? "#bbb";
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  page: { fontFamily: "system-ui, sans-serif", padding: "1.5rem", maxWidth: "960px", margin: "0 auto" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" },
  title: { fontSize: "1.5rem", fontWeight: 700, margin: 0 },
  navBtn: { padding: "0.5rem 1rem", background: "#f0f0f0", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: 600 },
  addBtn: { padding: "0.6rem 1.2rem", background: "#333", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: 600 },
  pairList: { display: "flex", flexDirection: "column", gap: "1.25rem" },
  empty: { textAlign: "center", padding: "3rem", color: "#666" },
  errorBanner: { background: "#ffebee", color: "#c62828", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1rem" },
  muted: { color: "#888", fontSize: "0.82rem" },

  // Card
  card: { background: "#fff", border: "1px solid #e0e0e0", borderRadius: "12px", padding: "1.25rem", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" },
  cardTop: { display: "flex", justifyContent: "space-between", alignItems: "flex-start" },
  cardNames: { display: "flex", flexWrap: "wrap", gap: "0.4rem", alignItems: "center", fontSize: "0.9rem" },
  spotifyTag: { fontSize: "0.7rem", fontWeight: 700, color: "#1DB954", background: "#f0fdf4", padding: "1px 6px", borderRadius: "4px", border: "1px solid #bbf7d0" },
  ytTag: { fontSize: "0.7rem", fontWeight: 700, color: "#c62828", background: "#fff5f5", padding: "1px 6px", borderRadius: "4px", border: "1px solid #fecaca" },
  dirChip: { fontSize: "0.75rem", color: "#666", background: "#f5f5f5", padding: "2px 8px", borderRadius: "12px", border: "1px solid #e0e0e0" },
  deleteBtn: { background: "none", border: "none", cursor: "pointer", color: "#bbb", fontSize: "1rem", padding: "0 4px" },
  cardMeta: { marginTop: "0.4rem" },
  statusBanner: { marginTop: "0.75rem", padding: "0.5rem 0.75rem", borderRadius: "8px", fontSize: "0.85rem" },
  cardActions: { marginTop: "0.75rem", display: "flex", gap: "0.6rem" },
  btn: { padding: "0.5rem 1rem", border: "none", borderRadius: "8px", fontWeight: 600, cursor: "pointer", fontSize: "0.85rem" },
  scheduleRow: { marginTop: "0.75rem", display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.85rem" },
  switchLabel: { display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" },
  select: { padding: "0.25rem 0.5rem", borderRadius: "6px", border: "1px solid #ccc", fontSize: "0.85rem" },

  // History
  historySection: { marginTop: "0.75rem", borderTop: "1px solid #f0f0f0", paddingTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.25rem" },
  historyJobBlock: { borderRadius: "6px", overflow: "hidden", border: "1px solid #f0f0f0" },
  historyJobRow: { display: "flex", gap: "0.75rem", alignItems: "center", fontSize: "0.82rem", flexWrap: "wrap", padding: "0.4rem 0.6rem", cursor: "pointer", background: "#fafafa" },
  statusDot: { width: 8, height: 8, borderRadius: "50%", flexShrink: 0 },
  expandToggle: { marginLeft: "auto", color: "#aaa", fontSize: "0.7rem" },

  // Track list
  trackListWrapper: { marginTop: "0.75rem", border: "1px solid #eeeeee", borderRadius: "8px", overflow: "hidden" },
  trackListHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0.75rem", background: "#f9f9f9", borderBottom: "1px solid #eee" },
  trackListTitle: { fontSize: "0.8rem", fontWeight: 700, color: "#555" },
  trackScroll: { maxHeight: "320px", overflowY: "auto" },

  // Track row
  trackRow: { display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.35rem 0.75rem", borderBottom: "1px solid #fafafa", transition: "background 0.15s" },
  trackRowPending: { display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.75rem", color: "#aaa" },
  pendingDot: { width: 8, height: 8, borderRadius: "50%", background: "#f5a623", animation: "pulse 1s infinite" },
  trackIndex: { fontSize: "0.7rem", color: "#ccc", minWidth: "1.6rem", textAlign: "right", flexShrink: 0 },
  trackSource: { display: "flex", flexDirection: "column", minWidth: 0, flex: "0 0 200px" },
  providerTag: { fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.02em" },
  trackName: { fontSize: "0.82rem", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  trackArtist: { fontSize: "0.72rem", color: "#888", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  trackArrow: { fontSize: "0.9rem", flexShrink: 0 },
  trackTarget: { display: "flex", flexDirection: "column", flex: 1, minWidth: 0 },
  targetName: { fontSize: "0.82rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#444" },
  matchMethod: { fontSize: "0.68rem", color: "#aaa" },
  statusBadge: { fontSize: "0.68rem", fontWeight: 700, padding: "1px 6px", borderRadius: "4px", flexShrink: 0, whiteSpace: "nowrap" },
  trackError: { fontSize: "0.8rem", cursor: "help", flexShrink: 0 },
};
