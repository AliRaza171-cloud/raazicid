// A small map inside a WebView (Leaflet + free CARTO tiles), so no Google Maps key is needed in Expo Go.
import { useEffect, useRef } from "react";
import { View } from "react-native";
import { WebView } from "react-native-webview";
import { colors } from "../theme";

export type MapMarker = { lat: number; lng: number; label: string; kind: "pickup" | "point" | "rider" };
export type MapData = { markers: MapMarker[]; path: { lat: number; lng: number }[] };

const HTML = `<!doctype html><html><head>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#m{height:100%;margin:0}.pin{border-radius:50%;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)}</style>
</head><body><div id="m"></div><script>
var map = L.map('m', { zoomControl: false, attributionControl: true }).setView([24.86, 67.01], 12);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 19, attribution: '&copy; OpenStreetMap &copy; CARTO' }).addTo(map);
var layer = L.layerGroup().addTo(map), first = true;
var COLORS = { pickup: '#0F6B5C', point: '#2449A8', rider: '#D97706' };
window.update = function (data) {
  layer.clearLayers();
  var pts = [];
  if (data.path && data.path.length > 1) {
    L.polyline(data.path.map(function (p) { return [p.lat, p.lng]; }), { color: COLORS.rider, weight: 4, opacity: .7 }).addTo(layer);
  }
  data.markers.forEach(function (m) {
    var size = m.kind === 'rider' ? 22 : 18;
    var icon = L.divIcon({ className: '', html: '<div class="pin" style="width:' + size + 'px;height:' + size + 'px;background:' + COLORS[m.kind] + '"></div>', iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
    L.marker([m.lat, m.lng], { icon: icon }).bindTooltip(m.label).addTo(layer);
    pts.push([m.lat, m.lng]);
  });
  if (first && pts.length) { map.fitBounds(pts, { padding: [40, 40], maxZoom: 15 }); first = false; }
};
</script></body></html>`;

export default function MapView({ data, height = 260 }: { data: MapData | null; height?: number }) {
  const ref = useRef<WebView>(null);
  const loaded = useRef(false);

  const push = () => {
    if (data && loaded.current) ref.current?.injectJavaScript(`window.update(${JSON.stringify(data)}); true;`);
  };

  useEffect(push, [data]);

  return (
    <View style={{ height, borderRadius: 16, overflow: "hidden", backgroundColor: colors.line }} accessibilityLabel="Map">
      <WebView
        ref={ref}
        originWhitelist={["*"]}
        source={{ html: HTML, baseUrl: "https://raazicid.app/" }}
        onLoadEnd={() => {
          loaded.current = true;
          push();
        }}
        scrollEnabled={false}
      />
    </View>
  );
}
