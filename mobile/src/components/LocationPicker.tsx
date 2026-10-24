// Province > City > Region > Area, one dropdown at a time, loaded from GET /locations.
import { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, type LocationItem } from "../api";
import { colors } from "../theme";

const LEVELS = [
  { key: "province", label: "Province" },
  { key: "city", label: "City" },
  { key: "region", label: "Region" },
  { key: "area", label: "Area" },
] as const;

type Picked = (LocationItem | null)[];

/** Calls onChange with the most specific place chosen so far (or null). */
export default function LocationPicker({ onChange }: { onChange: (locationId: string | null, path: string[]) => void }) {
  const [picked, setPicked] = useState<Picked>([null, null, null, null]);
  const [open, setOpen] = useState<number | null>(null);
  const [options, setOptions] = useState<LocationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [childrenExist, setChildrenExist] = useState<boolean[]>([true, true, true, true]);

  const parentId = open === null ? undefined : open === 0 ? null : picked[open - 1]?.id ?? null;

  useEffect(() => {
    if (parentId === undefined) return;
    let alive = true;
    setOptions([]);
    setLoading(true);
    setError(null);
    api<LocationItem[]>(parentId ? `/locations?parent_id=${parentId}` : "/locations")
      .then((rows) => alive && setOptions(rows))
      .catch((e: Error) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [open, parentId]);

  const choose = async (level: number, item: LocationItem) => {
    const next: Picked = picked.map((p, i) => (i < level ? p : i === level ? item : null));
    setPicked(next);
    setOpen(null);
    const chosen = next.filter(Boolean) as LocationItem[];
    onChange(item.id, chosen.map((c) => c.name));
    // Some cities have no regions yet: hide the next dropdown if there is nothing in it
    if (level < 3) {
      try {
        const kids = await api<LocationItem[]>(`/locations?parent_id=${item.id}`);
        setChildrenExist((prev) => prev.map((v, i) => (i === level + 1 ? kids.length > 0 : i > level + 1 ? true : v)));
      } catch {
        /* keep showing it */
      }
    }
  };

  return (
    <View style={{ gap: 10 }}>
      {LEVELS.map((lvl, i) => {
        const enabled = i === 0 || (picked[i - 1] !== null && childrenExist[i]);
        if (i > 0 && picked[i - 1] !== null && !childrenExist[i]) return null;
        return (
          <View key={lvl.key} style={{ gap: 6 }}>
            <Text style={st.label}>{lvl.label}</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Choose ${lvl.label}`}
              disabled={!enabled}
              onPress={() => setOpen(i)}
              style={[st.select, !enabled && { opacity: 0.5 }]}
            >
              <Text style={{ color: picked[i] ? colors.ink : "#8A928E", fontSize: 15 }}>
                {picked[i]?.name ?? (enabled ? `Choose ${lvl.label.toLowerCase()}` : `Choose ${LEVELS[i - 1]?.label.toLowerCase()} first`)}
              </Text>
            </Pressable>
          </View>
        );
      })}

      <Modal visible={open !== null} animationType="slide" onRequestClose={() => setOpen(null)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
          <View style={st.modalHead}>
            <Text style={{ fontSize: 18, fontWeight: "800", color: colors.ink }}>{open !== null ? `Choose ${LEVELS[open].label.toLowerCase()}` : ""}</Text>
            <Pressable accessibilityRole="button" onPress={() => setOpen(null)} style={{ padding: 10 }}>
              <Text style={{ color: colors.primary, fontWeight: "700" }}>Close</Text>
            </Pressable>
          </View>
          {loading ? (
            <View style={{ alignItems: "center", gap: 10, marginTop: 40 }}>
              <ActivityIndicator color={colors.primary} />
              <Text style={{ color: colors.muted }}>Loading places…</Text>
            </View>
          ) : null}
          {error ? <Text style={{ color: colors.urgent, padding: 20, fontWeight: "600" }}>{error}</Text> : null}
          {!loading && !error && options.length === 0 ? <Text style={{ color: colors.muted, padding: 20 }}>No places found.</Text> : null}
          <FlatList
            style={{ flex: 1 }}
            data={options}
            keyExtractor={(o) => o.id}
            renderItem={({ item }) => (
              <Pressable accessibilityRole="button" onPress={() => open !== null && choose(open, item)} style={st.row}>
                <Text style={{ fontSize: 16, color: colors.ink }}>{item.name}</Text>
              </Pressable>
            )}
          />
        </SafeAreaView>
      </Modal>
    </View>
  );
}

const st = StyleSheet.create({
  label: { fontSize: 13, fontWeight: "600", color: colors.ink2 },
  select: { height: 48, borderWidth: 1, borderColor: colors.line2, borderRadius: 12, paddingHorizontal: 14, justifyContent: "center", backgroundColor: "#fff" },
  modalHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 20, paddingVertical: 12, borderBottomWidth: 1, borderColor: colors.line },
  row: { paddingHorizontal: 20, paddingVertical: 16, borderBottomWidth: 1, borderColor: colors.line, backgroundColor: "#fff" },
});
