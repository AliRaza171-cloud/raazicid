import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Disasters from "./pages/Disasters";
import DonationDetail from "./pages/DonationDetail";
import Donations from "./pages/Donations";
import Flags from "./pages/Flags";
import Login from "./pages/Login";
import NeedFinder from "./pages/NeedFinder";
import NeedsMap from "./pages/NeedsMap";
import Points from "./pages/Points";
import Reports from "./pages/Reports";
import Riders from "./pages/Riders";
import Seasonal from "./pages/Seasonal";
import Tracking from "./pages/Tracking";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="disasters" element={<Disasters />} />
        <Route path="donations" element={<Donations />} />
        <Route path="donations/:id" element={<DonationDetail />} />
        <Route path="tracking" element={<Tracking />} />
        <Route path="riders" element={<Riders />} />
        <Route path="points" element={<Points />} />
        <Route path="needs" element={<NeedsMap />} />
        <Route path="need-finder" element={<NeedFinder />} />
        <Route path="reports" element={<Reports />} />
        <Route path="seasonal" element={<Seasonal />} />
        <Route path="flags" element={<Flags />} />
      </Route>
    </Routes>
  );
}
