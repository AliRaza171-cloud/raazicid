import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import LiveMap, { MapLegend, type MapMarker } from "../components/LiveMap";
import { PageHeader } from "../components/Layout";
import { api, type TrackingItem } from "../lib/api";

const REFRESH_MS = 15000;

/** Every active job on one map, refreshed every 15 s. Stalled jobs (no GPS for 10+ minutes) come first. */
export default function Tracking() {
  const [items, setItems] = useState<TrackingItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ lat: number; lng: number } | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback(() => {
    api<TrackingItem[]>("/admin/tracking")
      .then((data) => {
        setItems(data);
        setUpdated(new Date());
        setError(null);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
    const t = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(t);
  }, [load]);

  const markers = useMemo<MapMarker[]>(() => {
    const out: MapMarker[] = [];
    for (const i of items ?? []) {
      if (i.last) out.push({ id: `r-${i.job_id}`, lat: i.last.lat, lng: i.last.lng, label: `${i.rider_name} · ${i.title}`, kind: i.stalled ? "stalled" : "rider" });
      const dest = i.heading_to === "point" && i.point ? i.point : i.pickup;
      out.push({ id: `d-${i.job_id}`, lat: dest.lat, lng: dest.lng, label: `${i.heading_to === "point" ? dest.name : "Pickup"} · ${i.title}`, kind: i.heading_to === "point" ? "point" : "pickup" });
    }
    return out;
  }, [items]);

  return (
    <>
      <PageHeader title="Live tracking" sub={`Riders on a job. Updates every 15 s${updated ? ` · last ${updated.toLocaleTimeString("en-PK")}` : ""}.`} />
      <main className="page">
        {error && <div className="flash bad" role="alert">{error}</div>}
        <MapLegend />
        <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
          <div style={{ flex: "2 1 480px" }}>
            <LiveMap markers={markers} focus={focus} />
          </div>
          <section className="card" style={{ flex: "1 1 320px", display: "flex", flexDirection: "column", gap: 10 }}>
            <h2 style={{ margin: 0, fontSize: 16 }}>Active jobs · {items?.length ?? "–"}</h2>
            {items === null ? (
              <p className="muted">Loading…</p>
            ) : items.length === 0 ? (
              <p className="muted">No rider is on a job right now.</p>
            ) : (
              items.map((i) => (
                <div key={i.job_id} style={{ borderTop: "1px solid var(--line)", paddingTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <strong style={{ flex: 1 }}>{i.title}</strong>
                    {i.stalled ? <span className="chip bad">Stalled</span> : <span className={`chip ${i.heading_to === "point" ? "info" : "ok"}`}>{i.heading_to === "point" ? "Picked up" : i.job_status === "assigned" ? "Not accepted yet" : "To pickup"}</span>}
                  </div>
                  <span className="muted small">
                    {i.rider_name} · {i.heading_to === "point" ? `to ${i.point?.name}` : `pickup in ${i.pickup.area.slice(-1)[0] ?? ""}`}
                  </span>
                  <span className="small" style={{ color: i.stalled ? "var(--urgent)" : "var(--muted)" }}>
                    {i.minutes_since_ping === null ? "No GPS yet" : i.minutes_since_ping === 0 ? "GPS just now" : `GPS ${i.minutes_since_ping} min ago`}
                  </span>
                  <span style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                    {i.last && <button className="btn ghost small" onClick={() => setFocus({ lat: i.last!.lat, lng: i.last!.lng })}>Show on map</button>}
                    <a className="btn ghost small" href={`tel:${i.rider_phone}`}>Call rider</a>
                    <Link className="btn ghost small" to={`/donations/${i.donation_id}`}>Open {i.donation_ref}</Link>
                  </span>
                </div>
              ))
            )}
          </section>
        </div>
        <p className="muted small" style={{ margin: 0 }}>Riders share GPS while their job screen is open in the app. "Stalled" means no update for 10+ minutes; call the rider or reassign from the donation page.</p>
      </main>
    </>
  );
}
