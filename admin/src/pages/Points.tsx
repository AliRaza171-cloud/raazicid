import { useCallback, useEffect, useState, type FormEvent } from "react";
import LocationSelect from "../components/LocationSelect";
import { PageHeader } from "../components/Layout";
import { api, type Category, type Point, type PointDetail, type PointType } from "../lib/api";
import { POINT_TYPES, date, pointTypeLabel } from "../lib/format";

type Editing = { mode: "new" } | { mode: "edit"; id: string };

export default function Points() {
  const [points, setPoints] = useState<Point[] | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [locationId, setLocationId] = useState<string | null>(null);
  const [showClosed, setShowClosed] = useState(true);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (locationId) p.set("location_id", locationId);
    if (!showClosed) p.set("open_only", "true");
    api<Point[]>(`/points?${p}`)
      .then(setPoints)
      .catch((e) => setError(e.message));
  }, [locationId, showClosed]);

  useEffect(load, [load]);
  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const saved = (msg: string) => {
    setFlash(msg);
    load();
    window.setTimeout(() => setFlash(null), 4000);
  };

  const isOpen = (p: Point) => p.is_active && (!p.closes_at || new Date(p.closes_at) > new Date());

  return (
    <>
      <PageHeader title="Distribution points" sub="Places in needy areas where riders drop donations and our team hands them out.">
        <button className="btn" onClick={() => setEditing({ mode: "new" })}>+ Add a point</button>
      </PageHeader>
      <main className="page">
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <LocationSelect compact onChange={(id) => setLocationId(id)} />
          <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0, fontWeight: 600 }}>
            <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> Show closed points
          </label>
        </div>

        {flash && <div className="flash ok" role="status">{flash}</div>}
        {error && <div className="flash bad" role="alert">{error}</div>}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "2 1 480px", padding: 0, overflowX: "auto" }}>
            {points === null ? (
              <p style={{ padding: 18 }} className="muted">Loading points…</p>
            ) : points.length === 0 ? (
              <p style={{ padding: 18 }} className="muted">No distribution points yet. Add the first one so donations have somewhere to go.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Point</th>
                    <th>Location</th>
                    <th>Accepts</th>
                    <th>Last 30 days</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {points.map((p) => (
                    <tr key={p.id} className="click" onClick={() => setEditing({ mode: "edit", id: p.id })}
                      style={editing?.mode === "edit" && editing.id === p.id ? { background: "var(--green-50)" } : undefined}>
                      <td>
                        <button onClick={() => setEditing({ mode: "edit", id: p.id })} style={{ padding: 0, border: 0, background: "none", font: "inherit", fontWeight: 700, cursor: "pointer", textAlign: "left" }}>
                          {p.name}
                        </button>
                        <div className="muted small">{pointTypeLabel(p.type)}{p.contact_name ? ` · ${p.contact_name}` : ""}</div>
                      </td>
                      <td>
                        {p.location_path.slice(-2).join(" · ")}
                        <div className="muted small">{p.location_path[0]}</div>
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {p.same_day_food && <span className="chip ok">Same-day food</span>}
                          {p.categories.length === 0 ? (
                            <span className="chip wait">Everything</span>
                          ) : (
                            p.categories.map((c) => <span key={c.id} className="chip wait">{c.name}</span>)
                          )}
                        </div>
                      </td>
                      <td>
                        {p.items_30d} items
                        {p.open_requests > 0 && <div className="small" style={{ color: "var(--warn)", fontWeight: 700 }}>{p.open_requests} open request{p.open_requests > 1 ? "s" : ""}</div>}
                      </td>
                      <td>
                        {isOpen(p) ? (
                          <span className="chip ok">{p.closes_at ? `Closes ${date(p.closes_at)}` : "Active"}</span>
                        ) : (
                          <span className="chip bad">Closed</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {editing && (
            <PointPanel
              key={editing.mode === "edit" ? editing.id : "new"}
              editing={editing}
              cats={cats}
              onClose={() => setEditing(null)}
              onSaved={(p, created) => {
                saved(created ? `Added ${p.name}` : `Saved ${p.name}`);
                setEditing({ mode: "edit", id: p.id });
              }}
            />
          )}
        </div>
      </main>
    </>
  );
}

function PointPanel({ editing, cats, onClose, onSaved }: {
  editing: Editing;
  cats: Category[];
  onClose: () => void;
  onSaved: (p: PointDetail, created: boolean) => void;
}) {
  const [point, setPoint] = useState<PointDetail | null>(null);
  const [name, setName] = useState("");
  const [type, setType] = useState<PointType>("mosque");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [changeLocation, setChangeLocation] = useState(editing.mode === "new");
  const [address, setAddress] = useState("");
  const [coords, setCoords] = useState("");
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [accepts, setAccepts] = useState<number[]>([]);
  const [sameDayFood, setSameDayFood] = useState(false);
  const [active, setActive] = useState(true);
  const [closesAt, setClosesAt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fill = (p: PointDetail) => {
    setPoint(p);
    setName(p.name);
    setType(p.type);
    setLocationId(p.location_id);
    setAddress(p.address);
    setCoords(`${p.lat}, ${p.lng}`);
    setContactName(p.contact_name ?? "");
    setContactPhone(p.contact_phone ?? "");
    setAccepts(p.categories.map((c) => c.id));
    setSameDayFood(p.same_day_food);
    setActive(p.is_active);
    setClosesAt(p.closes_at ? p.closes_at.slice(0, 10) : "");
  };

  useEffect(() => {
    if (editing.mode === "edit") api<PointDetail>(`/points/${editing.id}`).then(fill).catch((e) => setError(e.message));
  }, [editing]);

  const toggle = (id: number) => setAccepts((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    // Accepts "24.8607, 67.0011" as copied from Google Maps (right-click on the map)
    const m = coords.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!m) return setError("Coordinates should look like 24.8607, 67.0011 (latitude, longitude)");
    if (!locationId) return setError("Choose the province, city and area of the point");
    const body = {
      name: name.trim(), type, location_id: locationId, address: address.trim(),
      lat: parseFloat(m[1]), lng: parseFloat(m[2]),
      contact_name: contactName.trim() || null, contact_phone: contactPhone.trim() || null,
      same_day_food: sameDayFood, is_active: active,
      closes_at: closesAt ? new Date(`${closesAt}T23:59:00`).toISOString() : null,
      category_ids: accepts,
    };
    setBusy(true);
    try {
      const out =
        editing.mode === "new"
          ? await api<PointDetail>("/admin/points", { method: "POST", body: JSON.stringify(body) })
          : await api<PointDetail>(`/admin/points/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      fill(out);
      setChangeLocation(false);
      onSaved(out, editing.mode === "new");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="card" style={{ flex: "1 1 360px", display: "flex", flexDirection: "column", gap: 14 }} aria-label="Point details">
      <div style={{ display: "flex", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: 18, marginRight: "auto" }}>{editing.mode === "new" ? "Add a distribution point" : point?.name ?? "Loading…"}</h2>
        <button onClick={onClose} aria-label="Close" style={{ border: 0, background: "none", fontSize: 22, cursor: "pointer" }}>×</button>
      </div>

      {(editing.mode === "new" || point) && (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label htmlFor="pname">Name</label>
            <input id="pname" className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} placeholder="Noor Community Point" />
          </div>
          <div>
            <label htmlFor="ptype">Type</label>
            <select id="ptype" className="select" style={{ width: "100%" }} value={type} onChange={(e) => setType(e.target.value as PointType)}>
              {POINT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label>Location</label>
            {changeLocation ? (
              <LocationSelect allLabel="Choose" onChange={(id) => setLocationId(id)} />
            ) : (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ flex: 1 }}>{point?.location_path.join(" › ")}</span>
                <button type="button" className="btn ghost small" onClick={() => { setChangeLocation(true); setLocationId(null); }}>Change</button>
              </div>
            )}
          </div>
          <div>
            <label htmlFor="paddr">Address</label>
            <input id="paddr" className="input" value={address} onChange={(e) => setAddress(e.target.value)} required minLength={3} placeholder="Near Chakiwara Chowk, Lyari" />
          </div>
          <div>
            <label htmlFor="pcoords">Coordinates (latitude, longitude)</label>
            <input id="pcoords" className="input" value={coords} onChange={(e) => setCoords(e.target.value)} required placeholder="24.8607, 67.0011" />
            <span className="muted small">In Google Maps, right-click the place and click the numbers to copy them. A map picker comes in Phase 4.</span>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <div style={{ flex: "1 1 140px" }}>
              <label htmlFor="pcname">Contact person</label>
              <input id="pcname" className="input" value={contactName} onChange={(e) => setContactName(e.target.value)} />
            </div>
            <div style={{ flex: "1 1 140px" }}>
              <label htmlFor="pcphone">Contact phone</label>
              <input id="pcphone" className="input" value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} placeholder="0300 1234567" />
            </div>
          </div>
          <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
            <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", marginBottom: 6 }}>Accepts (leave all unticked to accept everything)</legend>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 6 }}>
              {cats.map((c) => (
                <label key={c.id} style={{ display: "flex", gap: 6, alignItems: "center", margin: 0, fontWeight: 500 }}>
                  <input type="checkbox" checked={accepts.includes(c.id)} onChange={() => toggle(c.id)} /> {c.name}
                </label>
              ))}
            </div>
          </fieldset>
          <label style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}>
            <input type="checkbox" checked={sameDayFood} onChange={(e) => setSameDayFood(e.target.checked)} /> Can hand out cooked food the same day
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}>
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Open (riders can deliver here)
          </label>
          <div>
            <label htmlFor="pcloses">Closes on (temporary camps only)</label>
            <input id="pcloses" type="date" className="input" value={closesAt} onChange={(e) => setClosesAt(e.target.value)} />
          </div>
          {error && <div className="flash bad" role="alert">{error}</div>}
          <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : editing.mode === "new" ? "Add point" : "Save changes"}</button>
        </form>
      )}

      {point && <Requests point={point} cats={cats} onChange={() => api<PointDetail>(`/points/${point.id}`).then(fill)} />}
    </aside>
  );
}

function Requests({ point, cats, onChange }: { point: PointDetail; cats: Category[]; onChange: () => void }) {
  const [categoryId, setCategoryId] = useState("");
  const [qty, setQty] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api(`/points/${point.id}/requests`, { method: "POST", body: JSON.stringify({ category_id: Number(categoryId), quantity: Number(qty), note: note.trim() || null }) });
      setCategoryId("");
      setQty("");
      setNote("");
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const setStatus = async (id: string, status: "fulfilled" | "cancelled") => {
    try {
      await api(`/admin/point-requests/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
      onChange();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <section style={{ borderTop: "1px solid var(--line)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        <h3 style={{ margin: 0, fontSize: 15 }}>What people here are asking for</h3>
        <p className="muted small" style={{ margin: "2px 0 0" }}>Feeds "needs by area" in Phase 6.</p>
      </div>
      {point.requests.length === 0 && <p className="muted small" style={{ margin: 0 }}>No requests yet.</p>}
      {point.requests.map((r) => (
        <div key={r.id} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14 }}>
          <span style={{ flex: 1 }}>
            <strong>{r.quantity} × {r.category.name}</strong>
            {r.note ? ` · ${r.note}` : ""}
            <span className="muted small" style={{ display: "block" }}>{date(r.created_at)} · {r.requested_by_name}</span>
          </span>
          {r.status === "open" ? (
            <>
              <button className="btn ghost small" onClick={() => setStatus(r.id, "fulfilled")}>Fulfilled</button>
              <button className="btn ghost small" onClick={() => setStatus(r.id, "cancelled")} aria-label="Cancel request">×</button>
            </>
          ) : (
            <span className={`chip ${r.status === "fulfilled" ? "ok" : "wait"}`}>{r.status === "fulfilled" ? "Fulfilled" : "Cancelled"}</span>
          )}
        </div>
      ))}
      <form onSubmit={add} style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <select className="select" aria-label="Category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)} required style={{ flex: "1 1 140px" }}>
          <option value="">Category…</option>
          {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input className="input" aria-label="Quantity" type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} required placeholder="Qty" style={{ width: 80, height: 42 }} />
        <input className="input" aria-label="Note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optional)" style={{ flex: "1 1 140px", height: 42 }} />
        <button className="btn small" type="submit" style={{ height: 42 }}>Add</button>
      </form>
      {error && <div className="flash bad" role="alert">{error}</div>}
    </section>
  );
}
