import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./lib/auth";
import Dashboard from "./pages/Dashboard";
import DonationDetail from "./pages/DonationDetail";
import Donations from "./pages/Donations";
import Login from "./pages/Login";
import Ngos from "./pages/Ngos";
import Riders from "./pages/Riders";
import Tracking from "./pages/Tracking";

/** Sends signed-out visitors to /login and remembers where they were going. */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <div style={{ padding: 32, color: "var(--muted)" }}>Loading…</div>;
  if (status !== "signedIn") return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<RequireAdmin><Layout /></RequireAdmin>}>
        <Route index element={<Dashboard />} />
        <Route path="donations" element={<Donations />} />
        <Route path="donations/:id" element={<DonationDetail />} />
        <Route path="tracking" element={<Tracking />} />
        <Route path="riders" element={<Riders />} />
        <Route path="ngos" element={<Ngos />} />
        <Route path="points" element={<Navigate to="/ngos" replace />} />
      </Route>
      </Routes>
    </AuthProvider>
  );
}
