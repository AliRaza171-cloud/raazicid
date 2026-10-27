import { useFocusEffect, useRoute } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { Linking, ScrollView, StyleSheet, Text, View } from "react-native";
import { api, type Tracking } from "../../api";
import MapView, { type MapData } from "../../components/MapView";
import { Button, ErrorBox } from "../../components/ui";
import { STATUS, minutesAgo, placeUrl } from "../../status";
import { colors, space } from "../../theme";

/** Where is my donation? Map with the rider, refreshed every 15 seconds while this screen is open. */
export default function TrackingScreen() {
  const { params } = useRoute<any>() as { params: { id: string } };
  const [t, setT] = useState<Tracking | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      let alive = true;
      const load = () =>
        api<Tracking>(`/donations/${params.id}/tracking`)
          .then((data) => {
            if (!alive) return;
            setT(data);
            setError(null);
          })
          .catch((e) => alive && setError(e.message));
      load();
      const timer = setInterval(load, 15000);
      return () => {
        alive = false;
        clearInterval(timer);
      };
    }, [params.id]),
  );

  const map: MapData | null = t
    ? {
        markers: [
          { lat: t.pickup.lat, lng: t.pickup.lng, label: "Pickup", kind: "pickup" as const },
          ...(t.ngo && !t.ngo.approx ? [{ lat: t.ngo.lat, lng: t.ngo.lng, label: t.ngo.name ?? "NGO", kind: "ngo" as const }] : []),
          ...(t.last ? [{ lat: t.last.lat, lng: t.last.lng, label: t.rider?.full_name ?? "Rider", kind: "rider" as const }] : []),
        ],
        path: t.path,
      }
    : null;

  const headline = !t
    ? "Loading…"
    : t.donation_status === "rider_assigned"
      ? t.job_status === "assigned" ? "A rider has been assigned" : "The rider is coming to you"
      : t.donation_status === "picked_up"
        ? `On the way to ${t.ngo?.name ?? "the NGO"}`
        : STATUS[t.donation_status].label;

  return (
    <ScrollView style={{ backgroundColor: colors.bg }} contentContainerStyle={{ padding: space(5), gap: space(4) }}>
      <Text style={st.h1}>{headline}</Text>
      <MapView data={map} />
      <View style={{ flexDirection: "row", gap: 14, flexWrap: "wrap" }}>
        <Legend color={colors.primary} label="Pickup" />
        <Legend color="#2449A8" label="NGO" />
        <Legend color={colors.rider} label="Rider" />
      </View>
      <ErrorBox message={error} />

      {t?.rider ? (
        <View style={st.card}>
          <Text style={{ fontWeight: "800", fontSize: 16, color: colors.ink }}>{t.rider.full_name}</Text>
          <Text style={{ color: colors.muted }}>
            RAAZICID rider · {t.rider.vehicle_type} {t.rider.vehicle_number}
          </Text>
          <Text style={{ color: t.stalled ? colors.warn : colors.ink2 }}>
            {t.last ? `Location updated ${minutesAgo(t.last.at)}` : "Location appears once the rider starts the job"}
            {t.stalled ? " · not moving recently" : ""}
          </Text>
          {t.last ? <Button label="See rider in Google Maps" onPress={() => Linking.openURL(placeUrl(t.last!.lat, t.last!.lng))} /> : null}
          <Button label="Call rider" variant="outline" onPress={() => Linking.openURL(`tel:${t.rider!.phone}`)} />
        </View>
      ) : null}
      {t?.ngo && !t.ngo.approx ? (
        <Button label={`Where it goes: ${t.ngo.name ?? "the NGO"}`} variant="outline"
          onPress={() => Linking.openURL(placeUrl(t.ngo!.lat, t.ngo!.lng))} />
      ) : null}
      <Text style={{ fontSize: 12, color: colors.muted }}>Updates every 15 seconds. The rider's location is shared only while their job screen is open.</Text>
    </ScrollView>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
      <View style={{ width: 12, height: 12, borderRadius: 6, backgroundColor: color }} />
      <Text style={{ fontSize: 12, color: colors.ink2 }}>{label}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  h1: { fontSize: 20, fontWeight: "800", color: colors.ink },
  card: { backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: colors.line, padding: 14, gap: 8 },
});
