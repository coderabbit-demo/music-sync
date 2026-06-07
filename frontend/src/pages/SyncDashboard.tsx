import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { syncApi, type PlaylistPair, type SyncJob } from "../api/sync";

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
    refetchInterval: 5000, // poll every 5 s to pick up job status changes
  });

  const autoCreateFired = useRef(false);

  const createMutation = useMutation({
    mutationFn: syncApi.createPair,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pairs"] });
    },
    onError: (err: unknown) => {
      // 409 means the pair already exists — treat as success
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        queryClient.invalidateQueries({ queryKey: ["pairs"] });
      }
    },
  });

  const deleteMutation = useMutation({
    mutationFn: syncApi.deletePair,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["pairs"] }),
  });

  // Auto-create pair when navigated from Playlists page with preselection.
  // The ref guard prevents React 18 StrictMode's double-mount from firing twice.
  useEffect(() => {
    if (preselect?.spotify_playlist_id && preselect?.ytmusic_playlist_id && !autoCreateFired.current) {
      autoCreateFired.current = true;
      createMutation.mutate({
        spotify_playlist_id: preselect.spotify_playlist_id,
        ytmusic_playlist_id: preselect.ytmusic_playlist_id,
        sync_direction: "spotify_to_yt",
      });
      // Clear location state so refresh doesn't re-trigger
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
        <div style={styles.error}>
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

function PairCard({
  pair,
  onDelete,
  onRefresh,
}: {
  pair: PlaylistPair;
  onDelete: () => void;
  onRefresh: () => void;
}) {
  const queryClient = useQueryClient();
  const [showJobs, setShowJobs] = useState(false);
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

  // Poll the active job until it leaves "running"
  const { data: activeJob } = useQuery({
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
    queryFn: () => syncApi.listJobs(pair.id, 5),
    enabled: showJobs,
  });

  const dirLabel: Record<string, string> = {
    spotify_to_yt: "Spotify → YT Music",
    yt_to_spotify: "YT Music → Spotify",
    bidirectional: "Bidirectional",
  };

  const isBusy = syncMutation.isPending || activeJob?.status === "running" || activeJob?.status === "pending";

  return (
    <div style={styles.card}>
      <div style={styles.cardTop}>
        <div style={styles.cardNames}>
          <strong>{pair.spotify_playlist_name}</strong>
          <span style={styles.arrow}>{dirLabel[pair.sync_direction]}</span>
          <strong>{pair.ytmusic_playlist_name}</strong>
        </div>
        <button style={styles.deleteBtn} onClick={onDelete} title="Remove pair">
          ✕
        </button>
      </div>

      <div style={styles.cardMeta}>
        {pair.last_synced_at ? (
          <span style={styles.muted}>
            Last synced: {new Date(pair.last_synced_at).toLocaleString()}
          </span>
        ) : (
          <span style={styles.muted}>Never synced</span>
        )}
      </div>

      {activeJob && (isBusy || activeJob.status === "completed" || activeJob.status === "failed") && (
        <div style={{ ...styles.jobStatus, background: statusColor(activeJob.status) }}>
          {activeJob.status === "running" || activeJob.status === "pending"
            ? "Syncing…"
            : activeJob.status === "completed"
            ? `Done — ${activeJob.tracks_added} added, ${activeJob.tracks_skipped} skipped, ${activeJob.tracks_failed} not found`
            : `Failed: ${activeJob.error_message ?? "unknown error"}`}
        </div>
      )}

      <div style={styles.cardActions}>
        <button
          style={{ ...styles.btn, background: "#333", color: "#fff", opacity: isBusy ? 0.6 : 1 }}
          onClick={() => syncMutation.mutate()}
          disabled={isBusy}
        >
          {isBusy ? "Syncing…" : "Sync Now"}
        </button>
        <button style={{ ...styles.btn, background: "#f0f0f0" }} onClick={() => setShowJobs((v) => !v)}>
          {showJobs ? "Hide History" : "History"}
        </button>
      </div>

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
            <option key={h} value={h}>
              {h < 24 ? `${h}h` : `${h / 24}d`}
            </option>
          ))}
        </select>
      </div>

      {showJobs && (
        <div style={styles.jobHistory}>
          {jobs.length === 0 && <p style={styles.muted}>No sync history yet.</p>}
          {jobs.map((job) => (
            <div key={job.id} style={styles.jobRow}>
              <span style={{ ...styles.statusDot, background: statusColor(job.status) }} />
              <span style={styles.muted}>{new Date(job.created_at).toLocaleString()}</span>
              <span>{job.triggered_by === "scheduler" ? "Auto" : "Manual"}</span>
              <span>{job.tracks_added} added / {job.tracks_skipped} skipped / {job.tracks_failed} not found</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    completed: "#e8f5e9",
    failed: "#ffebee",
    running: "#fff8e1",
    pending: "#fff8e1",
  };
  return map[status] ?? "#f5f5f5";
}

const styles: Record<string, React.CSSProperties> = {
  page: { fontFamily: "system-ui, sans-serif", padding: "1.5rem", maxWidth: "860px", margin: "0 auto" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" },
  title: { fontSize: "1.5rem", fontWeight: 700, margin: 0 },
  navBtn: { padding: "0.5rem 1rem", background: "#f0f0f0", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: 600 },
  addBtn: { padding: "0.6rem 1.2rem", background: "#333", color: "#fff", border: "none", borderRadius: "8px", cursor: "pointer", fontWeight: 600 },
  pairList: { display: "flex", flexDirection: "column", gap: "1rem" },
  card: { background: "#fff", border: "1px solid #e0e0e0", borderRadius: "12px", padding: "1.25rem", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" },
  cardTop: { display: "flex", justifyContent: "space-between", alignItems: "flex-start" },
  cardNames: { display: "flex", flexWrap: "wrap", gap: "0.4rem", alignItems: "center", fontSize: "0.95rem" },
  arrow: { color: "#888", fontSize: "0.8rem" },
  deleteBtn: { background: "none", border: "none", cursor: "pointer", color: "#bbb", fontSize: "1rem", padding: "0 4px" },
  cardMeta: { marginTop: "0.4rem" },
  jobStatus: { marginTop: "0.75rem", padding: "0.5rem 0.75rem", borderRadius: "8px", fontSize: "0.85rem" },
  cardActions: { marginTop: "0.75rem", display: "flex", gap: "0.6rem" },
  btn: { padding: "0.5rem 1rem", border: "none", borderRadius: "8px", fontWeight: 600, cursor: "pointer", fontSize: "0.85rem" },
  scheduleRow: { marginTop: "0.75rem", display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.85rem" },
  switchLabel: { display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" },
  select: { padding: "0.25rem 0.5rem", borderRadius: "6px", border: "1px solid #ccc", fontSize: "0.85rem" },
  jobHistory: { marginTop: "0.75rem", borderTop: "1px solid #f0f0f0", paddingTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.4rem" },
  jobRow: { display: "flex", gap: "0.75rem", alignItems: "center", fontSize: "0.82rem", flexWrap: "wrap" },
  statusDot: { width: 8, height: 8, borderRadius: "50%", flexShrink: 0 },
  empty: { textAlign: "center", padding: "3rem", color: "#666" },
  muted: { color: "#888", fontSize: "0.85rem" },
  error: { background: "#ffebee", color: "#c62828", padding: "0.75rem 1rem", borderRadius: "8px", marginBottom: "1rem" },
};
