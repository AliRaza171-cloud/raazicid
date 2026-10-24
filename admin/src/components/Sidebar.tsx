import { NavLink } from "react-router-dom";
import { useAuth } from "../lib/auth";

type Item = { to: string; label: string };

const groups: { label: string; items: Item[] }[] = [
  {
    label: "Operations",
    items: [
      { to: "/", label: "Dashboard" },
      { to: "/disasters", label: "Disaster alerts" },
      { to: "/donations", label: "Donations" },
      { to: "/tracking", label: "Live tracking" },
      { to: "/riders", label: "Riders" },
      { to: "/points", label: "Distribution points" },
    ],
  },
  {
    label: "Planning",
    items: [
      { to: "/needs", label: "Needs by area" },
      { to: "/need-finder", label: "Need finder" },
      { to: "/reports", label: "Report library" },
      { to: "/seasonal", label: "Seasonal planner" },
    ],
  },
  { label: "Trust", items: [{ to: "/flags", label: "Fraud flags" }] },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  return (
    <nav className="side" aria-label="Admin">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0F6B5C" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" />
          </svg>
        </span>
        RAAZICID
      </div>
      {groups.map((g) => (
        <div className="side-group" key={g.label}>
          <span className="side-label">{g.label}</span>
          {g.items.map((it) => (
            <NavLink key={it.to} to={it.to} end={it.to === "/"} className={({ isActive }) => (isActive ? "side-link active" : "side-link")}>
              {it.label}
            </NavLink>
          ))}
        </div>
      ))}
      <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
        {user && <span style={{ padding: "0 12px", fontSize: 13, color: "#8fb0a6" }}>Signed in as {user.full_name}</span>}
        <button type="button" onClick={() => void logout()} className="side-link" style={{ border: 0, background: "none", font: "inherit", fontWeight: 600, cursor: "pointer", textAlign: "left" }}>
          Log out
        </button>
      </div>
    </nav>
  );
}
