import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import LocationSelect from "../components/LocationSelect";
import { PageHeader } from "../components/Layout";
import PinPicker, { type Centre } from "../components/PinPicker";
import { api, type Category, type Ngo, type NgoSearch } from "../lib/api";

type Editing = { mode: "new" } | { mode: "edit"; ngo: Ngo };

/** NGOs, charities and welfare trusts where our riders drop donations. Found by web search or added by hand. */
export default function Ngos() {
  const [ngos, setNgos] = useState<Ngo[] | null>(null);
  const [cats, setCats] = useState<Category[]>([]);
  const [locationId, setLocationId] = useState<string | null>(null);
  const [placeName, setPlaceName] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [searchCat, setSearchCat] = useState("");
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const load = useCallback(() => {
    const p = new URLSearchParams();
    if (locationId) p.set("location_id", locationId);
    if (showHidden) p.set("include_hidden", "true");
    if (q.trim()) p.set("q", q.trim());
    api<Ngo[]>(`/admin/ngos?${p}`).then(setNgos).catch((e) => setError(e.message));
  }, [locationId, showHidden, q]);

  useEffect(load, [load]);
  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const search = async () => {
    if (!locationId) return setError("Choose a city first");
    setSearching(true);
    setError(null);
    setFlash(null);
    try {
      const r = await api<NgoSearch>("/admin/ngos/search", {
        method: "POST", body: JSON.stringify({ location_id: locationId, category_id: searchCat ? Number(searchCat) : null }),
      });
      setFlash(r.status);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSearching(false);
    }
  };

  const saved = (n: Ngo, created: boolean) => {
    setFlash(created ? `Added ${n.name}` : `Saved ${n.name}`);
    setEditing({ mode: "edit", ngo: n });
    load();
  };

  return (
    <>
      <PageHeader title="NGOs" sub="NGOs, charities and welfare trusts where our riders drop donations. They give the items to people in need.">
        <button className="btn" onClick={() => setEditing({ mode: "new" })}>+ Add an NGO</button>
      </PageHeader>
      <main className="page">
        <section className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: "3 1 420px" }}>
              <LocationSelect compact onChange={(id, path) => { setLocationId(id); setPlaceName(path[path.length - 1] ?? null); }} />
            </div>
            <input className="input" style={{ flex: "1 1 180px", height: 42 }} placeholder="Search by name" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search NGOs by name" />
            <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0, fontWeight: 600 }}>
              <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> Show hidden
            </label>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", borderTop: "1px solid var(--line)", paddingTop: 10 }}>
            <strong style={{ marginRight: 4 }}>Find NGOs on the web</strong>
            <span className="muted small">{placeName ? `in ${placeName}` : "choose a city above"}</span>
            <select className="select" value={searchCat} onChange={(e) => setSearchCat(e.target.value)} aria-label="Item the NGO should take">
              <option value="">Any donated goods</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <button className="btn" disabled={searching || !locationId} onClick={search}>{searching ? "Searching the web…" : "Search the web"}</button>
            <span className="muted small">Takes 1 to 3 minutes and uses AI credit. Call an NGO before the first delivery.</span>
          </div>
        </section>

        {searching && <div className="flash" style={{ background: "var(--info-bg)", color: "var(--info)" }} role="status">Searching the web for NGOs{placeName ? ` in ${placeName}` : ""} and finding their offices on the map…</div>}
        {flash && <div className="flash ok" role="status">{flash}</div>}
        {error && <div className="flash bad" role="alert">{error}</div>}

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <section className="card" style={{ flex: "2 1 520px", padding: 0, overflowX: "auto" }}>
            {ngos === null ? (
              <p style={{ padding: 18 }} className="muted">Loading NGOs…</p>
            ) : ngos.length === 0 ? (
              <p style={{ padding: 18 }} className="muted">
                No NGOs {placeName ? `in ${placeName} ` : ""}yet. Choose a city and press <strong>Search the web</strong>, or add one you know.
              </p>
            ) : (
              <table className="table">
                <thead><tr><th>NGO</th><th>City</th><th>Takes</th><th>Last 30 days</th><th>Found</th></tr></thead>
                <tbody>
                  {ngos.map((n) => (
                    <tr key={n.id} className="click" onClick={() => setEditing({ mode: "edit", ngo: n })}
                      style={editing?.mode === "edit" && editing.ngo.id === n.id ? { background: "var(--green-50)" } : n.is_active ? undefined : { opacity: 0.6 }}>
                      <td>
                        <strong>{n.name}</strong>
                        {!n.is_active && <span className="chip wait" style={{ marginLeft: 6 }}>Hidden</span>}
                        <div className="muted small">{[n.phone, n.about].filter(Boolean).join(" · ")}</div>
                      </td>
                      <td>
                        {n.location_path.slice(-1)[0]}
                        <div className="muted small">{n.location_path[0]}</div>
                        {n.location_approx && <span className="chip" style={{ background: "var(--warn-bg)", color: "var(--warn)" }} title="Only the city centre is known">Address not on map</span>}
                        {n.place_warning && <span className="chip bad" title={n.place_warning}>Pin in the wrong place?</span>}
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                          {n.takes_cooked_food && <span className="chip ok">Cooked food</span>}
                          {n.categories.length === 0 ? <span className="chip wait">Everything</span>
                            : n.categories.map((c) => <span key={c.id} className="chip wait">{c.name}</span>)}
                        </div>
                      </td>
                      <td>{n.items_30d} donations</td>
                      <td className="small">
                        {n.found_by === "web_search" ? "Web search" : "Added by admin"}
                        {n.source_url && <div><a href={n.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Source</a></div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {editing && (
            <NgoPanel key={editing.mode === "edit" ? editing.ngo.id : "new"} editing={editing} cats={cats}
              onClose={() => setEditing(null)} onSaved={saved} />
          )}
        </div>
      </main>
    </>
  );
}

function NgoPanel({ editing, cats, onClose, onSaved }: {
  editing: Editing;
  cats: Category[];
  onClose: () => void;
  onSaved: (n: Ngo, created: boolean) => void;
}) {
  const start = editing.mode === "edit" ? editing.ngo : null;
  const [name, setName] = useState(start?.name ?? "");
  const [locationId, setLocationId] = useState<string | null>(start?.location_id ?? null);
  const [changeLocation, setChangeLocation] = useState(!start);
  const [address, setAddress] = useState(start?.address ?? "");
  const [coords, setCoords] = useState(start ? `${start.lat}, ${start.lng}` : "");
  const [phone, setPhone] = useState(start?.phone ?? "");
  const [website, setWebsite] = useState(start?.website ?? "");
  const [about, setAbout] = useState(start?.about ?? "");
  const [cooked, setCooked] = useState(start?.takes_cooked_food ?? false);
  const [accepts, setAccepts] = useState<number[]>(start?.categories.map((c) => c.id) ?? []);
  const [active, setActive] = useState(start?.is_active ?? true);
  const [centre, setCentre] = useState<Centre | null>(start ? { name: start.location_path.slice(-1)[0] ?? "", lat: start.lat, lng: start.lng } : null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const m = coords.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
  const pinAt = useMemo(() => (m ? { lat: parseFloat(m[1]), lng: parseFloat(m[2]) } : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [coords]);
  const toggle = (id: number) => setAccepts((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!locationId) return setError("Choose the NGO's city");
    if (!pinAt) return setError("Drop the pin on the map where the NGO's office is");
    const body = {
      name: name.trim(), location_id: locationId, address: address.trim(), lat: pinAt.lat, lng: pinAt.lng,
      phone: phone.trim() || null, website: website.trim() || null, about: about.trim() || null,
      takes_cooked_food: cooked, category_ids: accepts, ...(start ? { is_active: active } : {}),
    };
    setBusy(true);
    setError(null);
    try {
      const out = start
        ? await api<Ngo>(`/admin/ngos/${start.id}`, { method: "PATCH", body: JSON.stringify(body) })
        : await api<Ngo>("/admin/ngos", { method: "POST", body: JSON.stringify(body) });
      onSaved(out, !start);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="card" style={{ flex: "1 1 360px", display: "flex", flexDirection: "column", gap: 14 }} aria-label="NGO details">
      <div style={{ display: "flex", alignItems: "center" }}>
        <h2 style={{ margin: 0, fontSize: 18, marginRight: "auto" }}>{start ? start.name : "Add an NGO"}</h2>
        <button onClick={onClose} aria-label="Close" style={{ border: 0, background: "none", fontSize: 22, cursor: "pointer" }}>×</button>
      </div>
      {start?.found_by === "web_search" && (
        <div className="flash" style={{ background: "var(--info-bg)", color: "var(--info)" }}>
          Found by web search{start.source_url ? <> (<a href={start.source_url} target="_blank" rel="noreferrer">source</a>)</> : ""}.
          Call them before the first delivery to check they take donations.
        </div>
      )}
      {start?.location_approx && (
        <div className="flash" style={{ background: "var(--warn-bg)", color: "var(--warn)" }}>
          Only the city centre is known. Drop the pin on their office, or the first rider's delivery will set it.
        </div>
      )}
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div>
          <label htmlFor="nname">Name</label>
          <input id="nname" className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} placeholder="Hyderabad Welfare Trust" />
        </div>
        <div>
          <label>City</label>
          {changeLocation ? (
            <LocationSelect allLabel="Choose" onChange={(id, _path, chosen) => {
              setLocationId(id);
              const c = [...chosen].reverse().find((x) => x.level !== "province" && x.lat != null && x.lng != null);
              setCentre(c ? { name: c.name, lat: c.lat as number, lng: c.lng as number } : null);
            }} />
          ) : (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ flex: 1 }}>{start?.location_path.join(" › ")}</span>
              <button type="button" className="btn ghost small" onClick={() => { setChangeLocation(true); setLocationId(null); }}>Change</button>
            </div>
          )}
        </div>
        <div>
          <label htmlFor="naddr">Office address</label>
          <input id="naddr" className="input" value={address} onChange={(e) => setAddress(e.target.value)} required minLength={3} placeholder="Latifabad Unit 7, near the post office" />
        </div>
        <div>
          <label>Where is the office?</label>
          <PinPicker value={pinAt} centre={centre} address={address} onChange={(at) => setCoords(`${at.lat}, ${at.lng}`)} />
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 140px" }}>
            <label htmlFor="nphone">Phone</label>
            <input id="nphone" className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="022 1234567" />
          </div>
          <div style={{ flex: "1 1 160px" }}>
            <label htmlFor="nweb">Website</label>
            <input id="nweb" className="input" value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="example.org.pk" />
          </div>
        </div>
        <div>
          <label htmlFor="nabout">What they do</label>
          <input id="nabout" className="input" value={about} onChange={(e) => setAbout(e.target.value)} placeholder="Runs a shelter and a free kitchen for poor families" />
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", marginBottom: 6 }}>Takes (leave all unticked if they take everything)</legend>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 6 }}>
            {cats.map((c) => (
              <label key={c.id} style={{ display: "flex", gap: 6, alignItems: "center", margin: 0, fontWeight: 500 }}>
                <input type="checkbox" checked={accepts.includes(c.id)} onChange={() => toggle(c.id)} /> {c.name}
              </label>
            ))}
          </div>
        </fieldset>
        <label style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}>
          <input type="checkbox" checked={cooked} onChange={(e) => setCooked(e.target.checked)} /> Takes cooked food (gives it out the same day)
        </label>
        {start && (
          <label style={{ display: "flex", gap: 8, alignItems: "center", margin: 0 }}>
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Show this NGO (untick to hide it from the list and from donation choices)
          </label>
        )}
        {error && <div className="flash bad" role="alert">{error}</div>}
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : start ? "Save changes" : "Add NGO"}</button>
      </form>
    </aside>
  );
}
