import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, Text, View } from "react-native";
import { api, type DisasterAlert } from "../../api";
import { Button, Card, ErrorBox, Screen } from "../../components/ui";
import { FIGURE_LABELS, SEVERITY, shortDate } from "../../status";
import { colors } from "../../theme";

/** Disasters our team has confirmed in the last 30 days, with what is needed and where the relief camps are. */
export default function AlertsScreen() {
  const navigation = useNavigation<any>();
  const [alerts, setAlerts] = useState<DisasterAlert[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      api<DisasterAlert[]>("/alerts")
        .then((a) => {
          setAlerts(a);
          setError(null);
        })
        .catch((e) => setError(e.message));
    }, []),
  );

  return (
    <Screen title="Disaster alerts" sub="Checked by the RAAZICID team before they show here.">
      <ErrorBox message={error} />
      {alerts === null && !error ? <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} /> : null}
      {alerts && alerts.length === 0 ? (
        <Card>
          <Text style={{ color: colors.ink, fontWeight: "700" }}>No active disasters right now.</Text>
          <Text style={{ color: colors.muted, marginTop: 4 }}>You can still see what each area needs.</Text>
        </Card>
      ) : null}
      {alerts?.map((a) => <AlertCard key={a.id} a={a} navigation={navigation} />)}
      <Button label="What is needed where" variant="outline" onPress={() => navigation.navigate("Needs")} />
    </Screen>
  );
}

function AlertCard({ a, navigation }: { a: DisasterAlert; navigation: any }) {
  const sev = SEVERITY[a.severity];
  const figures = Object.entries(a.figures).filter(([, v]) => v > 0);
  const place = a.places[0]?.name ?? "Pakistan";
  return (
    <Card>
      <View style={{ gap: 8 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={{ fontSize: 11, fontWeight: "800", color: sev.fg, backgroundColor: sev.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" }}>
            {sev.label}
          </Text>
          <Text style={{ color: colors.muted, fontSize: 12 }}>{shortDate(a.started_at ?? a.created_at)}</Text>
        </View>
        <Text style={{ fontSize: 17, fontWeight: "800", color: colors.ink }}>{a.title}</Text>
        {a.places.length ? <Text style={{ color: colors.ink2 }}>{a.places.map((p) => p.path.slice(-2).join(", ")).join(" · ")}</Text> : null}
        {a.summary ? <Text style={{ color: colors.ink2 }}>{a.summary}</Text> : null}
        {figures.length ? (
          <Text style={{ color: colors.ink, fontWeight: "700" }}>{figures.map(([k, v]) => `${v.toLocaleString()} ${FIGURE_LABELS[k] ?? k}`).join(" · ")}</Text>
        ) : null}

        {a.needs.length ? (
          <View style={{ gap: 6, marginTop: 4 }}>
            <Text style={{ fontWeight: "800", color: colors.ink }}>What is needed</Text>
            {a.needs.map((n) => (
              <Pressable key={n.category_id} accessibilityRole="button" accessibilityLabel={`Donate ${n.name}`}
                onPress={() => navigation.navigate("Donate", { categoryId: n.category_id, forText: `${n.name} for ${place}` })}
                style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 10, backgroundColor: colors.bg }}>
                <Text style={{ flex: 1, color: colors.ink, fontWeight: "600" }}>{n.name}</Text>
                {n.quantity_needed ? <Text style={{ color: colors.muted, fontSize: 12 }}>{n.quantity_needed.toLocaleString()} needed</Text> : null}
                <Text style={{ color: colors.primary, fontWeight: "800" }}>Donate ›</Text>
              </Pressable>
            ))}
          </View>
        ) : null}

        {a.camps.filter((c) => c.is_active).length ? (
          <Text style={{ color: colors.primaryDark, fontWeight: "600" }}>
            Relief camp{a.camps.length > 1 ? "s" : ""}: {a.camps.filter((c) => c.is_active).map((c) => c.name).join(", ")}
          </Text>
        ) : null}

        {a.sources.length ? (
          <View style={{ gap: 2 }}>
            <Text style={{ color: colors.muted, fontSize: 12 }}>Sources</Text>
            {a.sources.slice(0, 3).map((s, i) =>
              s.url ? (
                <Pressable key={i} accessibilityRole="link" onPress={() => Linking.openURL(s.url!)}>
                  <Text style={{ color: colors.primary, fontSize: 13 }} numberOfLines={1}>{s.publisher ? `${s.publisher}: ` : ""}{s.title}</Text>
                </Pressable>
              ) : (
                <Text key={i} style={{ color: colors.ink2, fontSize: 13 }}>{s.title}</Text>
              ),
            )}
          </View>
        ) : null}
      </View>
    </Card>
  );
}
