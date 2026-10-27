import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import { AuthProvider, useAuth } from "./lib/auth";
import Dashboard from "./pages/Dashboard";
import Disasters from "./pages/Disasters";
import DonationDetail from "./pages/DonationDetail";
import Donations from "./pages/Donations";
import Flags from "./pages/Flags";
import Login from "./pages/Login";
import NeedFinder from "./pages/NeedFinder";
import NeedsMap from "./pages/NeedsMap";
import Ngos from "./pages/Ngos";
import Reports from "./pages/Reports";
import Riders from "./pages/Riders";
import Seasonal from "./pages/Seasonal";
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
        <Route path="disasters" element={<Disasters />} />
        <Route path="donations" element={<Donations />} />
        <Route path="donations/:id" element={<DonationDetail />} />
        <Route path="tracking" element={<Tracking />} />
        <Route path="riders" element={<Riders />} />
        <Route path="ngos" element={<Ngos />} />
        <Route path="points" element={<Navigate to="/ngos" replace />} />
        <Route path="needs" element={<NeedsMap />} />
        <Route path="need-finder" element={<NeedFinder />} />
        <Route path="reports" element={<Reports />} />
        <Route path="seasonal" element={<Seasonal />} />
        <Route path="flags" element={<Flags />} />
      </Route>
      </Routes>
    </AuthProvider>
  );
}
