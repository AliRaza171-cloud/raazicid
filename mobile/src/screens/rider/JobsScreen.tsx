import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, type Job, type RiderSummary } from "../../api";
import { useAuth } from "../../auth";
import ReasonSheet from "../../components/ReasonSheet";
import { Button, ErrorBox } from "../../components/ui";
import { windowText } from "../../status";
import { colors, space } from "../../theme";

const LABEL: Record<string, string> = {
  assigned: "Assigned to you",
  accepted: "Accepted · go to pickup",
  picked_up: "Picked up · go to drop-off",
  delivered: "Delivered · record the hand-out",
};

export default function JobsScreen() {
  const navigation = useNavigation<any>();
  const { user } = useAuth();
  const [summary, setSummary] = useState<RiderSummary | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [declining, setDeclining] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([api<RiderSummary>("/rider/summary"), api<{ items: Job[] }>("/rider/jobs?filter=current")]);
      setSummary(s);
      setJobs(j.items);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
      const timer = setInterval(load, 30000);   // new jobs show up without pulling
      return () => clearInterval(timer);
    }, [load]),
  );

  const setAvailable = async (v: boolean) => {
    setSummary((s) => (s ? { ...s, is_available: v } : s));
    try {
      setSummary(await api<RiderSummary>("/rider/availability", { method: "PATCH", body: JSON.stringify({ is_available: v }) }));
    } catch (e) {
      setError((e as Error).message);
      load();
    }
  };

  const accept = async (job: Job) => {
    setBusy(job.id);
    try {
      await api(`/rider/jobs/${job.id}/accept`, { method: "POST" });
      await load();
      navigation.navigate("ActiveJob", { jobId: job.id });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const decline = async (reason: string) => {
    const job = declining!;
    setDeclining(null);
    setBusy(job.id);
    try {
      await api(`/rider/jobs/${job.id}/decline`, { method: "POST", body: JSON.stringify({ reason }) });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const open = (job: Job) => {
    if (job.status === "delivered") {
      navigation.navigate("HandOut", { donationId: job.donation_id, quantity: job.quantity, title: job.title, pointName: job.point?.name });
    } else {
      navigation.navigate("ActiveJob", { jobId: job.id });
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <ScrollView
        contentContainerStyle={{ padding: space(5), gap: space(4), paddingBottom: space(10) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      >
        <View style={{ flexDirection: "row", alignItems: "center" }}>
          <View style={{ flex: 1 }}>
            <Text style={st.h1}>Jobs</Text>
            <Text style={{ color: colors.muted }}>{user?.full_name}</Text>
          </View>
          <Text style={{ fontWeight: "700", color: summary?.is_available ? colors.primary : colors.muted, marginRight: 8 }}>
            {summary?.is_available ? "Available" : "Off duty"}
          </Text>
          <Switch
            accessibilityLabel="Available for jobs"
            value={!!summary?.is_available}
            onValueChange={setAvailable}
            trackColor={{ true: colors.primary }}
          />
        </View>

        <View style={{ flexDirection: "row", gap: 10 }}>
          <Stat value={summary?.done_today ?? "–"} label="Done today" />
          <Stat value={summary?.active_jobs ?? "–"} label="Active" />
          <Stat value={summary?.rating_avg ? summary.rating_avg.toFixed(1) : "–"} label="Rating" />
        </View>

        <ErrorBox message={error} />

        {jobs.length === 0 ? (
          <View style={st.empty}>
            <Text style={{ fontWeight: "700", color: colors.ink }}>No jobs right now</Text>
            <Text style={{ color: colors.muted, textAlign: "center" }}>
              {summary?.is_available ? "New jobs from the admin will show up here." : "Turn on Available so the admin can give you jobs."}
            </Text>
          </View>
        ) : (
          jobs.map((job) => (
            <View key={job.id} style={st.card}>
              <View style={{ flexDirection: "row", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <Text style={[st.pill, job.status === "assigned" ? { backgroundColor: colors.warnSoft, color: colors.warn } : null]}>{LABEL[job.status]}</Text>
                {job.food_type === "cooked" ? <Text style={[st.pill, { backgroundColor: colors.urgentSoft, color: colors.urgent }]}>Cooked food · go first</Text> : null}
                {job.trip_km != null ? <Text style={{ color: colors.muted, fontSize: 12 }}>{job.trip_km} km trip</Text> : null}
              </View>
              <Text style={st.title}>{job.title}</Text>
              <View style={{ gap: 6 }}>
                <Text style={st.meta}>
                  <Text style={st.metaLabel}>Pickup  </Text>
                  {job.pickup.address} · {windowText(job.pickup_from, job.pickup_to)}
                </Text>
                <Text style={st.meta}>
                  <Text style={st.metaLabel}>Drop-off  </Text>
                  {job.point ? `${job.point.name}, ${job.point.area.slice(-1)[0] ?? ""}` : "–"}
                </Text>
              </View>
              {job.status === "assigned" ? (
                <View style={{ flexDirection: "row", gap: 10 }}>
                  <View style={{ flex: 1 }}>
                    <Button label="Decline" variant="danger" onPress={() => setDeclining(job)} disabled={busy === job.id} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Button label="Accept job" onPress={() => accept(job)} loading={busy === job.id} />
                  </View>
                </View>
              ) : (
                <Button label={job.status === "delivered" ? "Record hand-out" : "Open job"} onPress={() => open(job)} />
              )}
            </View>
          ))
        )}
      </ScrollView>

      <ReasonSheet
        visible={declining !== null}
        title="Why are you declining?"
        presets={["Too far for me", "Vehicle problem", "Not free at that time"]}
        confirmLabel="Decline job"
        onCancel={() => setDeclining(null)}
        onConfirm={decline}
      />
    </SafeAreaView>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <View style={{ flex: 1, backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: colors.line, padding: 12 }}>
      <Text style={{ fontSize: 22, fontWeight: "800", color: colors.ink }}>{value}</Text>
      <Text style={{ fontSize: 12, color: colors.muted }}>{label}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  h1: { fontSize: 24, fontWeight: "800", color: colors.ink },
  card: { backgroundColor: "#fff", borderRadius: 16, borderWidth: 1, borderColor: colors.line, padding: 14, gap: 10 },
  pill: { fontSize: 11, fontWeight: "800", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden", backgroundColor: colors.primarySoft, color: colors.primaryDark },
  title: { fontSize: 17, fontWeight: "800", color: colors.ink },
  meta: { fontSize: 14, color: colors.ink2 },
  metaLabel: { fontWeight: "700", color: colors.muted },
  empty: { alignItems: "center", gap: 6, padding: 24, borderWidth: 2, borderStyle: "dashed", borderColor: colors.line2, borderRadius: 16 },
});
