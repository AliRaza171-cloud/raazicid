import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import LiveMap, { type MapMarker } from "../components/LiveMap";
import { api, type AreaNeed, type AreaNeeds, type AreaRow, type Category, type DepValue, type Deprivation, type NeedReason, type Ngo } from "../lib/api";
import { LEVELS, SHORT_CAT, ago } from "../lib/format";

const DOT = ["#9aa39e", "#d4a800", "#d9772b", "#a2361a"];
const NGO_COLOR = "#2449A8";
const GAP_RING = "#a2361a";
// A place in high or urgent need is a "coverage gap" when no NGO we know that takes the item is this close
const GAP_KM: Record<string, number> = { city: 30, region: 30, area: 10 };

type Crumb = { id: string | null; name: string };
type Picked = { place: string; placeId: string | null; need: AreaNeed };
type Nearest = { ngo: Ngo; km: number } | null;
type Gap = { row: AreaRow; level: number; need: string; nearest: Nearest; why: string };

function km(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const r = (d: number) => (d * Math.PI) / 180;
  const h = Math.sin(r(b.lat - a.lat) / 2) ** 2 + Math.cos(r(a.lat)) * Math.cos(r(b.lat)) * Math.sin(r(b.lng - a.lng) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

const takes = (p: Ngo, categoryId: number | null) => categoryId === null || p.categories.length === 0 || p.categories.some((c) => c.id === categoryId);

export default function NeedsMap() {
  const [trail, setTrail] = useState<Crumb[]>([{ id: null, name: "Pakistan" }]);
  const [data, setData] = useState<AreaNeeds | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [points, setPoints] = useState<Ngo[]>([]);   // NGOs we know
  const [view, setView] = useState<"grid" | "map">("grid");
  const [categoryId, setCategoryId] = useState<number | null>(null);   // map colour and gaps for one category, or all
  const [picked, setPicked] = useState<Picked | null>(null);
  const [focusRow, setFocusRow] = useState<string | null>(null);      // place clicked on the map
  const [focusPoint, setFocusPoint] = useState<string | null>(null);  // NGO clicked on the map
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

  const [dep, setDep] = useState<Deprivation | null>(null);   // long-term deprivation layer (survey tables)
  const loadDep = useCallback(() => {
    api<Deprivation>(here.id ? `/admin/deprivation?parent_id=${here.id}` : "/admin/deprivation").then(setDep).catch(() => setDep(null));
  }, [here.id]);
  useEffect(loadDep, [loadDep]);
  const loadPoints = useCallback(() => { api<Ngo[]>("/admin/ngos").then(setPoints).catch(() => undefined); }, []);
  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
    // reload NGOs when you come back to this tab (e.g. after a web search on the NGOs page)
    loadPoints();
    window.addEventListener("focus", loadPoints);
    return () => window.removeEventListener("focus", loadPoints);
  }, [loadPoints]);

  // Find NGOs for places in need that have none: OpenStreetMap, OCHA 3W, then web search (backend "NGO finder")
  const [filling, setFilling] = useState<string | null>(null);   // place id being filled, or "all"
  const [fillMsg, setFillMsg] = useState<string | null>(null);
  const fillGaps = async (locationId: string | null, key: string, categoryId?: number) => {
    setFilling(key);
    setFillMsg(null);
    setError(null);
    try {
      const r = await api<{ ok: boolean; status: string }>("/admin/ngos/fill-gaps", { method: "POST", body: JSON.stringify({ location_id: locationId, use_ai: true, category_id: categoryId ?? null }) });
      if (r.ok) setFillMsg(r.status);
      else setError(r.status);
      loadPoints();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setFilling(null);
    }
  };

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
        if (!best || d < best.km) best = { ngo: p, km: d };
      }
      return best;
    },
    [points],
  );

  // Places in high or urgent need with no NGO nearby that takes the item
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
        if (inside.length === 0) out.push({ row, level: lv, need: need.name, nearest: nearestFor(row, cat), why: `No NGO we know in ${row.name} takes ${need.name.toLowerCase()}` });
        continue;
      }
      const nearest = nearestFor(row, cat);
      const limit = GAP_KM[row.level] ?? 30;
      if (!nearest || nearest.km > limit) {
        out.push({ row, level: lv, need: need.name, nearest,
          why: nearest ? `Nearest NGO for ${need.name.toLowerCase()} is ${Math.round(nearest.km)} km away` : `No NGO we know takes ${need.name.toLowerCase()}` });
      }
    }
    return out.sort((a, b) => b.level - a.level || (b.nearest?.km ?? 1e9) - (a.nearest?.km ?? 1e9));
  }, [data, points, categoryId, levelOf, nearestFor]);

  const gapIds = new Set(gaps.map((g) => g.row.id));
  // Places in high or urgent need where OCHA 3W lists nobody working on it
  const neglected = data?.has_3w ? data.children.filter((r) => r.neglected.length > 0) : [];
  const pointsHere = points.filter((p) => !here.id || p.location_path.includes(here.name));

  const markers: MapMarker[] = [
    ...(data?.children ?? [])
      .filter((r) => r.lat !== null && r.lng !== null)
      .map((r) => {
        const lv = levelOf(r);
        const top = r.needs.filter((n) => n.level >= 2).map((n) => n.name);
        return {
          id: r.id, lat: r.lat as number, lng: r.lng as number, kind: "ngo" as const, color: DOT[lv], size: 14 + lv * 5,
          ring: gapIds.has(r.id) ? GAP_RING : undefined, selected: focusRow === r.id,
          label: `${r.name}: ${LEVELS[lv].label}${categoryId === null && top.length ? ` (${top.slice(0, 3).join(", ")})` : ""}${gapIds.has(r.id) ? " · no NGO nearby" : ""}${r.neglected.length ? " · neglected" : ""}`,
          onClick: () => { setFocusPoint(null); setPicked(null); setFocusRow(r.id); },
        };
      }),
    ...pointsHere.map((p) => ({
      id: `p-${p.id}`, lat: p.lat, lng: p.lng, kind: "ngo" as const, square: true, size: 14,
      color: NGO_COLOR, selected: focusPoint === p.id,
      label: `${p.name} (NGO)${p.location_approx ? " · office not on the map yet" : ""}`,
      onClick: () => { setFocusRow(null); setPicked(null); setFocusPoint(p.id); },
    })),
  ];

  const row = data?.children.find((r) => r.id === focusRow) ?? null;
  const point = points.find((p) => p.id === focusPoint) ?? null;

  return (
    <>
      <PageHeader title="Needs by area" sub="What each area needs: UN data (IPC, prices, poverty, people in need, rainfall), an AI scan of recent news and reports, disasters and displacement, and whether we know an NGO nearby to deliver to.">
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
              <span><span className="sw" style={{ background: NGO_COLOR, borderRadius: 4 }} />NGO</span>
              <span><span className="sw" style={{ background: "#fff", boxShadow: `0 0 0 2px ${GAP_RING}`, borderRadius: 9 }} />No NGO nearby</span>
              <span className="muted">· Click a place or an NGO.</span>
            </>
          ) : (
            <span className="muted">· Click a coloured cell to see why. Click a place name to look inside it.</span>
          )}
        </div>

        {scanning && <div className="flash" style={{ background: "var(--info-bg)", color: "var(--info)" }} role="status">The AI is reading recent news and UN / NGO reports. This takes 1–4 minutes; you can keep using the page.</div>}
        {scanMsg && <div className="flash ok" role="status">{scanMsg}</div>}
        {filling && <div className="flash" style={{ background: "var(--info-bg)", color: "var(--info)" }} role="status">Finding NGOs: OpenStreetMap, OCHA 3W, then a web search if needed. This can take a few minutes.</div>}
        {fillMsg && <div className="flash ok" role="status">{fillMsg}</div>}
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
                            {r.level}{gapIds.has(r.id) && <span style={{ color: "var(--urgent)", fontWeight: 700, textTransform: "none" }}> · no NGO nearby</span>}
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
                              onClick={() => { if (n) { setFocusRow(null); setFocusPoint(null); setPicked({ place: r.name, placeId: r.id, need: n }); } }}>
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
              <PlacePanel dep={dep?.rows.find((d) => d.id === row.id)?.values ?? null} depLabels={dep?.measures ?? []} row={row} categoryId={categoryId} levelOf={levelOf} nearest={nearestFor(row, categoryId ?? row.needs[0]?.category_id ?? null)}
                gap={gaps.find((g) => g.row.id === row.id) ?? null}
                onReason={(n) => setPicked({ place: row.name, placeId: row.id, need: n })} onOpen={() => open(row)} />
            ) : point ? (
              <NgoPanel p={point} />
            ) : (
              <Summary here={here} data={data} onPick={(n) => setPicked({ place: here.name, placeId: here.id, need: n })} />
            )}
          </aside>
        </div>

        {picked && <NeedDetail picked={picked} onClose={() => setPicked(null)} finding={filling !== null}
          onFind={(id) => fillGaps(id, id, picked.need.category_id)} />}

        <DeprivationCard here={here.name} dep={dep} reload={loadDep}
          onDetails={(id) => { setPicked(null); setFocusPoint(null); setFocusRow(id); }} />

        {data && gaps.length === 0 && neglected.length === 0 && (
          <div className="card" style={{ padding: "12px 18px", display: "flex", gap: 10, alignItems: "center" }}>
            <span className="chip ok">All clear</span>
            <span className="small">
              Every high or urgent need in {here.name} has an NGO nearby that takes the item
              {data.has_3w ? ", and an organisation working on it (OCHA 3W)" : ""}. If that changes, a list of the places will appear here.
            </span>
          </div>
        )}

        {data?.has_3w && neglected.length > 0 && (
          <section className="card" style={{ padding: 0 }}>
            <div style={{ padding: "16px 18px 0" }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>Neglected places in {here.name}</h2>
              <p className="muted small" style={{ margin: "2px 0 0" }}>
                High or urgent need, but no UN agency or NGO reports working on it there (OCHA 3W: who does what where).
              </p>
            </div>
            <table className="table">
                <thead><tr><th>Place</th><th>Nobody working on</th><th>Organisations there</th><th /></tr></thead>
                <tbody>
                  {neglected.map((r) => (
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
          </section>
        )}

        {gaps.length > 0 && (
        <section className="card" style={{ padding: 0 }}>
          <div style={{ padding: "16px 18px 0", display: "flex", gap: 8, alignItems: "flex-start", flexWrap: "wrap" }}>
            <div style={{ marginRight: "auto", maxWidth: 720 }}>
              <h2 style={{ margin: 0, fontSize: 16 }}>
                Coverage gaps{categoryId !== null ? ` for ${cats.find((c) => c.id === categoryId)?.name.toLowerCase()}` : ""} in {here.name}
              </h2>
              <p className="muted small" style={{ margin: "2px 0 0" }}>
                High or urgent need, but no NGO we know that takes the item within {GAP_KM.city} km (10 km for an area).
                The NGO finder looks for NGOs there, highest need first: OpenStreetMap offices and OCHA 3W organisations working
                on that need (free), then a web search where those found nothing. It also runs by itself once a day.
              </p>
            </div>
            {gaps.length > 0 && (
              <button className="btn small" disabled={filling !== null} onClick={() => fillGaps(here.id, "all")}>
                {filling === "all" ? "Finding NGOs… (up to a few minutes)" : `Find NGOs for these places`}
              </button>
            )}
          </div>
          <table className="table">
              <thead><tr><th>Place</th><th>Need</th><th>Why it is a gap</th><th /></tr></thead>
              <tbody>
                {gaps.map((g) => (
                  <tr key={g.row.id}>
                    <td><strong>{g.row.name}</strong><div className="muted small" style={{ textTransform: "capitalize" }}>{g.row.level}</div></td>
                    <td><span className={`chip lv${g.level}`}>{LEVELS[g.level].label}</span> {g.need}</td>
                    <td>{g.why}{g.nearest && <div className="muted small">Nearest: {g.nearest.ngo.name}</div>}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      {g.row.lat !== null && (
                        <button className="btn ghost small" onClick={() => { setView("map"); setPicked(null); setFocusPoint(null); setFocusRow(g.row.id); }}>Show on map</button>
                      )}{" "}
                      {g.row.has_children && <button className="btn ghost small" onClick={() => open(g.row)}>Look inside</button>}{" "}
                      <button className="btn ghost small" disabled={filling !== null} onClick={() => fillGaps(g.row.id, g.row.id)}>
                        {filling === g.row.id ? "Finding…" : "Find NGOs here"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
        </section>
        )}
      </main>
    </>
  );
}

const LEVEL_MEANING = ["", "Worth sending if you have these items.", "Send soon.", "Send these first."];
const FRESH: Record<string, { label: string; cls: string; tip: string }> = {
  new: { label: "New", cls: "ok", tip: "From the last 3 months" },
  recent: { label: "This year", cls: "wait", tip: "From the last 12 months" },
  old: { label: "Old", cls: "", tip: "Over a year old, so it counts less" },
};

function ReasonCard({ r, place, main }: { r: NeedReason; place: string; main: boolean }) {
  const fresh = FRESH[r.fresh ?? (r.old ? "old" : "recent")];
  const facts = [
    r.place && r.place !== place ? `Where: ${r.place}` : null,
    r.date ? `When: ${r.date}${r.old_year ? " (old)" : ""}` : null,
    `From: ${r.source}`,
  ].filter(Boolean);
  return (
    <div style={{ border: "1px solid var(--line)", borderRadius: 12, padding: "10px 12px", background: main ? "#fafbf9" : "#fff", opacity: r.old ? 0.85 : 1 }}>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
        <span className={`chip ${fresh.cls}`} title={fresh.tip} style={fresh.cls ? { height: 20, fontSize: 11 } : { height: 20, fontSize: 11, background: "var(--warn-bg)", color: "var(--warn)" }}>{fresh.label}</span>
        {r.strength && <span className="chip wait" title={`${r.points} points`} style={{ height: 20, fontSize: 11 }}>{r.strength[0].toUpperCase() + r.strength.slice(1)} reason</span>}
        {r.reached === "none" && <span className="chip bad" style={{ height: 20, fontSize: 11 }}>Nobody has helped them yet</span>}
      </div>
      <div style={{ fontWeight: main ? 700 : 600, fontSize: main ? 15 : 14 }}>{r.why}</div>
      {r.quote && <div className="small" style={{ fontStyle: "italic", color: "var(--ink-2)", marginTop: 4 }}>“{r.quote}”</div>}
      <div className="muted small" style={{ marginTop: 4 }}>{facts.join(" · ")}</div>
      {(r.alert_id || r.url || r.report_id) && (
        <div className="small" style={{ marginTop: 4, display: "flex", gap: 10, flexWrap: "wrap" }}>
          {r.alert_id && <Link to={`/disasters?id=${r.alert_id}`}>Open the alert</Link>}
          {r.url && <a href={r.url} target="_blank" rel="noreferrer">Open the source</a>}
          {r.report_id && <Link to={`/reports?id=${r.report_id}`}>Open the report</Link>}
        </div>
      )}
    </div>
  );
}

function Reasons({ picked }: { picked: Picked }) {
  const [first] = picked.need.reasons;
  const lv = picked.need.level;
  const count = picked.need.reasons.length;
  return (
    <>
      <div>
        <span className={`chip lv${lv}`}>{LEVELS[lv].label} need</span>
        <h2 style={{ margin: "8px 0 2px", fontSize: 18 }}>{picked.place} needs {picked.need.name.toLowerCase()}</h2>
        <div className="small" style={{ color: "var(--ink-2)" }}>{LEVEL_MEANING[lv]}</div>
      </div>
      {first && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div className="kpi-label">Main reason</div>
          <ReasonCard r={first} place={picked.place} main />
        </div>
      )}
      <button className="btn ghost small" onClick={() => document.getElementById("need-detail")?.scrollIntoView({ behavior: "smooth" })}>
        See all {count} reason{count === 1 ? "" : "s"} and the NGOs to contact ↓
      </button>
    </>
  );
}

type NeedNgo = {
  id: string; name: string; address: string; phone: string | null; website: string | null; about: string | null;
  city: string; distance_km: number | null; reachable: boolean; active_here: boolean; works_text: string | null;
  takes_listed: boolean; takes: string[]; checked: boolean; phone_confirmed: boolean; ban_checked: boolean;
  registration: string | null; location_approx: boolean; lat: number; lng: number; found_by: string;
};

const FOUND_BY: Record<string, string> = { web_search: "Web search", openstreetmap: "OpenStreetMap", ocha_3w: "OCHA 3W", admin: "Added by admin" };

/** Full-width detail for a picked need: why (one row per reason) and the NGOs to drop the item at, with contacts. */
function NeedDetail({ picked, onFind, finding, onClose }: { picked: Picked; onFind: (placeId: string) => void; finding: boolean; onClose: () => void }) {
  const [ngos, setNgos] = useState<NeedNgo[] | null>(null);
  useEffect(() => {
    setNgos(null);
    if (!picked.placeId) { setNgos([]); return; }
    api<NeedNgo[]>(`/admin/ngos/for-need?location_id=${picked.placeId}&category_id=${picked.need.category_id}`)
      .then(setNgos).catch(() => setNgos([]));
  }, [picked.placeId, picked.need.category_id, finding]);
  const need = picked.need;
  const item = need.name.toLowerCase();
  const fresh = (r: NeedReason) => FRESH[r.fresh ?? (r.old ? "old" : "recent")];
  const cell = { padding: "8px 10px", verticalAlign: "top" as const };

  return (
    <section className="card" id="need-detail" style={{ padding: 0 }}>
      <div style={{ padding: "16px 18px 6px", display: "flex", gap: 10, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ marginRight: "auto" }}>
          <h2 style={{ margin: 0, fontSize: 17 }}>
            {picked.place} needs {item} <span className={`chip lv${need.level}`} style={{ marginLeft: 6 }}>{LEVELS[need.level].label}</span>
          </h2>
          <p className="muted small" style={{ margin: "2px 0 0" }}>
            {LEVEL_MEANING[need.level]}
            {(need.place_count ?? 0) > 1 && need.places ? ` Found in ${need.place_count} places: ${need.places.map((x) => `${x.name} (${LEVELS[x.level].label.toLowerCase()})`).join(", ")}${(need.place_count ?? 0) > need.places.length ? "…" : ""}.` : ""}
          </p>
        </div>
        <button className="btn ghost small" onClick={onClose}>Close</button>
      </div>

      <h3 style={{ margin: 0, padding: "8px 18px 4px", fontSize: 14 }}>Why ({need.reasons.length} reason{need.reasons.length === 1 ? "" : "s"})</h3>
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr><th>Place</th><th>What we found</th><th>When</th><th>Age</th><th>Weight</th><th>Source</th></tr>
          </thead>
          <tbody>
            {need.reasons.map((r, i) => (
              <tr key={i} style={{ opacity: r.old ? 0.8 : 1 }}>
                <td style={cell}><strong>{r.place ?? picked.place}</strong></td>
                <td style={{ ...cell, minWidth: 260 }}>
                  {r.why}
                  {r.reached === "none" && <div><span className="chip bad" style={{ height: 20, fontSize: 11, marginTop: 4 }}>Nobody has helped them yet</span></div>}
                  {r.quote && <div className="small" style={{ fontStyle: "italic", color: "var(--ink-2)", marginTop: 4 }}>“{r.quote}”</div>}
                </td>
                <td style={{ ...cell, whiteSpace: "nowrap" }}>{r.date ?? "Now"}</td>
                <td style={cell}><span className={`chip ${fresh(r).cls}`} title={fresh(r).tip}
                  style={fresh(r).cls ? { height: 20, fontSize: 11 } : { height: 20, fontSize: 11, background: "var(--warn-bg)", color: "var(--warn)" }}>{fresh(r).label}</span></td>
                <td style={{ ...cell, whiteSpace: "nowrap" }} title={`${r.points} points`}>{r.strength ? r.strength[0].toUpperCase() + r.strength.slice(1) : r.points}</td>
                <td style={{ ...cell, minWidth: 160 }} className="small">
                  {r.source}
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {r.alert_id && <Link to={`/disasters?id=${r.alert_id}`}>Alert</Link>}
                    {r.url && <a href={r.url} target="_blank" rel="noreferrer">Source</a>}
                    {r.report_id && <Link to={`/reports?id=${r.report_id}`}>Report</Link>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ padding: "14px 18px 4px", display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        <h3 style={{ margin: 0, fontSize: 14, marginRight: "auto" }}>NGOs that take {item} {picked.placeId ? `in or near ${picked.place}` : ""}</h3>
        {picked.placeId && (
          <button className="btn ghost small" disabled={finding} onClick={() => onFind(picked.placeId as string)}>
            {finding ? "Finding NGOs…" : `Find more NGOs in ${picked.place}`}
          </button>
        )}
      </div>
      {!picked.placeId ? (
        <p className="muted" style={{ padding: "4px 18px 16px", margin: 0 }}>Choose a province or a district to see NGOs there.</p>
      ) : ngos === null ? (
        <p className="muted" style={{ padding: "4px 18px 16px", margin: 0 }}>Loading NGOs…</p>
      ) : ngos.length === 0 ? (
        <p className="muted" style={{ padding: "4px 18px 16px", margin: 0 }}>
          We know no NGO in or near {picked.place} that takes {item}. Press <strong>Find more NGOs</strong>, or add one you know on the <Link to="/ngos">NGOs page</Link>.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr><th>NGO</th><th>Office</th><th>Contact</th><th>Takes</th><th>Checks</th><th /></tr>
            </thead>
            <tbody>
              {ngos.map((n) => (
                <tr key={n.id} style={n.active_here ? { boxShadow: "inset 3px 0 0 var(--urgent)" } : undefined}>
                  <td style={{ ...cell, minWidth: 180 }}>
                    <strong>{n.name}</strong>
                    {n.about && <div className="muted small">{n.about}</div>}
                    {n.active_here && <div className="small" style={{ color: "var(--urgent)", fontWeight: 600 }}>{n.works_text ?? "Works here (OCHA 3W)"}</div>}
                    <div className="muted small">{FOUND_BY[n.found_by] ?? n.found_by}</div>
                  </td>
                  <td style={{ ...cell, minWidth: 170 }}>
                    {n.location_approx ? <span style={{ color: "var(--warn)" }}>{n.city}: address not known yet</span> : n.address}
                    <div className="muted small">{n.city}{n.distance_km !== null ? ` · ${n.distance_km} km` : ""}</div>
                    {!n.reachable && <div className="muted small">Office outside {picked.place}: ask where to drop.</div>}
                  </td>
                  <td style={{ ...cell, whiteSpace: "nowrap" }}>
                    {n.phone ? <a href={`tel:${n.phone.replace(/[^\d+]/g, "")}`}>{n.phone}</a> : <span className="muted">No phone yet</span>}
                    {n.website && <div><a className="small" href={n.website} target="_blank" rel="noreferrer">Website</a></div>}
                  </td>
                  <td style={{ ...cell, minWidth: 140 }} className="small">
                    {n.takes_listed ? n.takes.join(", ") : <span className="muted">Not confirmed (ask them)</span>}
                  </td>
                  <td style={cell}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
                      <span className={`chip ${n.phone_confirmed ? "ok" : ""}`} style={n.phone_confirmed ? { height: 20, fontSize: 11 } : { height: 20, fontSize: 11, background: "var(--warn-bg)", color: "var(--warn)" }}>
                        {n.phone_confirmed ? "✓ Called" : "Not called"}
                      </span>
                      <span className={`chip ${n.ban_checked ? "ok" : ""}`} style={n.ban_checked ? { height: 20, fontSize: 11 } : { height: 20, fontSize: 11, background: "var(--warn-bg)", color: "var(--warn)" }}>
                        {n.ban_checked ? "✓ Not banned" : "Ban list not checked"}
                      </span>
                      {n.registration && <span className="chip ok" style={{ height: 20, fontSize: 11 }}>{n.registration}</span>}
                    </div>
                  </td>
                  <td style={{ ...cell, whiteSpace: "nowrap" }}>
                    {!n.location_approx && <a className="btn ghost small" href={`https://www.google.com/maps/dir/?api=1&destination=${n.lat},${n.lng}`} target="_blank" rel="noreferrer">Directions</a>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small" style={{ padding: "6px 18px 14px", margin: 0 }}>
            Red edge: works on this need here (OCHA 3W). Call an NGO before the first delivery and tick its checks on the <Link to="/ngos">NGOs page</Link>.
          </p>
        </div>
      )}
      <details className="small" style={{ color: "var(--muted)", padding: "0 18px 14px" }}>
        <summary style={{ cursor: "pointer" }}>How do we decide the level?</summary>
        <ul style={{ margin: "6px 0 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: 3 }}>
          <li>Each reason gets points for how serious it is.</li>
          <li>The strongest reason counts in full. Every other strong reason adds 5 points.</li>
          <li>80 or more is urgent, 55 to 79 is high, 30 to 54 is some. This one has {need.score}.</li>
          <li>Information over a year old counts less. Over 2 years old is not used.</li>
          <li>Urgent needs a very serious reason (a severe disaster, or a food crisis for 30% of people or more), or several reasons together.</li>
        </ul>
      </details>
    </section>
  );
}

function PlacePanel({ row, categoryId, levelOf, nearest, gap, onReason, onOpen, dep, depLabels }: {
  dep: Record<string, DepValue> | null;
  depLabels: Deprivation["measures"];
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
          <div style={{ fontWeight: 500, marginTop: 4 }}>Search the web for NGOs here on the NGOs page, so riders can deliver to them.</div>
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
        {nearest ? <>Nearest NGO: <strong style={{ color: "var(--ink)" }}>{nearest.ngo.name}</strong>, {Math.round(nearest.km)} km</> : "No NGO we know takes this yet."}
      </div>
      {row.neglected.length > 0 && (
        <div className="flash" style={{ background: "#f1ebfe", color: "#5b21b6", fontWeight: 600 }}>
          Neglected: high need for {row.neglected.join(", ").toLowerCase()}, but no UN agency or NGO works on it here.
          <div style={{ fontWeight: 500, marginTop: 4 }}>A good place for RAAZICID to help: few others are.</div>
        </div>
      )}
      {dep && Object.keys(dep).length > 0 && (
        <div>
          <div className="kpi-label">Long-term deprivation (survey data, not this month's need)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
            {depLabels.filter((m) => dep[m.measure]).map((m) => {
              const v = dep[m.measure];
              return (
                <div key={m.measure} className="small">
                  {m.label}: <strong>{v.display}</strong> <DepBand band={v.band} />
                  <span className="muted"> · {v.source}{v.year ? ` ${v.year}` : ""}{v.places > 1 ? ` · ${v.places} districts` : ""}</span>
                </div>
              );
            })}
          </div>
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
        <Link className="btn ghost small" to="/ngos">NGOs</Link>
        <Link className="btn ghost small" to="/disasters">Disaster alerts</Link>
      </div>
    </>
  );
}

function NgoPanel({ p }: { p: Ngo }) {
  return (
    <>
      <div>
        <span className="chip info">NGO</span>
        <h2 style={{ margin: "8px 0 0", fontSize: 18 }}>{p.name}</h2>
        <span className="muted small">{p.address} · {p.location_path.slice(-2).join(", ")}{p.phone ? ` · ${p.phone}` : ""}</span>
        {p.about && <div className="small" style={{ marginTop: 4 }}>{p.about}</div>}
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {p.takes_cooked_food && <span className="chip ok">Cooked food</span>}
        {p.categories.length === 0 ? <span className="chip wait">Takes everything</span> : p.categories.map((c) => <span key={c.id} className="chip wait">{c.name}</span>)}
      </div>
      <div><div className="kpi-label">Last 30 days</div><div style={{ fontSize: 20, fontWeight: 800 }}>{p.items_30d} donations</div></div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link className="btn ghost small" to="/ngos">Manage NGOs</Link>
        {!p.location_approx && <a className="btn ghost small" href={`https://www.google.com/maps?q=${p.lat},${p.lng}`} target="_blank" rel="noreferrer">Google Maps</a>}
        {p.source_url && <a className="btn ghost small" href={p.source_url} target="_blank" rel="noreferrer">Source</a>}
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
        news and UN / NGO reports, disaster alerts, rainfall and displacement. An empty cell means no
        recent evidence yet: run <strong>Update … with AI</strong> for that province.
      </p>
    </>
  );
}

const DEP_SHORT: Record<string, string> = {
  out_of_school: "Out of school", illiteracy: "Can't read", no_safe_water: "No safe water", no_toilet: "No toilet",
  kutcha_housing: "Kutcha houses", no_electricity: "No electricity", food_insecurity: "Food insecure", displaced: "Displaced",
};
const BAND_STYLE: Record<string, { background: string; color: string }> = {
  high: { background: "var(--urgent-bg)", color: "var(--urgent)" },
  moderate: { background: "var(--warn-bg)", color: "var(--warn)" },
};

function DepBand({ band }: { band: DepValue["band"] }) {
  if (band !== "high" && band !== "moderate") return null;
  return <span className="chip" style={{ ...BAND_STYLE[band], height: 20, fontSize: 11 }}>{band === "high" ? "among the worst" : "above median"}</span>;
}

function DeprivationCard({ here, dep, reload, onDetails }: { here: string; dep: Deprivation | null; reload: () => void; onDetails: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [measure, setMeasure] = useState("out_of_school");
  const [source, setSource] = useState("PSLM District 2019-20");
  const [year, setYear] = useState("2020");
  const [valueColumn, setValueColumn] = useState("");
  const [placeColumn, setPlaceColumn] = useState("");
  const [invert, setInvert] = useState(false);
  const [addMissing, setAddMissing] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!dep) return null;
  const table = dep.tables.find((t) => t.measure === measure);
  const loaded = dep.tables.filter((t) => t.rows > 0);

  const upload = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return setError("Choose a CSV or Excel file");
    const form = new FormData();
    form.append("file", file);
    form.append("measure", measure);
    form.append("source", source.trim() || "Uploaded table");
    form.append("year", year);
    form.append("value_column", valueColumn.trim());
    form.append("place_column", placeColumn.trim());
    form.append("invert", String(invert && !!table?.share));
    form.append("add_missing", String(addMissing));
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      const r = await api<{ matched: number; added_places: number; unmatched: string[]; unmatched_count: number; problems: string[];
        used: { place: string; value: string; province: string | null } }>("/admin/deprivation/upload", { method: "POST", body: form });
      setMsg(`${r.matched} places loaded (places from "${r.used.place}", numbers from "${r.used.value}"`
        + `${r.used.province ? `, province from "${r.used.province}"` : ""})`
        + (r.added_places ? `; ${r.added_places} new districts added` : "")
        + (r.unmatched_count ? `; not recognised: ${r.unmatched.slice(0, 8).join(", ")}${r.unmatched_count > 8 ? "…" : ""}` : "")
        + (r.problems.length ? `; skipped: ${r.problems.slice(0, 3).join("; ")}` : ""));
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (m: string) => {
    await api(`/admin/deprivation/${m}`, { method: "DELETE" }).catch(() => undefined);
    reload();
  };

  const template = async () => {
    const t = await api<{ filename: string; csv: string }>("/admin/deprivation/template");
    const url = URL.createObjectURL(new Blob([t.csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = t.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="card" style={{ padding: 0 }}>
      <div style={{ padding: "16px 18px 0", display: "flex", gap: 8, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ marginRight: "auto", maxWidth: 760 }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>Long-term deprivation in {here} <span className="chip wait" style={{ marginLeft: 6 }}>Survey data</span></h2>
          <p className="muted small" style={{ margin: "2px 0 0" }}>
            Where people have lacked schooling, safe water, toilets, solid houses or food for years (PBS PSLM and HIES, IOM DTM).
            These surveys are a few years old, so they never change the need levels above: use them to see where help is
            useful for the long run. "Among the worst" = the worst quarter of places with that figure.
          </p>
        </div>
        <button className="btn ghost small" onClick={() => setOpen(!open)}>{open ? "Close" : "Upload a table"}</button>
      </div>

      {open && (
        <form onSubmit={upload} style={{ margin: "12px 18px", display: "flex", flexDirection: "column", gap: 10, background: "#fafbf9", border: "1px solid var(--line)", borderRadius: 12, padding: 12 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <div style={{ flex: "2 1 260px" }}>
              <label htmlFor="dmeasure">What the table measures</label>
              <select id="dmeasure" className="select" style={{ width: "100%" }} value={measure} onChange={(e) => { setMeasure(e.target.value); setInvert(false); }}>
                {dep.tables.map((t) => <option key={t.measure} value={t.measure}>{t.label}</option>)}
              </select>
              {table && <span className="muted small">{table.hint}</span>}
            </div>
            <div style={{ flex: "2 1 200px" }}>
              <label htmlFor="dsource">Source</label>
              <input id="dsource" className="input" value={source} onChange={(e) => setSource(e.target.value)} placeholder="PSLM District 2019-20" />
            </div>
            <div style={{ flex: "0 1 100px" }}>
              <label htmlFor="dyear">Year</label>
              <input id="dyear" className="input" inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} />
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 200px" }}>
              <label htmlFor="dvalue">Column with the numbers (optional)</label>
              <input id="dvalue" className="input" value={valueColumn} onChange={(e) => setValueColumn(e.target.value)} placeholder="e.g. Total, IDP Individuals" />
            </div>
            <div style={{ flex: "1 1 200px" }}>
              <label htmlFor="dplace">Column with place names (optional)</label>
              <input id="dplace" className="input" value={placeColumn} onChange={(e) => setPlaceColumn(e.target.value)} placeholder="e.g. District, Admin 2" />
            </div>
          </div>
          {table?.share && (
            <label style={{ display: "flex", gap: 8, alignItems: "center", margin: 0, fontWeight: 500 }}>
              <input type="checkbox" checked={invert} onChange={(e) => setInvert(e.target.checked)} />
              The table gives the opposite (e.g. literacy rate, access to water or electricity): turn 60% into 40%
            </label>
          )}
          <label style={{ display: "flex", gap: 8, alignItems: "center", margin: 0, fontWeight: 500 }}>
            <input type="checkbox" checked={addMissing} onChange={(e) => setAddMissing(e.target.checked)} />
            Add districts we don't have yet (needs a province column)
          </label>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <input type="file" accept=".csv,.xlsx,text/csv" aria-label="CSV or Excel file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <button type="button" className="btn ghost small" onClick={template}>Download a template with our place names</button>
          </div>
          <span className="muted small">
            CSV or Excel (first sheet). Title rows above the header are fine; rows named Total or Pakistan are skipped.
            Shares can be 34, 34% or 0.34. A new table replaces the old one of the same kind.
          </span>
          {error && <div className="flash bad" role="alert">{error}</div>}
          {msg && <div className="flash ok" role="status">{msg}</div>}
          <button className="btn" type="submit" disabled={busy}>{busy ? "Loading…" : "Load table"}</button>
        </form>
      )}

      {loaded.length > 0 && (
        <div style={{ padding: "8px 18px 0", display: "flex", gap: 6, flexWrap: "wrap" }}>
          {loaded.map((t) => (
            <span key={t.measure} className="chip wait" title={t.hint}>
              {t.label}: {t.rows} places{t.source ? ` · ${t.source}` : ""}{t.year ? ` ${t.year}` : ""}
              <button onClick={() => remove(t.measure)} aria-label={`Remove ${t.label}`} style={{ border: 0, background: "none", color: "inherit", cursor: "pointer", fontWeight: 800 }}>×</button>
            </span>
          ))}
        </div>
      )}

      {dep.measures.length === 0 || dep.rows.length === 0 ? (
        <p className="muted" style={{ padding: "10px 18px 16px", margin: 0 }}>
          {dep.measures.length === 0
            ? "No survey tables yet. Upload PSLM district tables (out-of-school children, literacy, water, toilets, housing, electricity), HIES 2024-25 province tables or IOM DTM sheets from HDX."
            : `No survey figures for the places in ${here}.`}
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Place</th>
                {dep.measures.map((m) => <th key={m.measure} title={`${m.label} · ${m.sources.join("; ")}`}>{DEP_SHORT[m.measure] ?? m.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {dep.rows.map((r) => (
                <tr key={r.id} className="click" onClick={() => onDetails(r.id)}>
                  <td><strong>{r.name}</strong></td>
                  {dep.measures.map((m) => {
                    const v = r.values[m.measure];
                    return (
                      <td key={m.measure} title={v ? `${v.source}${v.year ? ` ${v.year}` : ""}${v.places > 1 ? ` · ${v.places} districts` : ""}` : "No figure"}
                        style={v?.band && BAND_STYLE[v.band] ? { ...BAND_STYLE[v.band], fontWeight: 700 } : undefined}>
                        {v ? v.display.replace(" (average)", "") : "–"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small" style={{ padding: "6px 18px 14px", margin: 0 }}>
            Red: among the worst quarter of places · amber: above the median. Bigger places show the average of their districts.
            Sources: {dep.measures.map((m) => `${DEP_SHORT[m.measure] ?? m.label}: ${m.sources.join(", ")}`).join(" · ")}
          </p>
        </div>
      )}
    </section>
  );
}
