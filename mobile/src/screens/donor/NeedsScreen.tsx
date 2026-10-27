import { useNavigation } from "@react-navigation/native";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { api, type AreaNeed, type AreaNeeds, type AreaRow } from "../../api";
import { useAuth } from "../../auth";
import { Button, Card, ErrorBox, Screen } from "../../components/ui";
import { LEVEL } from "../../status";
import { colors } from "../../theme";

type Crumb = { id: string | null; name: string };

/** What each area needs, starting at the donor's province. Tap a place to look inside it. */
export default function NeedsScreen() {
  const navigation = useNavigation<any>();
  const { user } = useAuth();
  const [trail, setTrail] = useState<Crumb[]>([{ id: null, name: "Pakistan" }]);
  const [data, setData] = useState<AreaNeeds | null>(null);
  const [open, setOpen] = useState<number | null>(null);   // category whose reasons are shown
  const [error, setError] = useState<string | null>(null);
  const startedAtHome = useRef(false);

  const here = trail[trail.length - 1];

  useEffect(() => {
    let alive = true;
    setData(null);
    setOpen(null);
    api<AreaNeeds>(here.id ? `/needs?parent_id=${here.id}` : "/needs")
      .then((d) => {
        if (!alive) return;
        // First visit: jump straight into the donor's own province
        const home = user?.location_path[0];
        if (!here.id && !startedAtHome.current && home) {
          startedAtHome.current = true;
          const row = d.children.find((c) => c.name === home);
          if (row) {
            setTrail([{ id: null, name: "Pakistan" }, { id: row.id, name: row.name }]);
            return;
          }
        }
        setData(d);
        setError(null);
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [here.id]);

  const donate = (n: AreaNeed, place: string) =>
    navigation.navigate("DonorTabs", { screen: "Donate", params: { categoryId: n.category_id, forText: `${n.name} in ${place}` } });

  const top = (data?.summary ?? []).filter((n) => n.level > 0).slice(0, 4);

  return (
    <Screen edges={["bottom"]}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
        {trail.map((c, i) => (
          <View key={c.id ?? "pk"} style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
            {i > 0 ? <Text style={{ color: colors.muted }}>›</Text> : null}
            {i < trail.length - 1 ? (
              <Pressable accessibilityRole="link" hitSlop={8} onPress={() => setTrail(trail.slice(0, i + 1))}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>{c.name}</Text>
              </Pressable>
            ) : (
              <Text style={{ color: colors.ink, fontWeight: "800" }}>{c.name}</Text>
            )}
          </View>
        ))}
      </View>

      <ErrorBox message={error} />
      {data === null && !error ? <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} /> : null}

      {data && here.id ? (
        <Card>
          <Text style={st.h}>Most needed in {here.name}</Text>
          {top.length === 0 ? (
            <Text style={{ color: colors.muted }}>No strong needs found here right now. Thank you for checking.</Text>
          ) : (
            top.map((n) => (
              <View key={n.category_id} style={{ gap: 6, paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.line }}>
                <Pressable accessibilityRole="button" accessibilityHint="Shows why" onPress={() => setOpen(open === n.category_id ? null : n.category_id)}
                  style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={{ flex: 1, fontWeight: "700", color: colors.ink, fontSize: 15 }}>{n.name}</Text>
                  <Level level={n.level} />
                  <Text style={{ color: colors.muted }}>{open === n.category_id ? "▴" : "▾"}</Text>
                </Pressable>
                {open === n.category_id ? (
                  <View style={{ gap: 6 }}>
                    {n.reasons.map((r, i) => (
                      <View key={i}>
                        <Text style={{ color: colors.ink2 }}>• {r.why}</Text>
                        <Text style={{ color: colors.muted, fontSize: 12, marginLeft: 10 }}>
                          {[r.place && r.place !== here.name ? r.place : null, r.date, r.fresh === "old" ? "older information" : null, r.source]
                            .filter(Boolean).join(" · ")}
                        </Text>
                      </View>
                    ))}
                    <Button label={`Donate ${n.name.toLowerCase()}`} onPress={() => donate(n, here.name)} />
                  </View>
                ) : null}
              </View>
            ))
          )}
        </Card>
      ) : null}

      {data && data.children.length ? (
        <View style={{ gap: 8 }}>
          <Text style={st.h}>{here.id ? `Places in ${here.name}` : "Provinces"}</Text>
          {data.children.map((row) => <PlaceRow key={row.id} row={row} onOpen={() => setTrail([...trail, { id: row.id, name: row.name }])} />)}
        </View>
      ) : null}

      <Text style={{ color: colors.muted, fontSize: 12 }}>
        Worked out from IPC food insecurity, food prices, poverty data, disaster alerts, displacement and recent news and reports.
      </Text>
    </Screen>
  );
}

function PlaceRow({ row, onOpen }: { row: AreaRow; onOpen: () => void }) {
  const shown = row.needs.filter((n) => n.level > 0).slice(0, 3);
  const body = (
    <Card>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
        <Text style={{ flex: 1, fontWeight: "800", color: colors.ink, fontSize: 15 }}>{row.name}</Text>
        {row.max_level > 0 ? <Level level={row.max_level} /> : null}
        {row.has_children ? <Text style={{ color: colors.muted, fontSize: 18 }}>›</Text> : null}
      </View>
      <Text style={{ color: colors.muted, fontSize: 13, marginTop: 4 }}>
        {shown.length ? shown.map((n) => `${n.name} (${LEVEL[n.level].label.toLowerCase()})`).join(" · ") : "No strong needs found"}
      </Text>
    </Card>
  );
  return row.has_children ? (
    <Pressable accessibilityRole="button" accessibilityLabel={`${row.name}, see places inside`} onPress={onOpen}>{body}</Pressable>
  ) : (
    body
  );
}

function Level({ level }: { level: number }) {
  const l = LEVEL[level];
  return (
    <Text style={{ fontSize: 11, fontWeight: "800", color: l.fg, backgroundColor: l.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" }}>
      {l.label}
    </Text>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 16, fontWeight: "800", color: colors.ink, marginBottom: 4 },
});
