import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import LiveMap, { type MapMarker } from "../components/LiveMap";
import { api, type AreaNeed, type AreaNeeds, type AreaRow, type Category, type Point } from "../lib/api";
import { LEVELS, SHORT_CAT, ago, pointTypeLabel } from "../lib/format";

const DOT = ["#9aa39e", "#d4a800", "#d9772b", "#a2361a"];
const POINT_COLOR = "#2449A8";
const CAMP_COLOR = "#7c3aed";
const GAP_RING = "#a2361a";
// A place in high or urgent need is a "coverage gap" when no open point that takes the item is this close
const GAP_KM: Record<string, number> = { city: 30, region: 30, area: 10 };

type Crumb = { id: string | null; name: string };
type Picked = { place: string; need: AreaNeed };
type Nearest = { point: Point; km: number } | null;
type Gap = { row: AreaRow; level: number; need: string; nearest: Nearest; why: string };

function km(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(r(b.lat - a.lat) / 2) ** 2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(r(b.lng - a.lng) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

const takes = (p: Point, categoryId: number | null) => categoryId === null || p.categories.length === 0 || p.categories.some((c) => c.id === categoryId);

export default function NeedsMap() {
  const [trail, setTrail] = useState<Crumb[]>([{ id: null, name: "Pakistan" }]);
  const [data, setData] = useState<AreaNeeds | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [points, setPoints] = useState<Point[]>([]);
  const [view, setView] = useState<"grid" | "map">("grid");
  const [categoryId, setCategoryId] = useState<number | null>(null);   // map colour and gaps for one category, or all
  const [picked, setPicked] = useState<Picked | null>(null);
  const [focusRow, setFocusRow] = useState<string | null>(null);      // place clicked on the map
  const [focusPoint, setFocusPoint] = useState<string | null>(null);  // point clicked on the map
  const [busy, setBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);
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
    api<Point[]>("/points?open_only=true").then(setPoints).catch(() => undefined);
  }, []);

  const clearFocus = () => {
    setPicked(null);
    setFocusRow(null);
    setFocusPoint(null);
  };

  const open = (row: AreaRow) => {
    if (!row.has_children) return;
    clearFocus();
    setData(null);
    setTrail((t) => [...t, { id: row.id, name: row.name }]);
  };

  const back = (i: number) => {
    clearFocus();
    setData(null);
    setTrail((t) => t.slice(0, i + 1));
  };

  // The province we are in (or all Pakistan at the top level): the AI scan covers one province at a time
  const scanProvince = trail.length > 1 ? trail[1] : null;

  const aiScan = async () => {
    setScanning(true);
    setScanMsg(null);
    setError(null);
    try {
      const r = await api<{ ok: boolean; status: string }>("/admin/needs/ai-scan", {
        method: "POST", body: JSON.stringify({ location_id: scanProvince?.id ?? null }),
      });
      if (r.ok) setScanMsg(`AI scan of ${scanProvince?.name ?? "Pakistan"}: ${r.status}`);
      else setError(r.status);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setScanning(false);
    }
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

  // Level of a place for the chosen category (or its highest level)
  const levelOf = useCallback(
    (row: AreaRow) => (categoryId === null ? row.max_level : row.needs.find((n) => n.category_id === categoryId)?.level ?? 0),
    [categoryId],
  );

  const nearestFor = useCallback(
    (row: AreaRow, cat: number | null): Nearest => {
      if (row.lat === null || row.lng === null) return null;
      let best: Nearest = null;
      for (const p of points) {
        if (!takes(p, cat)) continue;
        const d = km({ lat: row.lat, lng: row.lng }, p);
        if (!best || d < best.km) best = { point: p, km: d };
      }
      return best;
    },
    [points],
  );

  // Places in high or urgent need with no suitable open point nearby
  const gaps: Gap[] = useMemo(() => {
    if (!data) return [];
    const out: Gap[] = [];
    for (const row of data.children) {
      const lv = levelOf(row);
      if (lv < 2) continue;
      const need = categoryId === null ? row.needs[0] : row.needs.find((n) => n.category_id === categoryId);
      if (!need) continue;
      const cat = categoryId ?? need.category_id;
      if (row.level === "province") {
        const inside = points.filter((p) => p.location_path[0] === row.name && takes(p, cat));
        if (inside.length === 0) out.push({ row, level: lv, need: need.name, nearest: nearestFor(row, cat), why: `No open point in ${row.name} takes ${need.name.toLowerCase()}` });
        continue;
      }
      const nearest = nearestFor(row, cat);
      const limit = GAP_KM[row.level] ?? 30;
      if (!nearest || nearest.km > limit) {
        out.push({ row, level: lv, need: need.name, nearest,
          why: nearest ? `Nearest point for ${need.name.toLowerCase()} is ${Math.round(nearest.km)} km away` : `No open point takes ${need.name.toLowerCase()}` });
      }
    }
    return out.sort((a, b) => b.level - a.level || (b.nearest?.km ?? 1e9) - (a.nearest?.km ?? 1e9));
  }, [data, points, categoryId, levelOf, nearestFor]);

  const gapIds = new Set(gaps.map((g) => g.row.id));
  const pointsHere = points.filter((p) => !here.id || p.location_path.includes(here.name));

  const markers: MapMarker[] = [
    ...(data?.children ?? [])
      .filter((r) => r.lat !== null && r.lng !== null)
      .map((r) => {
        const lv = levelOf(r);
        const top = r.needs.filter((n) => n.level >= 2).map((n) => n.name);
        return {
          id: r.id, lat: r.lat as number, lng: r.lng as number, kind: "point" as const, color: DOT[lv], size: 14 + lv * 5,
          ring: gapIds.has(r.id) ? GAP_RING : undefined, selected: focusRow === r.id,
          label: `${r.name}: ${LEVELS[lv].label}${categoryId === null && top.length ? ` (${top.slice(0, 3).join(", ")})` : ""}${gapIds.has(r.id) ? " · no point nearby" : ""}${r.neglected.length ? " · neglected" : ""}`,
          onClick: () => { setFocusPoint(null); setPicked(null); setFocusRow(r.id); },
        };
      }),
    ...pointsHere.map((p) => ({
      id: `p-${p.id}`, lat: p.lat, lng: p.lng, kind: "point" as const, square: true, size: 14,
      color: p.type === "relief_camp" ? CAMP_COLOR : POINT_COLOR, selected: focusPoint === p.id,
      label: `${p.name} (${pointTypeLabel(p.type)})`,
      onClick: () => { setFocusRow(null); setPicked(null); setFocusPoint(p.id); },
    })),
  ];

  const row = data?.children.find((r) => r.id === focusRow) ?? null;
  const point = points.find((p) => p.id === focusPoint) ?? null;

  return (
    <>
      <PageHeader title="Needs by area" sub="What each area needs: UN data (IPC, prices, poverty, people in need, rainfall), an AI scan of recent news and reports, disasters and point requests, and whether we have a point nearby.">
        <span className="muted small">Updated {ago(data?.computed_at ?? null)}</span>
        <button className="btn ghost small" onClick={recompute} disabled={busy || scanning}>{busy ? "Working…" : "Recompute now"}</button>
        <button className="btn small" onClick={aiScan} disabled={scanning} title="The AI searches news, UN and NGO reports from the last 90 days (1-4 minutes, a few cents)">
          {scanning ? `Searching the web for ${scanProvince?.name ?? "Pakistan"}…` : `Update ${scanProvince?.name ?? "Pakistan"} with AI`}
        </button>
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
          <select className="select" style={{ marginLeft: "auto" }} aria-label="Category" value={categoryId ?? ""}
            onChange={(e) => { setCategoryId(e.target.value ? Number(e.target.value) : null); setPicked(null); }}>
            <option value="">All categories</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <div className="tabs" role="tablist">
            <button role="tab" aria-selected={view === "grid"} className={view === "grid" ? "btn small" : "btn ghost small"} onClick={() => setView("grid")}>Grid</button>
            <button role="tab" aria-selected={view === "map"} className={view === "map" ? "btn small" : "btn ghost small"} onClick={() => setView("map")}>Map</button>
          </div>
        </div>

        <div className="legend">
          {LEVELS.map((l) => <span key={l.label}><span className={`sw ${l.cls}`} />{l.label}</span>)}
          {view === "map" ? (
            <>
              <span><span className="sw" style={{ background: POINT_COLOR, borderRadius: 4 }} />Distribution point</span>
              <span><span className="sw" style={{ background: CAMP_COLOR, borderRadius: 4 }} />Relief camp</span>
              <span><span className="sw" style={{ background: "#fff", boxShadow: `0 0 0 2px ${GAP_RING}`, borderRadius: 9 }} />No point nearby</span>
              <span className="muted">· Click a place or a point.</span>
            </>
          ) : (
            <span className="muted">· Click a coloured cell to see why. Click a place name to look inside it.</span>
          )}
        </div>

        {scanning && <div className="flash" style={{ background: "var(--info-bg)", color: "var(--info)" }} role="status">The AI is reading recent news and UN / NGO reports. This takes 1–4 minutes; you can keep using the page.</div>}
        {scanMsg && <div className="flash ok" role="status">{scanMsg}</div>}
        {error && <div className="flash bad" role="alert">{error}</div>}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "3 1 640px", overflowX: "auto", padding: view === "map" ? 0 : 12 }}>
            {data === null ? (
              <p className="muted" style={{ padding: 12 }}>Loading…</p>
            ) : view === "map" ? (
              <LiveMap key={here.id ?? "pk"} markers={markers} height={540} />
            ) : (
              <table className="needs-grid">
                <thead>
                  <tr>
                    <th className="place">Place</th>
                    {cats.map((c) => <th key={c.id} title={c.name} style={categoryId === c.id ? { color: "var(--ink)" } : undefined}>{SHORT_CAT[c.id] ?? c.name}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.children.map((r) => {
                    const byCat = new Map(r.needs.map((n) => [n.category_id, n]));
                    return (
                      <tr key={r.id}>
                        <td className="place">
                          {r.has_children ? (
                            <button onClick={() => open(r)} style={{ border: 0, background: "none", font: "inherit", fontWeight: 700, cursor: "pointer", padding: 0, color: "var(--ink)", textAlign: "left" }}>
                              {r.name} ›
                            </button>
                          ) : (
                            <strong>{r.name}</strong>
                          )}
                          <div className="muted small" style={{ textTransform: "capitalize" }}>
                            {r.level}{gapIds.has(r.id) && <span style={{ color: "var(--urgent)", fontWeight: 700, textTransform: "none" }}> · no point nearby</span>}
                            {r.neglected.length > 0 && <span style={{ color: "#7c3aed", fontWeight: 700, textTransform: "none" }} title="High need, but no UN agency or NGO works on it here (OCHA 3W)"> · neglected</span>}
                          </div>
                        </td>
                        {cats.map((c) => {
                          const n = byCat.get(c.id);
                          const lv = n?.level ?? 0;
                          const sel = picked?.place === r.name && picked.need.category_id === c.id;
                          const dim = categoryId !== null && categoryId !== c.id;
                          return (
                            <td key={c.id} className={`cell lv${lv}${sel ? " sel" : ""}`} title={n ? `${c.name}: ${n.level_name}` : c.name}
                              style={dim ? { opacity: 0.35 } : undefined}
                              onClick={() => { if (n) { setFocusRow(null); setFocusPoint(null); setPicked({ place: r.name, need: n }); } }}>
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

          <aside className="card" style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", gap: 12 }} aria-label="Details">
            {picked ? (
              <Reasons picked={picked} />
            ) : row ? (
              <PlacePanel row={row} categoryId={categoryId} levelOf={levelOf} nearest={nearestFor(row, categoryId ?? row.needs[0]?.category_id ?? null)}
                gap={gaps.find((g) => g.row.id === row.id) ?? null}
                onReason={(n) => setPicked({ place: row.name, need: n })} onOpen={() => open(row)} />
            ) : point ? (
              <PointPanel p={point} />
            ) : (
              <Summary here={here} data={data} onPick={(n) => setPicked({ place: here.name, need: n })} />
            )}
          </aside>
        </div>

        {data?.has_3w && (
          <section className="card" style={{ padding: 0 }}>
            <div style={{ padding: "16px 18px 0" }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>Neglected places in {here.name}</h2>
              <p className="muted small" style={{ margin: "2px 0 0" }}>
                High or urgent need, but no UN agency or NGO reports working on it there (OCHA 3W: who does what where).
              </p>
            </div>
            {data.children.filter((r) => r.neglected.length > 0).length === 0 ? (
              <p className="muted" style={{ padding: "10px 18px 16px", margin: 0 }}>None: every high need here has an organisation working on it.</p>
            ) : (
              <table className="table">
                <thead><tr><th>Place</th><th>Nobody working on</th><th>Organisations there</th><th /></tr></thead>
                <tbody>
                  {data.children.filter((r) => r.neglected.length > 0).map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.name}</strong><div className="muted small" style={{ textTransform: "capitalize" }}>{r.level}</div></td>
                      <td>{r.neglected.join(", ")}</td>
                      <td className="small">{r.orgs ? `${r.orgs} (${Object.keys(r.who_works).slice(0, 3).join(", ")})` : "None reported"}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn ghost small" onClick={() => { setPicked(null); setFocusPoint(null); setFocusRow(r.id); }}>Details</button>{" "}
                        {r.has_children && <button className="btn ghost small" onClick={() => open(r)}>Look inside</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}

        <section className="card" style={{ padding: 0 }}>
          <div style={{ padding: "16px 18px 0" }}>
            <h2 style={{ margin: 0, fontSize: 16 }}>
              Coverage gaps{categoryId !== null ? ` for ${cats.find((c) => c.id === categoryId)?.name.toLowerCase()}` : ""} in {here.name}
            </h2>
            <p className="muted small" style={{ margin: "2px 0 0" }}>
              High or urgent need, but no open point that takes the item within {GAP_KM.city} km (10 km for an area). These are the places to open a point or a relief camp.
            </p>
          </div>
          {gaps.length === 0 ? (
            <p className="muted" style={{ padding: "10px 18px 16px", margin: 0 }}>
              {data ? "No gaps: every place in high or urgent need has a point nearby." : "Loading…"}
            </p>
          ) : (
            <table className="table">
              <thead><tr><th>Place</th><th>Need</th><th>Why it is a gap</th><th /></tr></thead>
              <tbody>
                {gaps.map((g) => (
                  <tr key={g.row.id}>
                    <td><strong>{g.row.name}</strong><div className="muted small" style={{ textTransform: "capitalize" }}>{g.row.level}</div></td>
                    <td><span className={`chip lv${g.level}`}>{LEVELS[g.level].label}</span> {g.need}</td>
                    <td>{g.why}{g.nearest && <div className="muted small">Nearest: {g.nearest.point.name}</div>}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {g.row.lat !== null && (
                        <button className="btn ghost small" onClick={() => { setView("map"); setPicked(null); setFocusPoint(null); setFocusRow(g.row.id); }}>Show on map</button>
                      )}{" "}
                      {g.row.has_children && <button className="btn ghost small" onClick={() => open(g.row)}>Look inside</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
    </>
  );
}

function Reasons({ picked }: { picked: Picked }) {
  return (
    <>
      <div>
        <span className={`chip lv${picked.need.level}`}>{LEVELS[picked.need.level].label} · {picked.need.score}</span>
        <h2 style={{ margin: "8px 0 0", fontSize: 18 }}>{picked.need.name} in {picked.place}</h2>
      </div>
      <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 10 }}>
        {picked.need.reasons.map((r, i) => (
          <li key={i} style={{ opacity: r.old ? 0.7 : 1 }}>
            {r.reached === "none" && <span className="chip bad" style={{ marginBottom: 4 }}>Nobody has reached them yet</span>}
            <div style={{ fontWeight: 600 }}>{r.why}</div>
            {r.quote && <div className="small" style={{ fontStyle: "italic", color: "var(--ink-2)" }}>“{r.quote}”</div>}
            <div className="muted small">
              {r.source}{r.date ? ` · ${r.date}` : ""}{r.place && r.place !== picked.place ? ` · in ${r.place}` : ""} · {r.points} points
              {r.old ? " · counts less (old)" : ""}
            </div>
            {r.alert_id && <Link className="small" to={`/disasters?id=${r.alert_id}`}>Open the alert</Link>}
            {r.url && <a className="small" href={r.url} target="_blank" rel="noreferrer">Open the source</a>}
          </li>
        ))}
      </ul>
      <p className="muted small" style={{ margin: 0 }}>Score = the strongest reason, plus 5 for each other strong one. 80+ urgent, 55+ high, 30+ some. Data over a year old counts less; over 2 years old is not used.</p>
    </>
  );
}

function PlacePanel({ row, categoryId, levelOf, nearest, gap, onReason, onOpen }: {
  row: AreaRow;
  categoryId: number | null;
  levelOf: (r: AreaRow) => number;
  nearest: Nearest;
  gap: Gap | null;
  onReason: (n: AreaNeed) => void;
  onOpen: () => void;
}) {
  const lv = levelOf(row);
  const needs = row.needs.filter((n) => n.level > 0 && (categoryId === null || n.category_id === categoryId));
  return (
    <>
      <div>
        <span className={`chip lv${lv}`}>{LEVELS[lv].label}</span>
        <h2 style={{ margin: "8px 0 0", fontSize: 18 }}>{row.name}</h2>
        <span className="muted small" style={{ textTransform: "capitalize" }}>{row.level}</span>
      </div>
      {gap && (
        <div className="flash bad" style={{ fontWeight: 600 }}>
          Coverage gap: {gap.why}.
          <div style={{ fontWeight: 500, marginTop: 4 }}>Open a distribution point, or a relief camp if there is a disaster here.</div>
        </div>
      )}
      {needs.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No need signals here{categoryId !== null ? " for this category" : ""}.</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {needs.slice(0, 6).map((n) => (
            <button key={n.category_id} onClick={() => onReason(n)}
              style={{ display: "flex", justifyContent: "space-between", gap: 8, border: "1px solid var(--line)", borderRadius: 10, background: "#fff", padding: "8px 10px", font: "inherit", cursor: "pointer", textAlign: "left" }}>
              <span>{n.name}<div className="muted small">{n.reasons[0]?.why}</div></span>
              <span className={`chip lv${n.level}`}>{LEVELS[n.level].label}</span>
            </button>
          ))}
        </div>
      )}
      <div className="muted small">
        {nearest ? <>Nearest open point: <strong style={{ color: "var(--ink)" }}>{nearest.point.name}</strong>, {Math.round(nearest.km)} km</> : "No open distribution point takes this yet."}
      </div>
      {row.neglected.length > 0 && (
        <div className="flash" style={{ background: "#f1ebfe", color: "#5b21b6", fontWeight: 600 }}>
          Neglected: high need for {row.neglected.join(", ").toLowerCase()}, but no UN agency or NGO works on it here.
          <div style={{ fontWeight: 500, marginTop: 4 }}>A good place for RAAZICID to help: few others are.</div>
        </div>
      )}
      {Object.keys(row.who_works).length > 0 && (
        <div>
          <div className="kpi-label">Who works here ({row.orgs} organisations, OCHA 3W)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 4 }}>
            {Object.entries(row.who_works).map(([sector, orgs]) => (
              <div key={sector} className="small"><strong>{sector}:</strong> {orgs.slice(0, 6).join(", ")}{orgs.length > 6 ? ` +${orgs.length - 6}` : ""}</div>
            ))}
          </div>
        </div>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {row.has_children && <button className="btn small" onClick={onOpen}>Look inside {row.name}</button>}
        <Link className="btn ghost small" to="/points">Distribution points</Link>
        <Link className="btn ghost small" to="/disasters">Disaster alerts</Link>
      </div>
    </>
  );
}

function PointPanel({ p }: { p: Point }) {
  return (
    <>
      <div>
        <span className="chip info">{pointTypeLabel(p.type)}</span>
        <h2 style={{ margin: "8px 0 0", fontSize: 18 }}>{p.name}</h2>
        <span className="muted small">{p.address} · {p.location_path.slice(-2).join(", ")}</span>
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {p.same_day_food && <span className="chip ok">Same-day food</span>}
        {p.categories.length === 0 ? <span className="chip wait">Takes everything</span> : p.categories.map((c) => <span key={c.id} className="chip wait">{c.name}</span>)}
      </div>
      <div style={{ display: "flex", gap: 20 }}>
        <div><div className="kpi-label">Last 30 days</div><div style={{ fontSize: 20, fontWeight: 800 }}>{p.items_30d} items</div></div>
        <div><div className="kpi-label">Open requests</div><div style={{ fontSize: 20, fontWeight: 800 }}>{p.open_requests}</div></div>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link className="btn ghost small" to="/points">Manage points</Link>
        <a className="btn ghost small" href={`https://www.google.com/maps?q=${p.lat},${p.lng}`} target="_blank" rel="noreferrer">Google Maps</a>
      </div>
    </>
  );
}

function Summary({ here, data, onPick }: { here: Crumb; data: AreaNeeds | null; onPick: (n: AreaNeed) => void }) {
  return (
    <>
      <h2 style={{ margin: 0, fontSize: 18 }}>{here.name}</h2>
      {data?.summary && data.summary.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="muted small">Top needs anywhere inside {here.name}</span>
          {data.summary.slice(0, 6).map((n) => (
            <button key={n.category_id} onClick={() => onPick(n)}
              style={{ display: "flex", justifyContent: "space-between", border: "1px solid var(--line)", borderRadius: 10, background: "#fff", padding: "8px 10px", font: "inherit", cursor: "pointer" }}>
              <span>{n.name}</span><span className={`chip lv${n.level}`}>{LEVELS[n.level].label}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted" style={{ margin: 0 }}>
          {here.id ? "No need signals here yet." : "Click a place on the map or a coloured cell in the grid to see the reasons and sources behind it."}
        </p>
      )}
      <p className="muted small" style={{ margin: 0 }}>
        Only evidence from the last 2 years counts: IPC food insecurity and WFP food prices (HDX), the AI scan of recent
        news and UN / NGO reports, disaster alerts, rainfall and what people ask for at our points. An empty cell means no
        recent evidence yet: run <strong>Update … with AI</strong> for that province.
      </p>
    </>
  );
}
