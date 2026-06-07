import { useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { authApi } from "../api/auth";

export default function ConnectPage() {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: status, isLoading } = useQuery({
    queryKey: ["authStatus"],
    queryFn: authApi.getStatus,
    refetchInterval: false,
  });

  // Invalidate status after returning from OAuth redirect
  useEffect(() => {
    if (searchParams.get("connected")) {
      queryClient.invalidateQueries({ queryKey: ["authStatus"] });
    }
  }, [searchParams, queryClient]);

  const disconnectMutation = useMutation({
    mutationFn: (provider: "spotify" | "ytmusic") => authApi.disconnect(provider),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["authStatus"] }),
  });

  const bothConnected = status?.spotify.connected && status?.ytmusic.connected;

  if (isLoading) return <div style={styles.page}>Loading…</div>;

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>music-sync</h1>
      <p style={styles.subtitle}>Connect your streaming accounts to get started.</p>

      <div style={styles.cards}>
        <ProviderCard
          name="Spotify"
          color="#1DB954"
          connected={status?.spotify.connected ?? false}
          onConnect={authApi.connectSpotify}
          onDisconnect={() => disconnectMutation.mutate("spotify")}
          disconnecting={disconnectMutation.isPending}
        />
        <ProviderCard
          name="YouTube Music"
          color="#FF0000"
          connected={status?.ytmusic.connected ?? false}
          onConnect={authApi.connectYTMusic}
          onDisconnect={() => disconnectMutation.mutate("ytmusic")}
          disconnecting={disconnectMutation.isPending}
        />
      </div>

      {bothConnected && (
        <button style={styles.continueBtn} onClick={() => navigate("/playlists")}>
          Browse Playlists →
        </button>
      )}
    </div>
  );
}

interface ProviderCardProps {
  name: string;
  color: string;
  connected: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  disconnecting: boolean;
}

function ProviderCard({ name, color, connected, onConnect, onDisconnect, disconnecting }: ProviderCardProps) {
  return (
    <div style={{ ...styles.card, borderColor: connected ? color : "#e0e0e0" }}>
      <div style={styles.cardHeader}>
        <span style={styles.cardName}>{name}</span>
        <span style={{ ...styles.badge, background: connected ? color : "#9e9e9e" }}>
          {connected ? "Connected" : "Not connected"}
        </span>
      </div>
      {connected ? (
        <button
          style={{ ...styles.btn, background: "#f5f5f5", color: "#333" }}
          onClick={onDisconnect}
          disabled={disconnecting}
        >
          Disconnect
        </button>
      ) : (
        <button style={{ ...styles.btn, background: color, color: "#fff" }} onClick={onConnect}>
          Connect {name}
        </button>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "system-ui, sans-serif",
    background: "#fafafa",
    padding: "2rem",
  },
  title: { fontSize: "2rem", fontWeight: 700, margin: 0 },
  subtitle: { color: "#666", marginTop: "0.5rem", marginBottom: "2rem" },
  cards: { display: "flex", gap: "1.5rem", flexWrap: "wrap", justifyContent: "center" },
  card: {
    background: "#fff",
    border: "2px solid",
    borderRadius: "12px",
    padding: "1.5rem",
    width: "260px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "1.25rem",
  },
  cardName: { fontWeight: 600, fontSize: "1rem" },
  badge: {
    fontSize: "0.75rem",
    fontWeight: 600,
    color: "#fff",
    padding: "2px 8px",
    borderRadius: "99px",
  },
  btn: {
    width: "100%",
    padding: "0.6rem 1rem",
    border: "none",
    borderRadius: "8px",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: "0.9rem",
  },
  continueBtn: {
    marginTop: "2rem",
    padding: "0.75rem 2rem",
    background: "#333",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontWeight: 600,
    fontSize: "1rem",
    cursor: "pointer",
  },
};
