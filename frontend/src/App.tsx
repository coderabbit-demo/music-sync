import { Routes, Route, Navigate } from "react-router-dom";
import ConnectPage from "./pages/Connect";
import PlaylistsPage from "./pages/Playlists";
import SyncDashboardPage from "./pages/SyncDashboard";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/connect" replace />} />
      <Route path="/connect" element={<ConnectPage />} />
      <Route path="/playlists" element={<PlaylistsPage />} />
      <Route path="/sync" element={<SyncDashboardPage />} />
    </Routes>
  );
}
