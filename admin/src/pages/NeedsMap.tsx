import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import LiveMap, { type MapMarker } from "../components/LiveMap";
import { api, type AreaNeed, type AreaNeeds, type AreaRow, type Category } from "../lib/api";
import { LEVELS, SHORT_CAT, ago } from "../lib/format";

const DOT = ["#9aa39e", "#d4a800", "#d9772b", "#a2361a"];

type Crumb = { id: string | null; name: string };
type Picked = { place: string; need: AreaNeed };

export default function NeedsMap() {
  const [trail, setTrail] = useState<Crumb[]>([{ id: null, name: "Pakistan" }]);
  const [data, setData] = useState<AreaNeeds | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [view, setView] = useState<"grid" | "map">("grid");
  const [picked, setPicked] = useState<Picked | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const here = trail[trail.length - 1];

  const load = useCallback(() => {
    setError(null);
    api<AreaNeeds>(here.id ? `/needs?parent_id=${here.id}` : "/needs")
      .then(setData)
      .catch((e) => setError(e.message));
  }, [here.id]);

  useEffect(load, [load]);
  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const open = (row: AreaRow) => {
    if (!row.has_children) return;
    setPicked(null);
    setData(null);
    setTrail((t) => [...t, { id: row.id, name: row.name }]);
  };

  const back = (i: number) => {
    setPicked(null);
    setData(null);
    setTrail((t) => t.slice(0, i + 1));
  };

  const recompute = async () => {
    setBusy(true);
    try {
      await api("/admin/needs/recompute", { method: "POST" });
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const markers: MapMarker[] = (data?.children ?? [])
    .filter((r) => r.lat !== null && r.lng !== null)
    .map((r) => ({
      id: r.id, lat: r.lat as number, lng: r.lng as number, kind: "point", color: DOT[r.max_level], size: 14 + r.max_level * 4,
      label: `${r.name}: ${r.max_level ? r.needs.filter((n) => n.level >= 2).map((n) => n.name).join(", ") || LEVELS[r.max_level].label : "no signal"}`,
    }));

  return (
    <>
      <PageHeader title="Needs by area" sub="What each area needs across all 12 categories, worked out from IPC, food prices, poverty, disasters and point requests.">
        <span className="muted small">Updated {ago(data?.computed_at ?? null)}</span>
        <button className="btn ghost small" onClick={recompute} disabled={busy}>{busy ? "Working…" : "Recompute now"}</button>
      </PageHeader>
      <main className="page">
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <nav className="crumbs" aria-label="Place">
            {trail.map((c, i) => (
              <span key={c.id ?? "pk"} style={{ display: "inline-flex", gap: 6 }}>
                {i > 0 && <span className="muted">›</span>}
                {i < trail.length - 1 ? <button onClick={() => back(i)}>{c.name}</button> : <strong>{c.name}</strong>}
              </span>
            ))}
          </nav>
          <div className="tabs" role="tablist" style={{ marginLeft: "auto" }}>
            <button role="tab" aria-selected={view === "grid"} className={view === "grid" ? "btn small" : "btn ghost small"} onClick={() => setView("grid")}>Grid</button>
            <button role="tab" aria-selected={view === "map"} className={view === "map" ? "btn small" : "btn ghost small"} onClick={() => setView("map")}>Map</button>
          </div>
        </div>

        <div className="legend">
          {LEVELS.map((l) => <span key={l.label}><span className={`sw ${l.cls}`} />{l.label}</span>)}
          <span className="muted">· Click a coloured cell to see why. Click a place name to look inside it.</span>
        </div>

        {error && <div className="flash bad" role="alert">{error}</div>}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "3 1 640px", overflowX: "auto", padding: view === "map" ? 0 : 12 }}>
            {data === null ? (
              <p className="muted" style={{ padding: 12 }}>Loading…</p>
            ) : view === "map" ? (
              <LiveMap key={here.id ?? "pk"} markers={markers} height={520} />
            ) : (
              <table className="needs-grid">
                <thead>
                  <tr>
                    <th className="place">Place</th>
                    {cats.map((c) => <th key={c.id} title={c.name}>{SHORT_CAT[c.id] ?? c.name}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.children.map((row) => {
                    const byCat = new Map(row.needs.map((n) => [n.category_id, n]));
                    return (
                      <tr key={row.id}>
                        <td className="place">
                          {row.has_children ? (
                            <button onClick={() => open(row)} style={{ border: 0, background: "none", font: "inherit", fontWeight: 700, cursor: "pointer", padding: 0, color: "var(--ink)", textAlign: "left" }}>
                              {row.name} ›
                            </button>
                          ) : (
                            <strong>{row.name}</strong>
                          )}
                          <div className="muted small" style={{ textTransform: "capitalize" }}>{row.level}</div>
                        </td>
                        {cats.map((c) => {
                          const n = byCat.get(c.id);
                          const lv = n?.level ?? 0;
                          const sel = picked?.place === row.name && picked.need.category_id === c.id;
                          return (
                            <td key={c.id} className={`cell lv${lv}${sel ? " sel" : ""}`} title={n ? `${c.name}: ${n.level_name}` : c.name}
                              onClick={() => n && setPicked({ place: row.name, need: n })}>
                              {lv ? LEVELS[lv].label : ""}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
            {data && data.children.length === 0 && <p className="muted" style={{ padding: 12 }}>No places listed here.</p>}
          </section>

          <aside className="card" style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: 12 }} aria-label="Why">
            {picked ? (
              <>
                <div>
                  <span className={`chip ${LEVELS[picked.need.level].cls}`}>{LEVELS[picked.need.level].label} · {picked.need.score}</span>
                  <h2 style={{ margin: "8px 0 0", fontSize: 18 }}>{picked.need.name} in {picked.place}</h2>
                </div>
                <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 10 }}>
                  {picked.need.reasons.map((r, i) => (
                    <li key={i}>
                      <div style={{ fontWeight: 600 }}>{r.why}</div>
                      <div className="muted small">
                        {r.source}{r.date ? ` · ${r.date}` : ""}{r.place && r.place !== picked.place ? ` · in ${r.place}` : ""} · {r.points} points
                      </div>
                      {r.alert_id && <Link className="small" to={`/disasters?id=${r.alert_id}`}>Open the alert</Link>}
                    </li>
                  ))}
                </ul>
                <p className="muted small" style={{ margin: 0 }}>
                  Score = the strongest reason, plus 5 for each other strong one. 80+ urgent, 55+ high, 30+ some.
                </p>
              </>
            ) : (
              <>
                <h2 style={{ margin: 0, fontSize: 18 }}>{here.name}</h2>
                {data?.summary && data.summary.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <span className="muted small">Top needs anywhere inside {here.name}</span>
                    {data.summary.slice(0, 6).map((n) => (
                      <button key={n.category_id} onClick={() => setPicked({ place: here.name, need: n })}
                        style={{ display: "flex", justifyContent: "space-between", border: "1px solid var(--line)", borderRadius: 10, background: "#fff", padding: "8px 10px", font: "inherit", cursor: "pointer" }}>
                        <span>{n.name}</span><span className={`chip ${LEVELS[n.level].cls}`}>{LEVELS[n.level].label}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="muted" style={{ margin: 0 }}>
                    {here.id ? "No need signals here yet." : "Pick a coloured cell to see the reasons and sources behind it."}
                  </p>
                )}
                <p className="muted small" style={{ margin: 0 }}>
                  Data: IPC food insecurity, WFP food prices and poverty rates (HDX, daily), GDACS and news alerts (every 30 min), and what people ask for at our distribution points.
                </p>
              </>
            )}
          </aside>
        </div>
      </main>
    </>
  );
}
