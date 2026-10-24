import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Image, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, type DonationListItem } from "../../api";
import { Chips, ErrorBox } from "../../components/ui";
import { STATUS, shortDate } from "../../status";
import { colors, space } from "../../theme";

type Filter = "active" | "done" | "all";

export default function DonationsScreen() {
  const navigation = useNavigation<any>();
  const [filter, setFilter] = useState<Filter>("active");
  const [items, setItems] = useState<DonationListItem[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await api<{ items: DonationListItem[] }>(`/donations/mine?filter=${filter}&limit=50`);
      setItems(data.items);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [filter]);

  // Reload every time the tab is opened, so status changes show up
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const note = (d: DonationListItem) =>
    d.status === "accepted" && d.point_name ? `Going to ${d.point_name}` : d.status === "in_review" ? "We are reviewing it" : null;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }} edges={["top"]}>
      <View style={{ padding: space(5), paddingBottom: space(2), gap: space(3) }}>
        <Text style={st.h1}>My donations</Text>
        <Chips
          options={[{ value: "active", label: "Active" }, { value: "done", label: "Completed" }, { value: "all", label: "All" }]}
          value={filter}
          onChange={(f) => {
            setItems(null);
            setFilter(f);
          }}
        />
        <ErrorBox message={error} />
      </View>
      {items === null && !error ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.primary} />
      ) : (
        <FlatList
          data={items ?? []}
          keyExtractor={(d: DonationListItem) => d.id}
          contentContainerStyle={{ padding: space(5), paddingTop: space(2), gap: space(3) }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
          ListEmptyComponent={
            <View style={{ alignItems: "center", gap: 12, marginTop: 40 }}>
              <Text style={{ color: colors.muted }}>{filter === "done" ? "No completed donations yet." : "Nothing here yet."}</Text>
              <Pressable accessibilityRole="button" onPress={() => navigation.navigate("Donate")}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Make a donation</Text>
              </Pressable>
            </View>
          }
          renderItem={({ item: d }: { item: DonationListItem }) => {
            const s = STATUS[d.status];
            return (
              <Pressable accessibilityRole="button" onPress={() => navigation.navigate("DonationDetail", { id: d.id })} style={st.card}>
                {d.photo_url ? <Image source={{ uri: d.photo_url }} style={st.thumb} /> : <View style={[st.thumb, { backgroundColor: colors.line }]} />}
                <View style={{ flex: 1, gap: 4 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <Text style={st.title} numberOfLines={1}>{d.title}</Text>
                    <Text style={[st.pill, { color: s.fg, backgroundColor: s.bg }]}>{s.label}</Text>
                  </View>
                  <Text style={st.meta}>{d.category.name} · {shortDate(d.created_at)} · {d.ref}</Text>
                  {note(d) ? <Text style={st.note}>{note(d)}</Text> : null}
                </View>
              </Pressable>
            );
          }}
        />
      )}
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  h1: { fontSize: 22, fontWeight: "800", color: colors.ink },
  card: { flexDirection: "row", gap: 12, padding: 12, backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: colors.line, alignItems: "center" },
  thumb: { width: 60, height: 60, borderRadius: 10 },
  title: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.ink },
  pill: { fontSize: 11, fontWeight: "800", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" },
  meta: { fontSize: 12, color: colors.muted },
  note: { fontSize: 12, color: colors.ink2 },
});
