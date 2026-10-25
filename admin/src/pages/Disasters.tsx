import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/Layout";
import LocationSelect from "../components/LocationSelect";
import { api, type Alert, type AlertStatus, type Category, type DataSource } from "../lib/api";
import { ALERT_STATUS, ALERT_TYPES, FIGURES, SEVERITY, ago, date, dateTime } from "../lib/format";

const TABS: { key: AlertStatus | "all"; label: string }[] = [
  { key: "unconfirmed", label: "Needs checking" },
  { key: "confirmed", label: "Confirmed" },
  { key: "handled", label: "Handled" },
  { key: "dismissed", label: "Dismissed" },
  { key: "all", label: "All" },
];

export default function Disasters() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("id");
  const [tab, setTab] = useState<AlertStatus | "all">("unconfirmed");
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [cats, setCats] = useState<Category[]>([]);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Alert[]>(tab === "all" ? "/admin/alerts" : `/admin/alerts?status=${tab}`).then(setAlerts).catch((e) => setError(e.message));
    api<Record<string, number>>("/admin/alerts/counts").then(setCounts).catch(() => undefined);
  }, [tab]);

  useEffect(load, [load]);
  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const select = (id: string | null) => {
    setAdding(false);
    setParams(id ? { id } : {});
  };

  const say = (msg: string) => {
    setFlash(msg);
    load();
    window.setTimeout(() => setFlash(null), 5000);
  };

  return (
    <>
      <PageHeader title="Disaster alerts" sub="Found automatically from GDACS and a Claude scan of NDMA, PDMA, PMD and Pakistani news. Check each one before acting.">
        <button className="btn ghost" onClick={() => { setParams({}); setAdding(true); }}>+ Add an alert</button>
      </PageHeader>
      <main className="page">
        <div className="tabs" role="tablist">
          {TABS.map((t) => (
            <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "btn small" : "btn ghost small"} onClick={() => setTab(t.key)}>
              {t.label}{t.key !== "all" && counts[t.key] ? ` (${counts[t.key]})` : ""}
            </button>
          ))}
        </div>

        {flash && <div className="flash ok" role="status">{flash}</div>}
        {error && <div className="flash bad" role="alert">{error}</div>}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "2 1 460px", padding: 0, overflowX: "auto" }}>
            {alerts === null ? (
              <p style={{ padding: 18 }} className="muted">Loading alerts…</p>
            ) : alerts.length === 0 ? (
              <p style={{ padding: 18 }} className="muted">
                {tab === "unconfirmed" ? "Nothing waiting to be checked. New alerts appear here as the sources find them." : "No alerts here."}
              </p>
            ) : (
              <table className="table">
                <thead>
                  <tr><th>Alert</th><th>Where</th><th>Severity</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {alerts.map((a) => (
                    <tr key={a.id} className="click" onClick={() => select(a.id)} style={selected === a.id ? { background: "var(--green-50)" } : undefined}>
                      <td>
                        <strong>{a.title}</strong>
                        <div className="muted small">
                          {ALERT_TYPES[a.type]} · {date(a.started_at ?? a.created_at)} · {a.from_gdacs ? "GDACS" : a.sources.length ? `${a.sources.length} source${a.sources.length > 1 ? "s" : ""}` : "Added by admin"}
                        </div>
                      </td>
                      <td>{a.places.map((p) => p.name).join(", ") || <span className="muted">Not placed</span>}</td>
                      <td><span className={`chip ${SEVERITY[a.severity].chip}`}>{SEVERITY[a.severity].label}</span></td>
                      <td><span className={`chip ${ALERT_STATUS[a.status].chip}`}>{ALERT_STATUS[a.status].label}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {adding && <AddAlert onClose={() => setAdding(false)} onSaved={(a) => { say(`Added ${a.title}`); setTab("confirmed"); select(a.id); }} />}
          {selected && !adding && <AlertPanel key={selected} id={selected} cats={cats} onClose={() => select(null)} onChanged={say} />}
        </div>

        <Sources onRan={say} />
      </main>
    </>
  );
}

// ---------- one alert ----------

function AlertPanel({ id, cats, onClose, onChanged }: { id: string; cats: Category[]; onClose: () => void; onChanged: (msg: string) => void }) {
  const [a, setA] = useState<Alert | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [camp, setCamp] = useState(false);

  useEffect(() => {
    api<Alert>(`/admin/alerts/${id}`).then(setA).catch((e) => setError(e.message));
  }, [id]);

  const status = async (s: AlertStatus, msg: string) => {
    setBusy(true);
    setError(null);
    try {
      setA(await api<Alert>(`/admin/alerts/${id}/status`, { method: "POST", body: JSON.stringify({ status: s }) }));
      onChanged(msg);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!a) {
    return (
      <aside className="card" style={{ flex: "1 1 380px" }}>
        {error ? <div className="flash bad" role="alert">{error}</div> : <p className="muted">Loading…</p>}
      </aside>
    );
  }

  const open = a.status === "unconfirmed" || a.status === "confirmed";
  const figures = Object.entries(a.figures).filter(([, v]) => v > 0);

  return (
    <aside className="card" style={{ flex: "1 1 380px", display: "flex", flexDirection: "column", gap: 14 }} aria-label="Alert details">
      <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
        <div style={{ marginRight: "auto" }}>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
            <span className={`chip ${SEVERITY[a.severity].chip}`}>{SEVERITY[a.severity].label}</span>
            <span className={`chip ${ALERT_STATUS[a.status].chip}`}>{ALERT_STATUS[a.status].label}</span>
            <span className="chip wait">{ALERT_TYPES[a.type]}</span>
          </div>
          <h2 style={{ margin: 0, fontSize: 18 }}>{a.title}</h2>
          <div className="muted small">Started {date(a.started_at ?? a.created_at)} · found {dateTime(a.created_at)}</div>
        </div>
        <button onClick={onClose} aria-label="Close" style={{ border: 0, background: "none", fontSize: 22, cursor: "pointer" }}>×</button>
      </div>

      {a.status === "unconfirmed" && (
        <div className="flash" style={{ background: "var(--warn-bg)", color: "var(--warn)", fontWeight: 600 }}>
          Found automatically. Open the sources, then confirm it or dismiss it. Unconfirmed alerts count for less on the needs map and donors do not see them.
        </div>
      )}

      <div>
        <label style={{ margin: 0 }}>Where</label>
        {a.places.length ? a.places.map((p) => <div key={p.id}>{p.path.join(" › ")}</div>) : <div className="muted">No place found in the text. Add the alert again by hand with the right place.</div>}
      </div>

      {a.summary && <p style={{ margin: 0 }}>{a.summary}</p>}

      {figures.length > 0 && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {figures.map(([k, v]) => (
            <div key={k}><div className="kpi-label">{FIGURES[k] ?? k}</div><div style={{ fontSize: 20, fontWeight: 800 }}>{v.toLocaleString()}</div></div>
          ))}
        </div>
      )}

      {a.sources.length > 0 && (
        <div>
          <label style={{ margin: 0 }}>Sources</label>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {a.sources.map((s, i) => (
              <li key={i}>
                {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a> : s.title}
                <span className="muted small">{s.publisher ? ` · ${s.publisher}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <div className="flash bad" role="alert">{error}</div>}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {a.status !== "confirmed" && a.status !== "handled" && (
          <button className="btn" disabled={busy} onClick={() => status("confirmed", `Confirmed: ${a.title}. Donors can see it now.`)}>Confirm</button>
        )}
        {a.status === "unconfirmed" && <button className="btn danger" disabled={busy} onClick={() => status("dismissed", "Dismissed")}>Dismiss</button>}
        {a.status === "confirmed" && <button className="btn ghost" disabled={busy} onClick={() => status("handled", `Marked handled: ${a.title}`)}>Mark handled</button>}
        {(a.status === "dismissed" || a.status === "handled") && (
          <button className="btn ghost" disabled={busy} onClick={() => status("unconfirmed", "Reopened")}>Reopen</button>
        )}
      </div>

      <NeedsTable alert={a} cats={cats} editable={open} onSaved={(x) => { setA(x); onChanged("Saved what is needed"); }} />

      <section style={{ borderTop: "1px solid var(--line)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>Relief camps</h3>
        {a.camps.length > 0 ? (
          a.camps.map((c) => (
            <div key={c.id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <strong style={{ marginRight: "auto" }}>{c.name}</strong>
              <span className={`chip ${c.is_active ? "ok" : "wait"}`}>{c.is_active ? "Open" : "Closed"}</span>
              <Link className="small" to="/points">Manage</Link>
            </div>
          ))
        ) : (
          <p className="muted small" style={{ margin: 0 }}>A relief camp is a temporary distribution point near the affected people. Riders deliver there and our team hands items out.</p>
        )}
        {open && !camp && <button className="btn ghost" onClick={() => setCamp(true)}>Open a relief camp</button>}
        {open && camp && (
          <CampForm alert={a} onCancel={() => setCamp(false)} onDone={(name) => {
            setCamp(false);
            api<Alert>(`/admin/alerts/${id}`).then(setA);
            onChanged(`Opened ${name}. It now shows in distribution points.`);
          }} />
        )}
      </section>
    </aside>
  );
}

function NeedsTable({ alert, cats, editable, onSaved }: { alert: Alert; cats: Category[]; editable: boolean; onSaved: (a: Alert) => void }) {
  const [rows, setRows] = useState(alert.needs.map((n) => ({ category_id: n.category_id, qty: n.quantity_needed?.toString() ?? "", pledged: n.quantity_pledged })));
  const [add, setAdd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const name = (id: number) => cats.find((c) => c.id === id)?.name ?? `#${id}`;

  useEffect(() => {
    setRows(alert.needs.map((n) => ({ category_id: n.category_id, qty: n.quantity_needed?.toString() ?? "", pledged: n.quantity_pledged })));
  }, [alert]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = rows.map((r) => ({ category_id: r.category_id, quantity_needed: r.qty.trim() ? Number(r.qty) : null }));
      onSaved(await api<Alert>(`/admin/alerts/${alert.id}/needs`, { method: "PUT", body: JSON.stringify(body) }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const unused = cats.filter((c) => !rows.some((r) => r.category_id === c.id));

  return (
    <section style={{ borderTop: "1px solid var(--line)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        <h3 style={{ margin: 0, fontSize: 15 }}>What is needed</h3>
        <p className="muted small" style={{ margin: "2px 0 0" }}>Suggested from the type of disaster and the families affected. Change it when the field team reports back. Empty = amount not known yet.</p>
      </div>
      {rows.length === 0 && <p className="muted small" style={{ margin: 0 }}>Nothing listed yet.</p>}
      {rows.map((r, i) => (
        <div key={r.category_id} style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ flex: 1 }}>{name(r.category_id)}</span>
          {r.pledged > 0 && <span className="muted small">{r.pledged} pledged</span>}
          <input className="input" style={{ width: 110, height: 36 }} inputMode="numeric" aria-label={`${name(r.category_id)} needed`} disabled={!editable}
            value={r.qty} placeholder="Not known" onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, qty: e.target.value.replace(/\D/g, "") } : x)))} />
          {editable && <button className="btn ghost small" aria-label={`Remove ${name(r.category_id)}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>}
        </div>
      ))}
      {editable && (
        <div style={{ display: "flex", gap: 8 }}>
          <select className="select" style={{ flex: 1 }} value={add} onChange={(e) => setAdd(e.target.value)} aria-label="Add a category">
            <option value="">Add a category…</option>
            {unused.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="btn ghost" disabled={!add} onClick={() => { setRows([...rows, { category_id: Number(add), qty: "", pledged: 0 }]); setAdd(""); }}>Add</button>
          <button className="btn" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save"}</button>
        </div>
      )}
      {error && <div className="flash bad" role="alert">{error}</div>}
    </section>
  );
}

function CampForm({ alert, onCancel, onDone }: { alert: Alert; onCancel: () => void; onDone: (name: string) => void }) {
  const first = alert.places[0];
  const [name, setName] = useState(first ? `${first.name} Relief Camp` : "");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState(first?.lat != null && first.lng != null ? `${first.lat}, ${first.lng}` : "");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [days, setDays] = useState("30");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const m = coords.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!m) return setError("Coordinates should look like 24.8607, 67.0011 (latitude, longitude)");
    if (!locationId) return setError("Choose the area of the camp");
    setBusy(true);
    try {
      await api(`/admin/alerts/${alert.id}/camp`, {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(), location_id: locationId, address: address.trim(), lat: parseFloat(m[1]), lng: parseFloat(m[2]),
          contact_name: contactName.trim() || null, contact_phone: contactPhone.trim() || null, open_days: Number(days) || 30,
        }),
      });
      onDone(name.trim());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10, background: "#fafbf9", border: "1px solid var(--line)", borderRadius: 12, padding: 12 }}>
      <div>
        <label htmlFor="cname">Camp name</label>
        <input id="cname" className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
      </div>
      <div>
        <label>Area</label>
        <LocationSelect allLabel="Choose" onChange={(id) => setLocationId(id)} />
      </div>
      <div>
        <label htmlFor="caddr">Address</label>
        <input id="caddr" className="input" value={address} onChange={(e) => setAddress(e.target.value)} required minLength={3} placeholder="Govt Boys School ground, main road" />
      </div>
      <div>
        <label htmlFor="ccoords">Coordinates (latitude, longitude)</label>
        <input id="ccoords" className="input" value={coords} onChange={(e) => setCoords(e.target.value)} required placeholder="34.7717, 72.3600" />
        <span className="muted small">Filled with the centre of the place. Replace it with the exact camp spot from Google Maps.</span>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 120px" }}>
          <label htmlFor="ccn">Contact person</label>
          <input id="ccn" className="input" value={contactName} onChange={(e) => setContactName(e.target.value)} />
        </div>
        <div style={{ flex: "1 1 120px" }}>
          <label htmlFor="ccp">Contact phone</label>
          <input id="ccp" className="input" value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} placeholder="0300 1234567" />
        </div>
        <div style={{ flex: "0 1 90px" }}>
          <label htmlFor="cdays">Open days</label>
          <input id="cdays" className="input" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))} />
        </div>
      </div>
      <span className="muted small">The camp takes the categories in "What is needed" and can hand out cooked food the same day.</span>
      {error && <div className="flash bad" role="alert">{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Opening…" : "Open camp"}</button>
        <button className="btn ghost" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

// ---------- add by hand ----------

function AddAlert({ onClose, onSaved }: { onClose: () => void; onSaved: (a: Alert) => void }) {
  const [type, setType] = useState("flood");
  const [severity, setSeverity] = useState("moderate");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [families, setFamilies] = useState("");
  const [people, setPeople] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!locationId) return setError("Choose where it happened");
    setBusy(true);
    setError(null);
    try {
      const figures: Record<string, number> = {};
      if (families) figures.families_affected = Number(families);
      if (people) figures.people_affected = Number(people);
      onSaved(await api<Alert>("/admin/alerts", {
        method: "POST",
        body: JSON.stringify({ type, severity, title: title.trim(), summary: summary.trim() || null, location_ids: [locationId], figures }),
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="card" style={{ flex: "1 1 380px" }} aria-label="Add an alert">
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: 18, marginRight: "auto" }}>Add an alert</h2>
          <button type="button" onClick={onClose} aria-label="Close" style={{ border: 0, background: "none", fontSize: 22, cursor: "pointer" }}>×</button>
        </div>
        <p className="muted small" style={{ margin: 0 }}>For something you heard about directly (field team, PDMA call). It is confirmed straight away.</p>
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <label htmlFor="atype">Type</label>
            <select id="atype" className="select" style={{ width: "100%" }} value={type} onChange={(e) => setType(e.target.value)}>
              {Object.entries(ALERT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label htmlFor="asev">Severity</label>
            <select id="asev" className="select" style={{ width: "100%" }} value={severity} onChange={(e) => setSeverity(e.target.value)}>
              {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label htmlFor="atitle">Title</label>
          <input id="atitle" className="input" value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3} placeholder="Flash floods in Swat" />
        </div>
        <div>
          <label>Where</label>
          <LocationSelect allLabel="Choose" onChange={(id) => setLocationId(id)} />
        </div>
        <div>
          <label htmlFor="asum">What happened (optional)</label>
          <textarea id="asum" className="input" style={{ height: 80, paddingTop: 10 }} value={summary} onChange={(e) => setSummary(e.target.value)} />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <label htmlFor="afam">Families affected</label>
            <input id="afam" className="input" inputMode="numeric" value={families} onChange={(e) => setFamilies(e.target.value.replace(/\D/g, ""))} />
          </div>
          <div style={{ flex: 1 }}>
            <label htmlFor="apeople">People affected</label>
            <input id="apeople" className="input" inputMode="numeric" value={people} onChange={(e) => setPeople(e.target.value.replace(/\D/g, ""))} />
          </div>
        </div>
        {error && <div className="flash bad" role="alert">{error}</div>}
        <button className="btn" type="submit" disabled={busy}>{busy ? "Adding…" : "Add alert"}</button>
      </form>
    </aside>
  );
}

// ---------- data sources ----------

function Sources({ onRan }: { onRan: (msg: string) => void }) {
  const [rows, setRows] = useState<DataSource[]>([]);
  const [running, setRunning] = useState<string | null>(null);

  const load = () => api<DataSource[]>("/admin/sources").then(setRows).catch(() => undefined);
  useEffect(() => {
    load();
  }, []);

  const run = async (s: DataSource) => {
    setRunning(s.kind);
    try {
      const r = await api<{ ok: boolean; status: string }>(`/admin/sources/${s.kind}/run`, { method: "POST" });
      onRan(`${s.name}: ${r.status}`);
    } catch (e) {
      onRan(`${s.name}: ${(e as Error).message}`);
    } finally {
      setRunning(null);
      load();
    }
  };

  const shown = rows.filter((r) => r.can_run || r.kind === "reliefweb");

  return (
    <section className="card" style={{ padding: 0, overflowX: "auto" }}>
      <div style={{ padding: "16px 18px 0" }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>Data sources</h2>
        <p className="muted small" style={{ margin: "2px 0 0" }}>Checked automatically while the backend runs. "Scan news" asks Claude to search official and news sites (about 1 minute, a few cents each time).</p>
      </div>
      <table className="table">
        <thead><tr><th>Source</th><th>Last run</th><th>Result</th><th /></tr></thead>
        <tbody>
          {shown.map((s) => (
            <tr key={s.kind}>
              <td><strong>{s.name}</strong><div className="muted small">{s.kind === "web_search" ? "When you run it" : s.can_run ? "Automatic" : "Waiting for ReliefWeb approval (Phase 6B)"}</div></td>
              <td>{ago(s.last_run_at)}</td>
              <td style={{ maxWidth: 380 }}>
                {s.last_status ? <span style={{ color: s.last_status.startsWith("Error") ? "var(--urgent)" : undefined }}>{s.last_status}</span> : <span className="muted">–</span>}
              </td>
              <td style={{ textAlign: "right" }}>
                {s.can_run && (
                  <button className="btn ghost small" disabled={running !== null} onClick={() => run(s)}>
                    {running === s.kind ? "Running…" : s.kind === "web_search" ? "Scan news now" : "Run now"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
