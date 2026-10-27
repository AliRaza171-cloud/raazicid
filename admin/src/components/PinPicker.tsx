// Put an NGO office on the map: click the exact spot or drag the pin. Address search uses OpenStreetMap
// Nominatim (free, no key; one search per button press). "Use my location" uses the browser's GPS.
import { useEffect, useRef, useState } from "react";
import { addBaseTiles, loadLeaflet } from "./LiveMap";

export type LatLng = { lat: number; lng: number };
export type Centre = { name: string; lat: number; lng: number };
type Found = { name: string; lat: number; lng: number };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Leaflet = any;

const PAKISTAN: [number, number] = [30.3753, 69.3451];

function pinIcon(L: Leaflet) {
  return L.divIcon({
    className: "",
    html: `<svg width="30" height="42" viewBox="0 0 30 42" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,.4))">
      <path d="M15 1C7.3 1 1 7.2 1 14.9 1 25.3 15 41 15 41s14-15.7 14-26.1C29 7.2 22.7 1 15 1z" fill="#A2361A" stroke="#fff" stroke-width="2"/>
      <circle cx="15" cy="15" r="5" fill="#fff"/></svg>`,
    iconSize: [30, 42],
    iconAnchor: [15, 41],   // the tip of the pin is the spot
  });
}

export default function PinPicker({
  value,
  onChange,
  centre,
  address,
  height = 280,
}: {
  value: LatLng | null;
  onChange: (p: LatLng) => void;
  centre: Centre | null;      // the chosen city / area: where to look first
  address: string;            // used for the search when the search box is empty
  height?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<Leaflet>(null);
  const pin = useRef<Leaflet>(null);
  const change = useRef(onChange);
  change.current = onChange;
  const [ready, setReady] = useState(false);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Found[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const place = (p: LatLng, zoom?: number) => {
    const L = (window as unknown as { L?: Leaflet }).L;
    if (!L || !map.current) return;
    if (!pin.current) {
      pin.current = L.marker([p.lat, p.lng], { icon: pinIcon(L), draggable: true, autoPan: true }).addTo(map.current);
      pin.current.on("dragend", () => {
        const at = pin.current.getLatLng();
        change.current({ lat: round(at.lat), lng: round(at.lng) });
      });
    } else {
      pin.current.setLatLng([p.lat, p.lng]);
    }
    if (zoom) map.current.setView([p.lat, p.lng], zoom);
  };

  useEffect(() => {
    let cancelled = false;
    loadLeaflet()
      .then((L) => {
        if (cancelled || !box.current || map.current) return;
        const start = value ? { at: [value.lat, value.lng], zoom: 16 } : centre ? { at: [centre.lat, centre.lng], zoom: 13 } : { at: PAKISTAN, zoom: 5 };
        map.current = L.map(box.current, { zoomControl: true }).setView(start.at, start.zoom);
        addBaseTiles(L, map.current);
        map.current.on("click", (e: { latlng: { lat: number; lng: number } }) => {
          const p = { lat: round(e.latlng.lat), lng: round(e.latlng.lng) };
          place(p);
          change.current(p);
        });
        if (value) place(value);
        setReady(true);
      })
      .catch((e: Error) => setNote(e.message));
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      pin.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Typed coordinates (or a saved point loading) move the pin
  useEffect(() => {
    if (!ready || !value) return;
    const at = pin.current?.getLatLng();
    if (!at || Math.abs(at.lat - value.lat) > 1e-6 || Math.abs(at.lng - value.lng) > 1e-6) {
      place(value);
      if (!at || !map.current.getBounds().contains([value.lat, value.lng])) map.current.setView([value.lat, value.lng], 16);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, value?.lat, value?.lng]);

  // A new city or area chosen, or the pin is far from it: look there (the pin stays until you click the right spot)
  useEffect(() => {
    const far = !value || Math.abs(value.lat - (centre?.lat ?? 0)) > 0.3 || Math.abs(value.lng - (centre?.lng ?? 0)) > 0.3;
    if (ready && centre && far) map.current.setView([centre.lat, centre.lng], 13);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, centre?.lat, centre?.lng]);

  const search = async () => {
    const q = (query.trim() || [address.trim(), centre?.name].filter(Boolean).join(", ")).trim();
    if (q.length < 3) return setNote("Type an address or a landmark to search");
    setBusy(true);
    setNote(null);
    setFound(null);
    try {
      const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=pk&limit=5&accept-language=en&q=${encodeURIComponent(q)}`;
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error();
      const rows = (await res.json()) as { display_name: string; lat: string; lon: string }[];
      const list = rows.map((r) => ({ name: r.display_name, lat: Number(r.lat), lng: Number(r.lon) }));
      if (!list.length) setNote(`Nothing found for "${q}". Try a nearby landmark or road, or just click the map.`);
      setFound(list);
    } catch {
      setNote("Search is not available right now. Click the map instead.");
    } finally {
      setBusy(false);
    }
  };

  const pick = (f: Found) => {
    const p = { lat: round(f.lat), lng: round(f.lng) };
    place(p, 17);
    change.current(p);
    setFound(null);
    setNote("Pin moved. Zoom in and drag it onto the exact building if needed.");
  };

  const mine = () => {
    if (!navigator.geolocation) return setNote("This browser cannot share its location");
    setNote("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const p = { lat: round(pos.coords.latitude), lng: round(pos.coords.longitude) };
        place(p, 17);
        change.current(p);
        setNote(`Pin set to where you are (accurate to about ${Math.round(pos.coords.accuracy)} m).`);
      },
      () => setNote("Could not get your location. Allow location access, or click the map."),
      { enableHighAccuracy: true, timeout: 15000 },
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          className="input"
          style={{ flex: 1 }}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              search();
            }
          }}
          placeholder={address ? `Search: ${address}${centre ? `, ${centre.name}` : ""}` : "Search an address or landmark"}
          aria-label="Search an address"
        />
        <button type="button" className="btn ghost small" onClick={search} disabled={busy}>{busy ? "…" : "Find"}</button>
      </div>
      {found && found.length > 0 && (
        <div style={{ border: "1px solid var(--line)", borderRadius: 10, overflow: "hidden" }}>
          {found.map((f, i) => (
            <button key={i} type="button" onClick={() => pick(f)}
              style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px", border: 0, borderTop: i ? "1px solid var(--line)" : 0, background: "#fff", cursor: "pointer", font: "inherit", fontSize: 13 }}>
              {f.name}
            </button>
          ))}
        </div>
      )}
      <div ref={box} style={{ height, width: "100%", borderRadius: 12, overflow: "hidden", background: "#e9ece7", cursor: "crosshair" }} role="application" aria-label="Map: click to place the point" />
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        {centre && <button type="button" className="btn ghost small" onClick={() => map.current?.setView([centre.lat, centre.lng], 13)}>Go to {centre.name}</button>}
        <button type="button" className="btn ghost small" onClick={mine}>Use my location</button>
        {value && <button type="button" className="btn ghost small" onClick={() => map.current?.setView([value.lat, value.lng], 17)}>Show the pin</button>}
      </div>
      <span className="muted small">
        {value ? "Drag the pin or click elsewhere to move it." : "Click the exact building on the map to drop the pin."}
        {" "}Search by OpenStreetMap.
      </span>
      {note && <span className="small" role="status">{note}</span>}
    </div>
  );
}

const round = (n: number) => Math.round(n * 1e6) / 1e6;
