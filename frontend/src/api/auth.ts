import axios from "axios";

export interface ProviderStatus {
  connected: boolean;
  scope?: string;
}

export interface AuthStatus {
  spotify: ProviderStatus;
  ytmusic: ProviderStatus;
}

export const authApi = {
  getStatus: (): Promise<AuthStatus> =>
    axios.get<AuthStatus>("/api/music/status").then((r) => r.data),

  connectSpotify: () => {
    window.location.href = "http://127.0.0.1:8000/api/music/spotify/connect";
  },

  connectYTMusic: () => {
    window.location.href = "/api/music/ytmusic/connect";
  },

  disconnect: (provider: "spotify" | "ytmusic"): Promise<void> =>
    axios.delete(`/api/music/${provider}`).then(() => undefined),
};
