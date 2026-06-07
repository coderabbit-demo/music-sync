import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { playlistsApi, type Playlist } from "../api/playlists";

export default function PlaylistsPage() {
  const navigate = useNavigate();
  const [selectedSpotify, setSelectedSpotify] = useState<Playlist | null>(null);
  const [selectedYT, setSelectedYT] = useState<Playlist | null>(null);

  const { data: spotifyData, isLoading: spLoading, error: spError } = useQuery({
    queryKey: ["playlists", "spotify"],
    queryFn: () => playlistsApi.listPlaylists("spotify", 50),
  });

  const { data: ytData, isLoading: ytLoading, error: ytError } = useQuery({
    queryKey: ["playlists", "ytmusic"],
    queryFn: () => playlistsApi.listPlaylists("ytmusic", 50),
  });

  function handleSync() {
    if (!selectedSpotify || !selectedYT) return;
    navigate("/sync", {
      state: {
        spotify_playlist_id: selectedSpotify.id,
        spotify_playlist_name: selectedSpotify.name,
        ytmusic_playlist_id: selectedYT.id,
        ytmusic_playlist_name: selectedYT.name,
      },
    });
  }

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Select Playlists to Sync</h1>
        <div style={styles.headerActions}>
          {selectedSpotify && selectedYT && (
            <button style={styles.syncBtn} onClick={handleSync}>
              Sync "{selectedSpotify.name}" → "{selectedYT.name}"
            </button>
          )}
          <button style={styles.navBtn} onClick={() => navigate("/sync")}>
            Sync Dashboard
          </button>
        </div>
      </header>

      <div style={styles.columns}>
        <ProviderColumn
          title="Spotify"
          color="#1DB954"
          playlists={spotifyData?.items ?? []}
          loading={spLoading}
          error={spError ? "Failed to load Spotify playlists" : null}
          selected={selectedSpotify}
          onSelect={setSelectedSpotify}
        />
        <ProviderColumn
          title="YouTube Music"
          color="#FF0000"
          playlists={ytData?.items ?? []}
          loading={ytLoading}
          error={ytError ? "Failed to load YouTube Music playlists" : null}
          selected={selectedYT}
          onSelect={setSelectedYT}
        />
      </div>
    </div>
  );
}

interface ColumnProps {
  title: string;
  color: string;
  playlists: Playlist[];
  loading: boolean;
  error: string | null;
  selected: Playlist | null;
  onSelect: (p: Playlist) => void;
}

function ProviderColumn({ title, color, playlists, loading, error, selected, onSelect }: ColumnProps) {
  return (
    <div style={styles.column}>
      <h2 style={{ ...styles.columnTitle, borderColor: color }}>{title}</h2>
      {loading && <p style={styles.muted}>Loading…</p>}
      {error && <p style={styles.error}>{error}</p>}
      {!loading && !error && playlists.length === 0 && (
        <p style={styles.muted}>No playlists found.</p>
      )}
      <ul style={styles.list}>
        {playlists.map((p) => (
          <li
            key={p.id}
            style={{
              ...styles.item,
              borderColor: selected?.id === p.id ? color : "transparent",
              background: selected?.id === p.id ? `${color}15` : "#fff",
            }}
            onClick={() => onSelect(p)}
          >
            {p.thumbnail_url && (
              <img src={p.thumbnail_url} alt="" style={styles.thumb} />
            )}
            <div style={styles.itemText}>
              <span style={styles.itemName}>{p.name}</span>
              <span style={styles.itemMeta}>{p.track_count} tracks</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    fontFamily: "system-ui, sans-serif",
    padding: "1.5rem",
    maxWidth: "1100px",
    margin: "0 auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "1.5rem",
    flexWrap: "wrap",
    gap: "1rem",
  },
  title: { fontSize: "1.5rem", fontWeight: 700, margin: 0 },
  headerActions: { display: "flex", gap: "0.75rem" },
  syncBtn: {
    padding: "0.6rem 1.2rem",
    background: "#333",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontWeight: 600,
    cursor: "pointer",
  },
  navBtn: {
    padding: "0.6rem 1.2rem",
    background: "#f0f0f0",
    color: "#333",
    border: "none",
    borderRadius: "8px",
    fontWeight: 600,
    cursor: "pointer",
  },
  columns: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" },
  column: {},
  columnTitle: {
    fontSize: "1.1rem",
    fontWeight: 700,
    borderLeft: "4px solid",
    paddingLeft: "0.6rem",
    marginTop: 0,
  },
  list: { listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "6px" },
  item: {
    display: "flex",
    alignItems: "center",
    gap: "0.75rem",
    padding: "0.6rem 0.75rem",
    borderRadius: "8px",
    border: "2px solid",
    cursor: "pointer",
    transition: "all 0.15s",
  },
  thumb: { width: 40, height: 40, borderRadius: 4, objectFit: "cover", flexShrink: 0 },
  itemText: { display: "flex", flexDirection: "column" },
  itemName: { fontWeight: 600, fontSize: "0.9rem" },
  itemMeta: { fontSize: "0.75rem", color: "#888" },
  muted: { color: "#888", fontSize: "0.9rem" },
  error: { color: "#c62828", fontSize: "0.9rem" },
};
