import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, Text, View } from "react-native";
import { api, type Appeal, type AppNotification, type DisasterAlert } from "../../api";
import { Button, Card, Chips, ErrorBox, Screen } from "../../components/ui";
import { FIGURE_LABELS, SEVERITY, shortDate } from "../../status";
import { colors } from "../../theme";

type Tab = "help" | "updates";

/** Appeals for my province and confirmed disasters, plus my own updates (donation status, appeals sent to me). */
export default function AlertsScreen() {
  const navigation = useNavigation<any>();
  const [tab, setTab] = useState<Tab>("help");
  const [alerts, setAlerts] = useState<DisasterAlert[] | null>(null);
  const [appeals, setAppeals] = useState<Appeal[]>([]);
  const [notes, setNotes] = useState<{ unread: number; items: AppNotification[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      Promise.all([
        api<DisasterAlert[]>("/alerts"),
        api<Appeal[]>("/appeals/active"),
        api<{ unread: number; items: AppNotification[] }>("/me/notifications"),
      ])
        .then(([a, ap, n]) => {
          setAlerts(a);
          setAppeals(ap);
          setNotes(n);
          setError(null);
        })
        .catch((e) => setError(e.message));
    }, []),
  );

  const openUpdates = (v: Tab) => {
    setTab(v);
    if (v === "updates" && notes?.unread) {
      api("/me/notifications/read", { method: "POST" }).catch(() => undefined);
      setNotes({ ...notes, unread: 0 });
    }
  };

  const donate = (categoryId: number, forText: string) => navigation.navigate("Donate", { categoryId, forText });

  return (
    <Screen title="Alerts" sub="Appeals and disasters checked by the RAAZICID team, and updates on your donations.">
      <Chips<Tab>
        options={[{ value: "help", label: "Where help is needed" }, { value: "updates", label: notes?.unread ? `My updates (${notes.unread})` : "My updates" }]}
        value={tab}
        onChange={openUpdates}
      />
      <ErrorBox message={error} />
      {alerts === null && !error ? <ActivityIndicator color={colors.primary} style={{ marginTop: 24 }} /> : null}

      {tab === "help" && alerts ? (
        <>
          {appeals.map((ap) => <AppealCard key={ap.id} ap={ap} onDonate={donate} />)}
          {alerts.map((a) => <AlertCard key={a.id} a={a} onDonate={donate} />)}
          {appeals.length === 0 && alerts.length === 0 ? (
            <Card>
              <Text style={{ color: colors.ink, fontWeight: "700" }}>No appeals or disasters right now.</Text>
              <Text style={{ color: colors.muted, marginTop: 4 }}>You can still see what each area needs.</Text>
            </Card>
          ) : null}
          <Button label="What is needed where" variant="outline" onPress={() => navigation.navigate("Needs")} />
        </>
      ) : null}

      {tab === "updates" && notes ? (
        notes.items.length === 0 ? (
          <Card><Text style={{ color: colors.muted }}>No updates yet. They appear here when your donations move along.</Text></Card>
        ) : (
          notes.items.map((n) => (
            <Pressable key={n.id} accessibilityRole={n.data.donation_id ? "button" : undefined} disabled={!n.data.donation_id}
              onPress={() => navigation.navigate("DonationDetail", { id: n.data.donation_id })}>
              <Card>
                <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                  {!n.read ? <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary }} /> : null}
                  <Text style={{ flex: 1, fontWeight: "800", color: colors.ink }}>{n.title}</Text>
                  <Text style={{ color: colors.muted, fontSize: 12 }}>{shortDate(n.created_at)}</Text>
                </View>
                <Text style={{ color: colors.ink2, marginTop: 4 }}>{n.body}</Text>
              </Card>
            </Pressable>
          ))
        )
      ) : null}
    </Screen>
  );
}

function AppealCard({ ap, onDonate }: { ap: Appeal; onDonate: (categoryId: number, forText: string) => void }) {
  const place = ap.place.slice(-1)[0] ?? "Pakistan";
  return (
    <View style={{ backgroundColor: colors.primary, borderRadius: 16, padding: 16, gap: 8 }}>
      <Text style={{ color: "#D5ECE5", fontSize: 12, fontWeight: "800" }}>APPEAL · {ap.place.slice(-2).join(", ").toUpperCase()}</Text>
      <Text style={{ color: "#fff", fontSize: 17, fontWeight: "800" }}>{ap.title}</Text>
      <Text style={{ color: "#E8F4F0" }}>{ap.message}</Text>
      {ap.categories.length ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {ap.categories.map((c) => (
            <Pressable key={c.id} accessibilityRole="button" accessibilityLabel={`Donate ${c.name}`} onPress={() => onDonate(c.id, `${c.name} for ${place}`)}
              style={{ backgroundColor: "#fff", borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 }}>
              <Text style={{ color: colors.primary, fontWeight: "800" }}>Donate {c.name.toLowerCase()} ›</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      {ap.ends_at ? <Text style={{ color: "#BFE0D6", fontSize: 12 }}>Until {shortDate(ap.ends_at)}</Text> : null}
    </View>
  );
}

function AlertCard({ a, onDonate }: { a: DisasterAlert; onDonate: (categoryId: number, forText: string) => void }) {
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
                onPress={() => onDonate(n.category_id, `${n.name} for ${place}`)}
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
