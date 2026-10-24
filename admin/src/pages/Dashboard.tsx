import { useEffect, useState } from "react";
import { PageHeader, ComingIn } from "../components/Layout";
import { api, API_URL, type AiStats, type AiStatus, type Category, type LocationItem } from "../lib/api";

type Health = { status: string; database?: string; pgvector?: boolean };

/** Phase 1: proves the web app can talk to the backend and the database. */
export default function Dashboard() {
  const [api_, setApi] = useState<"checking" | "ok" | "down">("checking");
  const [db, setDb] = useState<Health | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [provinces, setProvinces] = useState<LocationItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [aiStats, setAiStats] = useState<AiStats | null>(null);

  useEffect(() => {
    api<Health>("/health")
      .then(() => setApi("ok"))
      .catch(() => setApi("down"));
    api<Health>("/health/db")
      .then(setDb)
      .catch((e) => setError(String(e.message ?? e)));
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
    api<LocationItem[]>("/locations").then(setProvinces).catch(() => undefined);
    api<AiStatus>("/ai/status").then(setAi).catch(() => undefined);
    api<AiStats>("/admin/ai/stats").then(setAiStats).catch(() => undefined);
  }, []);

  const chip = (ok: boolean | null) =>
    ok === null ? <span className="chip wait">Checking</span> : ok ? <span className="chip ok">OK</span> : <span className="chip bad">Not reachable</span>;

  return (
    <>
      <PageHeader title="Dashboard" sub="Phase 1 setup check: is everything connected?" />
      <main className="page">
        <section className="grid-kpi">
          <div className="card">
            <div className="kpi-label">Backend API</div>
            <div style={{ marginTop: 8 }}>{chip(api_ === "checking" ? null : api_ === "ok")}</div>
            <div className="sub" style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>{API_URL}</div>
          </div>
          <div className="card">
            <div className="kpi-label">Database (Neon)</div>
            <div style={{ marginTop: 8 }}>{chip(db ? db.database === "reachable" : error ? false : null)}</div>
          </div>
          <div className="card">
            <div className="kpi-label">pgvector (for RAG)</div>
            <div style={{ marginTop: 8 }}>{chip(db ? Boolean(db.pgvector) : error ? false : null)}</div>
          </div>
          <div className="card">
            <div className="kpi-label">Seed data</div>
            <div className="kpi-value">{cats.length} / 12</div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>categories · {provinces.length} provinces</div>
          </div>
        </section>
        {error && <div className="card" style={{ borderColor: "#edb49e" }}>Database check failed: {error}</div>}
        {cats.length > 0 && (
          <section className="card">
            <h2 style={{ margin: "0 0 10px", fontSize: 16 }}>Categories from the database</h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {cats.map((c) => (
                <span key={c.id} className="chip wait">{c.name}</span>
              ))}
            </div>
          </section>
        )}
        <section className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>AI</h2>
          <div className="grid-kpi">
            <div>
              <div className="kpi-label">Photo classifier</div>
              <div style={{ marginTop: 6 }}>
                {ai === null ? <span className="chip wait">Checking</span>
                  : ai.classifier === "ready" ? <span className="chip ok">Ready</span>
                  : <span className="chip warn">{ai.classifier === "not_installed" ? "PyTorch not installed" : "Model files missing"}</span>}
              </div>
              {ai?.version && <div className="muted small" style={{ marginTop: 6 }}>{ai.version}</div>}
            </div>
            <div>
              <div className="kpi-label">Test accuracy</div>
              <div className="kpi-value">{ai?.accuracy != null ? `${Math.round(ai.accuracy * 100)}%` : "–"}</div>
              <div className="muted small">Open Images test photos{ai?.own_photo_accuracy != null ? ` · own photos ${Math.round(ai.own_photo_accuracy * 100)}%` : ""}</div>
            </div>
            <div>
              <div className="kpi-label">Donors kept the AI's choice</div>
              <div className="kpi-value">{aiStats?.top1_rate != null ? `${Math.round(aiStats.top1_rate * 100)}%` : "–"}</div>
              <div className="muted small">
                {aiStats ? `${aiStats.top1_kept} of ${aiStats.donations_with_ai} real donations · in top 3: ${aiStats.top3_rate != null ? Math.round(aiStats.top3_rate * 100) + "%" : "–"}` : ""}
              </div>
            </div>
            <div>
              <div className="kpi-label">AI document check</div>
              <div style={{ marginTop: 6 }}>{ai === null ? <span className="chip wait">Checking</span> : ai.document_review ? <span className="chip ok">Ready</span> : <span className="chip warn">Add ANTHROPIC_API_KEY</span>}</div>
            </div>
          </div>
        </section>
        <ComingIn phase={8} what="KPI cards, the needs-your-action queue, seasonal panel, need hotspots and charts." />
      </main>
    </>
  );
}
