import { useFocusEffect, useNavigation, useRoute } from "@react-navigation/native";
import * as Location from "expo-location";
import { useCallback, useRef, useState } from "react";
import { Image, Linking, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, type Job } from "../../api";
import ReasonSheet from "../../components/ReasonSheet";
import { Button, ErrorBox } from "../../components/ui";
import { directionsUrl, placeUrl, windowText } from "../../status";
import { colors, space } from "../../theme";

const STEPS = ["To pickup", "Picked up", "To drop-off", "Delivered"];
const PING_EVERY_MS = 15000;

/** The job the rider is doing now: where to go, who to call, and the proof buttons. Shares GPS while open. */
export default function ActiveJobScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const wantedId: string | undefined = route.params?.jobId;
  const [job, setJob] = useState<Job | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [sharing, setSharing] = useState<"off" | "on" | "denied">("off");
  const [declining, setDeclining] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastPing = useRef(0);

  const load = useCallback(async () => {
    try {
      const data = await api<{ items: Job[] }>("/rider/jobs?filter=current");
      const active = data.items.filter((j) => j.status === "accepted" || j.status === "picked_up");
      setJob(active.find((j) => j.id === wantedId) ?? active[0] ?? null);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoaded(true);
    }
  }, [wantedId]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  // Live location: only while this screen is open and the job is under way (Expo Go has no background GPS)
  useFocusEffect(
    useCallback(() => {
      if (!job) return;
      let sub: Location.LocationSubscription | null = null;
      let stopped = false;
      (async () => {
        const perm = await Location.requestForegroundPermissionsAsync();
        if (!perm.granted) {
          setSharing("denied");
          return;
        }
        if (stopped) return;
        sub = await Location.watchPositionAsync(
          { accuracy: Location.Accuracy.Balanced, timeInterval: PING_EVERY_MS, distanceInterval: 0 },
          (pos) => {
            const now = Date.now();
            if (now - lastPing.current < PING_EVERY_MS - 1000) return;
            lastPing.current = now;
            api(`/rider/jobs/${job.id}/ping`, { method: "POST", body: JSON.stringify({ lat: pos.coords.latitude, lng: pos.coords.longitude }) }).catch(() => undefined);
          },
        );
        setSharing("on");
      })();
      return () => {
        stopped = true;
        sub?.remove();
        setSharing("off");
      };
    }, [job?.id]),
  );

  const decline = async (reason: string) => {
    setDeclining(false);
    try {
      await api(`/rider/jobs/${job!.id}/decline`, { method: "POST", body: JSON.stringify({ reason }) });
      navigation.navigate("Jobs");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (!job) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg, padding: space(5), gap: 12 }} edges={["top"]}>
        <Text style={st.h1}>Active job</Text>
        <ErrorBox message={error} />
        {loaded ? (
          <View style={{ gap: 12 }}>
            <Text style={{ color: colors.muted }}>You have no job under way. Accept a job on the Jobs tab to start.</Text>
            <Button label="Go to Jobs" variant="outline" onPress={() => navigation.navigate("Jobs")} />
          </View>
        ) : null}
      </SafeAreaView>
    );
  }

  const toPoint = job.status === "picked_up";
  const dest = toPoint ? job.point! : job.pickup;
  const step = toPoint ? 2 : 0;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <ScrollView
        contentContainerStyle={{ padding: space(5), gap: space(4), paddingBottom: space(10) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      >
        <View style={{ flexDirection: "row", gap: 6 }}>
          {STEPS.map((s, i) => (
            <View key={s} style={{ flex: 1, gap: 4 }}>
              <View style={{ height: 5, borderRadius: 3, backgroundColor: i <= step ? colors.primary : colors.line2 }} />
              <Text style={{ fontSize: 11, fontWeight: i === step ? "800" : "500", color: i === step ? colors.ink : colors.muted }}>{s}</Text>
            </View>
          ))}
        </View>

        <View style={st.card}>
          <Text style={st.small}>{toPoint ? "Drop-off" : "Pickup"}</Text>
          <Text style={st.h2}>{toPoint ? dest.name : job.donor_name}</Text>
          <Text style={{ color: colors.ink2 }}>{dest.address}</Text>
          <Text style={{ color: colors.muted }}>{dest.area.join(", ")}</Text>
          {!toPoint ? <Text style={{ color: colors.ink2 }}>When: {windowText(job.pickup_from, job.pickup_to)}</Text> : null}
          <Text style={{ color: colors.ink2, fontWeight: "700" }}>{job.title} · {job.quantity} item{job.quantity === 1 ? "" : "s"}</Text>
          <Button label={toPoint ? "Navigate to drop-off in Google Maps" : "Navigate to pickup in Google Maps"} onPress={() => Linking.openURL(directionsUrl(dest.lat, dest.lng))} />
          {!toPoint && job.point ? (
            <Button label={`See drop-off: ${job.point.name ?? "distribution point"}`} variant="outline"
              onPress={() => Linking.openURL(placeUrl(job.point!.lat, job.point!.lng))} />
          ) : null}
        </View>

        {job.photos.length ? (
          <ScrollView horizontal contentContainerStyle={{ gap: 8 }} showsHorizontalScrollIndicator={false}>
            {job.photos.map((u) => <Image key={u} source={{ uri: u }} style={{ width: 120, height: 90, borderRadius: 10 }} accessibilityLabel="Donation photo" />)}
          </ScrollView>
        ) : null}
        {job.description ? <Text style={{ color: colors.ink2 }}>{job.description}</Text> : null}

        <View style={st.card}>
          {job.donor_phone ? <Contact label="Donor" name={job.donor_name} phone={job.donor_phone} /> : null}
          {job.point?.contact_phone ? <Contact label="Point contact" name={job.point.contact_name ?? job.point.name ?? ""} phone={job.point.contact_phone} /> : null}
        </View>

        <Text style={{ fontSize: 12, color: sharing === "on" ? colors.primary : colors.warn }}>
          {sharing === "on"
            ? "● Sharing your location with the donor and RAAZICID while this screen is open"
            : sharing === "denied"
              ? "Location permission is off. Turn it on so the donor can track you"
              : "Starting location sharing…"}
        </Text>

        <ErrorBox message={error} />
        <Button
          label={toPoint ? "I have arrived · upload delivery proof" : "I have the items · upload pickup proof"}
          onPress={() =>
            navigation.navigate("Proof", {
              jobId: job.id,
              kind: toPoint ? "deliver" : "pickup",
              title: job.title,
              quantity: job.quantity,
              placeName: toPoint ? dest.name : "the donor's place",
              target: { lat: dest.lat, lng: dest.lng },
            })
          }
        />
        {!toPoint ? <Button label="I can't do this job" variant="danger" onPress={() => setDeclining(true)} /> : null}
      </ScrollView>

      <ReasonSheet
        visible={declining}
        title="Why can't you do this job?"
        presets={["Donor not answering", "Vehicle problem", "Items too big for my vehicle"]}
        confirmLabel="Give the job back"
        onCancel={() => setDeclining(false)}
        onConfirm={decline}
      />
    </SafeAreaView>
  );
}

function Contact({ label, name, phone }: { label: string; name: string; phone: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
      <View style={{ flex: 1 }}>
        <Text style={st.small}>{label}</Text>
        <Text style={{ fontWeight: "700", color: colors.ink }}>{name}</Text>
      </View>
      <View style={{ width: 110 }}>
        <Button label="Call" variant="outline" onPress={() => Linking.openURL(`tel:${phone}`)} />
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  h1: { fontSize: 24, fontWeight: "800", color: colors.ink },
  h2: { fontSize: 18, fontWeight: "800", color: colors.ink },
  small: { fontSize: 12, fontWeight: "700", color: colors.muted, textTransform: "uppercase" },
  card: { backgroundColor: "#fff", borderRadius: 16, borderWidth: 1, borderColor: colors.line, padding: 14, gap: 8 },
});
