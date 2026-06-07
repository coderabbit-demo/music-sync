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
    axios.get<AuthStatus>("/api/auth/status").then((r) => r.data),

  connectSpotify: () => {
    window.location.href = "/api/auth/spotify/connect";
  },

  connectYTMusic: () => {
    window.location.href = "/api/auth/ytmusic/connect";
  },

  disconnect: (provider: "spotify" | "ytmusic"): Promise<void> =>
    axios.delete(`/api/auth/${provider}`).then(() => undefined),
};
