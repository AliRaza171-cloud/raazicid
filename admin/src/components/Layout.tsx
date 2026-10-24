import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";

export default function Layout() {
  return (
    <div className="shell">
      <div className="shell-side">
        <Sidebar />
      </div>
      <div className="shell-main">
        <Outlet />
      </div>
    </div>
  );
}

export function PageHeader({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <header className="topbar">
      <div style={{ marginRight: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
        <h1>{title}</h1>
        {sub && <span className="sub">{sub}</span>}
      </div>
      {children}
    </header>
  );
}

/** Placeholder body for pages built in later phases. */
export function ComingIn({ phase, what }: { phase: number; what: string }) {
  return (
    <div className="todo">
      <strong>Built in Phase {phase}.</strong> {what} The finished look is on the design canvas.
    </div>
  );
}
