import { useNavigation, useRoute } from "@react-navigation/native";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Image, Linking, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { api, type Donation } from "../../api";
import { Button, ErrorBox } from "../../components/ui";
import { STATUS, dateTime, windowText } from "../../status";
import { colors, space } from "../../theme";

/** One donation: photos, status, pickup, where it is going and its history. */
export default function DonationDetailScreen() {
  const { params } = useRoute<any>() as { params: { id: string; justCreated?: boolean } };
  const navigation = useNavigation<any>();
  const [d, setD] = useState<Donation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    try {
      setD(await api<Donation>(`/donations/${params.id}`));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  const cancel = () =>
    Alert.alert("Cancel this donation?", "We will not pick it up.", [
      { text: "Keep it", style: "cancel" },
      {
        text: "Cancel donation",
        style: "destructive",
        onPress: async () => {
          setCancelling(true);
          try {
            setD(await api<Donation>(`/donations/${params.id}/cancel`, { method: "POST" }));
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setCancelling(false);
          }
        },
      },
    ]);

  if (!d) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, padding: space(5) }}>
        {error ? <ErrorBox message={error} /> : <ActivityIndicator style={{ marginTop: 40 }} color={colors.primary} />}
      </View>
    );
  }

  const s = STATUS[d.status];
  return (
    <ScrollView
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: space(5), gap: space(4), paddingBottom: space(10) }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
    >
      {params.justCreated && d.status === "in_review" ? (
        <View style={[st.banner, { backgroundColor: colors.primarySoft }]}>
          <Text style={{ fontWeight: "800", color: colors.primaryDark }}>Thank you! Your donation was sent.</Text>
          <Text style={{ color: colors.ink2 }}>We will review it and tell you where it goes.</Text>
        </View>
      ) : null}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
        {d.photos.map((url) => (
          <Image key={url} source={{ uri: url }} style={st.photo} accessibilityLabel="Donation photo" />
        ))}
      </ScrollView>

      <View style={{ gap: 6 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={[st.pill, { color: s.fg, backgroundColor: s.bg }]}>{s.label}</Text>
          <Text style={{ color: colors.muted, fontSize: 12 }}>{d.ref}</Text>
        </View>
        <Text style={st.h1}>{d.title}</Text>
        <Text style={{ color: colors.ink2 }}>
          {d.category.name} · {d.quantity}
          {d.condition ? ` · ${d.condition}` : ""}
          {d.food_type ? ` · ${d.food_type === "cooked" ? "cooked food" : "dry / packed food"}` : ""}
        </Text>
        {d.description ? <Text style={{ color: colors.ink2 }}>{d.description}</Text> : null}
      </View>

      {d.status === "rejected" && d.reject_reason ? (
        <View style={[st.banner, { backgroundColor: colors.urgentSoft }]}>
          <Text style={{ fontWeight: "800", color: colors.urgent }}>Why we could not accept it</Text>
          <Text style={{ color: colors.ink }}>{d.reject_reason}</Text>
        </View>
      ) : null}

      <View style={st.card}>
        <Row label="Pickup" value={`${d.pickup.address}\n${d.pickup.location_path.slice(-2).join(", ")}`} />
        <Row label="When" value={windowText(d.pickup.from, d.pickup.to)} />
        {d.ngo ? <Row label={d.status === "delivered" ? "Delivered to" : "Going to"} value={`${d.ngo.name}\n${d.ngo.location_path.slice(-2).join(", ")}`} /> : null}
      </View>

      {d.job && (d.status === "rider_assigned" || d.status === "picked_up") ? (
        <View style={st.card}>
          <Text style={{ fontWeight: "800", color: colors.ink }}>Your rider: {d.job.rider_name}</Text>
          <Text style={{ color: colors.muted }}>{d.job.vehicle}</Text>
          <Button label="Track rider" onPress={() => navigation.navigate("Tracking", { id: d.id })} />
          <Button label="Call rider" variant="outline" onPress={() => Linking.openURL(`tel:${d.job!.rider_phone}`)} />
        </View>
      ) : null}

      {d.status === "delivered" ? (
        <View style={[st.banner, { backgroundColor: colors.primarySoft }]}>
          <Text style={{ fontWeight: "800", color: colors.primaryDark }}>Delivered. Thank you!</Text>
          <Text style={{ color: colors.ink2 }}>
            Our rider gave your donation to {d.ngo?.name ?? "the NGO"}, who will pass it on to people in need.
          </Text>
        </View>
      ) : null}

      {d.proofs.length ? (
        <>
          <Text style={st.h2}>Proof photos</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {d.proofs.map((p) => (
              <View key={p.url + p.kind} style={{ gap: 4 }}>
                <Image source={{ uri: p.url }} style={[st.photo, { width: 160, height: 120 }]} accessibilityLabel={PROOF[p.kind]} />
                <Text style={{ fontSize: 12, color: colors.ink2, fontWeight: "600" }}>{PROOF[p.kind]}</Text>
              </View>
            ))}
          </ScrollView>
        </>
      ) : null}

      <Text style={st.h2}>History</Text>
      <View style={st.card}>
        {d.history.map((h, i) => (
          <View key={i} style={{ flexDirection: "row", gap: 10 }}>
            <View style={[st.dot, i === d.history.length - 1 && { backgroundColor: colors.primary }]} />
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: "700", color: colors.ink }}>{STATUS[h.to_status].label}</Text>
              {h.note ? <Text style={{ color: colors.ink2 }}>{h.note}</Text> : null}
              <Text style={{ fontSize: 12, color: colors.muted }}>{dateTime(h.at)}</Text>
            </View>
          </View>
        ))}
      </View>

      <ErrorBox message={error} />
      {d.can_cancel ? <Button label="Cancel donation" variant="danger" onPress={cancel} loading={cancelling} /> : null}
    </ScrollView>
  );
}

const PROOF = { pickup_proof: "Picked up from you", delivery_proof: "Handed to the NGO" } as const;

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: "row", gap: 12 }}>
      <Text style={{ width: 72, fontSize: 13, fontWeight: "600", color: colors.muted }}>{label}</Text>
      <Text style={{ flex: 1, color: colors.ink }}>{value}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  h1: { fontSize: 22, fontWeight: "800", color: colors.ink },
  h2: { fontSize: 16, fontWeight: "800", color: colors.ink },
  photo: { width: 220, height: 160, borderRadius: 14, backgroundColor: colors.line },
  pill: { fontSize: 12, fontWeight: "800", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, overflow: "hidden" },
  banner: { padding: 14, borderRadius: 14, gap: 4 },
  card: { backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: colors.line, padding: 14, gap: 14 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.line2, marginTop: 5 },
});
