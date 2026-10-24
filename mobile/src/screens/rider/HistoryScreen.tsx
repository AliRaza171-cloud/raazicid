import { useFocusEffect } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { FlatList, RefreshControl, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, type Job } from "../../api";
import { ErrorBox } from "../../components/ui";
import { dateTime } from "../../status";
import { colors, space } from "../../theme";

const LABEL: Record<string, { text: string; fg: string; bg: string }> = {
  delivered: { text: "Delivered", fg: colors.primaryDark, bg: colors.primarySoft },
  declined: { text: "Declined", fg: colors.muted, bg: colors.line },
  cancelled: { text: "Taken off you", fg: colors.warn, bg: colors.warnSoft },
};

export default function HistoryScreen() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setJobs((await api<{ items: Job[] }>("/rider/jobs?filter=history&limit=50")).items);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <Text style={{ fontSize: 24, fontWeight: "800", color: colors.ink, padding: space(5), paddingBottom: space(2) }}>History</Text>
      <View style={{ paddingHorizontal: space(5) }}>
        <ErrorBox message={error} />
      </View>
      <FlatList
        data={jobs ?? []}
        keyExtractor={(j: Job) => j.id}
        contentContainerStyle={{ padding: space(5), gap: space(3) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
        ListEmptyComponent={jobs ? <Text style={{ color: colors.muted }}>Finished jobs will show here.</Text> : null}
        renderItem={({ item: j }: { item: Job }) => {
          const l = LABEL[j.status] ?? { text: j.status, fg: colors.muted, bg: colors.line };
          return (
            <View style={{ backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: colors.line, padding: 14, gap: 4 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Text style={{ flex: 1, fontWeight: "700", color: colors.ink }} numberOfLines={1}>{j.title}</Text>
                <Text style={{ fontSize: 11, fontWeight: "800", color: l.fg, backgroundColor: l.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" }}>{l.text}</Text>
              </View>
              <Text style={{ fontSize: 12, color: colors.muted }}>
                {j.donation_ref} · {dateTime(j.delivered_at ?? j.assigned_at)}
                {j.point ? ` · ${j.point.name}` : ""}
              </Text>
              {j.decline_reason ? <Text style={{ fontSize: 13, color: colors.ink2 }}>{j.decline_reason}</Text> : null}
            </View>
          );
        }}
      />
    </SafeAreaView>
  );
}
