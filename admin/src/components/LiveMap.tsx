// Map for the admin (Leaflet + free OpenStreetMap tiles, loaded from a CDN so there is nothing extra to install).
// No API key: OpenStreetMap tiles first; if they fail, Esri's free street map instead.
import { useEffect, useRef } from "react";

export type MapMarker = { id: string; lat: number; lng: number; label: string; kind: "pickup" | "point" | "rider" | "stalled"; color?: string; size?: number };
export type MapLine = { id: string; points: { lat: number; lng: number }[] };

const COLORS = { pickup: "#0F6B5C", point: "#2449A8", rider: "#D97706", stalled: "#A2361A" };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Leaflet = any;
let loading: Promise<Leaflet> | null = null;

function loadLeaflet(): Promise<Leaflet> {
  const w = window as unknown as { L?: Leaflet };
  if (w.L) return Promise.resolve(w.L);
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(css);
      const js = document.createElement("script");
      js.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      js.onload = () => resolve(w.L);
      js.onerror = () => reject(new Error("Could not load the map. Check your internet connection."));
      document.head.appendChild(js);
    });
  }
  return loading;
}

/** OpenStreetMap tiles (no key). If several tiles fail to load, switch to Esri's free street map. */
function addBaseTiles(L: Leaflet, m: Leaflet) {
  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  });
  let errors = 0;
  osm.on("tileerror", () => {
    errors += 1;
    if (errors !== 3) return;
    m.removeLayer(osm);
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19,
      attribution: "Tiles &copy; Esri",
    }).addTo(m);
  });
  osm.addTo(m);
}

export default function LiveMap({
  markers,
  lines = [],
  focus,
  height = 480,
}: {
  markers: MapMarker[];
  lines?: MapLine[];
  focus?: { lat: number; lng: number } | null;
  height?: number;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<Leaflet>(null);
  const layer = useRef<Leaflet>(null);
  const fitted = useRef(false);
  const latest = useRef({ markers, lines });
  latest.current = { markers, lines };   // draw() always uses the newest data, even if the map loads late

  useEffect(() => {
    let cancelled = false;
    loadLeaflet().then((L) => {
      if (cancelled || !box.current || map.current) return;
      map.current = L.map(box.current, { zoomControl: true }).setView([30.3753, 69.3451], 5);   // Pakistan
      addBaseTiles(L, map.current);
      layer.current = L.layerGroup().addTo(map.current);
      draw();
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const draw = () => {
    const L = (window as unknown as { L?: Leaflet }).L;
    if (!L || !layer.current) return;
    layer.current.clearLayers();
    const { markers, lines } = latest.current;
    for (const line of lines) {
      if (line.points.length > 1) {
        L.polyline(line.points.map((p) => [p.lat, p.lng]), { color: COLORS.rider, weight: 4, opacity: 0.6 }).addTo(layer.current);
      }
    }
    const pts: [number, number][] = [];
    for (const m of markers) {
      const size = m.size ?? (m.kind === "rider" || m.kind === "stalled" ? 20 : 16);
      const icon = L.divIcon({
        className: "",
        html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${m.color ?? COLORS[m.kind]};border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      L.marker([m.lat, m.lng], { icon }).bindTooltip(m.label).addTo(layer.current);
      pts.push([m.lat, m.lng]);
    }
    if (!fitted.current && pts.length) {
      map.current.fitBounds(pts, { padding: [40, 40], maxZoom: 14 });
      fitted.current = true;
    }
  };

  useEffect(draw, [markers, lines]);

  useEffect(() => {
    if (focus && map.current) map.current.setView([focus.lat, focus.lng], 15);
  }, [focus]);

  return <div ref={box} style={{ height, width: "100%", borderRadius: 14, overflow: "hidden", background: "#e9ece7" }} role="region" aria-label="Map" />;
}

export function MapLegend() {
  const item = (c: string, t: string) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13 }}>
      <span style={{ width: 12, height: 12, borderRadius: 6, background: c, display: "inline-block" }} /> {t}
    </span>
  );
  return (
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
      {item(COLORS.rider, "Rider on a job")}
      {item(COLORS.stalled, "Stalled (no GPS 10+ min)")}
      {item(COLORS.pickup, "Pickup")}
      {item(COLORS.point, "Distribution point")}
    </div>
  );
}
