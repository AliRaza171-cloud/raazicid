import { useEffect, useState, type FormEvent } from "react";
import LocationSelect from "./LocationSelect";
import { api, type Appeal, type Category, type LocationItem } from "../lib/api";

type Defaults = {
  title?: string;
  message?: string;
  locationId?: string | null;
  locationPath?: string[];
  categoryIds?: number[];
  alertId?: string | null;
};

/** Ask donors in chosen provinces to give specific items for an area. Sends an in-app notification to each donor. */
export default function AppealForm({ defaults = {}, cats, onSent, onCancel }: {
  defaults?: Defaults;
  cats: Category[];
  onSent: (a: Appeal) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(defaults.title ?? "");
  const [message, setMessage] = useState(defaults.message ?? "");
  const [locationId, setLocationId] = useState<string | null>(defaults.locationId ?? null);
  const [changePlace, setChangePlace] = useState(!defaults.locationId);
  const [picked, setPicked] = useState<number[]>(defaults.categoryIds ?? []);
  const [provinces, setProvinces] = useState<LocationItem[]>([]);
  const [target, setTarget] = useState<"area" | "all" | "choose">("area");
  const [chosen, setChosen] = useState<string[]>([]);
  const [days, setDays] = useState("14");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<LocationItem[]>("/locations").then(setProvinces).catch(() => undefined);
  }, []);

  const toggle = (id: number) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const toggleProv = (id: string) => setChosen((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!locationId) return setError("Choose the area the appeal is for");
    if (target === "choose" && chosen.length === 0) return setError("Choose at least one province");
    setBusy(true);
    try {
      const a = await api<Appeal>("/admin/appeals", {
        method: "POST",
        body: JSON.stringify({
          title: title.trim(), message: message.trim(), location_id: locationId, category_ids: picked,
          province_ids: target === "choose" ? chosen : [], all_pakistan: target === "all",
          alert_id: defaults.alertId ?? null, days: Number(days) || 14,
        }),
      });
      onSent(a);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10, background: "#fafbf9", border: "1px solid var(--line)", borderRadius: 12, padding: 12 }}>
      <div>
        <label htmlFor="aptitle">Title donors see</label>
        <input id="aptitle" className="input" value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3} maxLength={160} placeholder="Blankets needed in Lyari" />
      </div>
      <div>
        <label htmlFor="apmsg">Message</label>
        <textarea id="apmsg" className="input" style={{ height: 90, paddingTop: 10 }} value={message} onChange={(e) => setMessage(e.target.value)} required minLength={10} maxLength={1500}
          placeholder="Nights are getting cold and many families have no blankets. Donate through the app and our rider will collect." />
      </div>
      <div>
        <label>For which area</label>
        {changePlace ? (
          <LocationSelect allLabel="Choose" onChange={(id) => setLocationId(id)} />
        ) : (
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span style={{ flex: 1 }}>{(defaults.locationPath ?? []).join(" › ")}</span>
            <button type="button" className="btn ghost small" onClick={() => { setChangePlace(true); setLocationId(null); }}>Change</button>
          </div>
        )}
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", marginBottom: 6 }}>Items needed</legend>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 6 }}>
          {cats.map((c) => (
            <label key={c.id} style={{ display: "flex", gap: 6, alignItems: "center", margin: 0, fontWeight: 500 }}>
              <input type="checkbox" checked={picked.includes(c.id)} onChange={() => toggle(c.id)} /> {c.name}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", marginBottom: 6 }}>Send to donors in</legend>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
          <label style={{ display: "flex", gap: 6, margin: 0, fontWeight: 500 }}><input type="radio" checked={target === "area"} onChange={() => setTarget("area")} /> The area's province</label>
          <label style={{ display: "flex", gap: 6, margin: 0, fontWeight: 500 }}><input type="radio" checked={target === "choose"} onChange={() => setTarget("choose")} /> Chosen provinces</label>
          <label style={{ display: "flex", gap: 6, margin: 0, fontWeight: 500 }}><input type="radio" checked={target === "all"} onChange={() => setTarget("all")} /> All Pakistan</label>
        </div>
        {target === "choose" && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 6 }}>
            {provinces.map((p) => (
              <label key={p.id} style={{ display: "flex", gap: 6, margin: 0, fontWeight: 500 }}>
                <input type="checkbox" checked={chosen.includes(p.id)} onChange={() => toggleProv(p.id)} /> {p.name}
              </label>
            ))}
          </div>
        )}
      </fieldset>
      <div style={{ maxWidth: 160 }}>
        <label htmlFor="apdays">Show for (days)</label>
        <input id="apdays" className="input" inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))} />
      </div>
      {error && <div className="flash bad" role="alert">{error}</div>}
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn" type="submit" disabled={busy}>{busy ? "Sending…" : "Send appeal"}</button>
        <button className="btn ghost" type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
