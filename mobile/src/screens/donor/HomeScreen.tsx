import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { useCallback, useState } from "react";
import { Image, Pressable, Text, View } from "react-native";
import { api, type DonationListItem } from "../../api";
import { useAuth } from "../../auth";
import { Button, Card, ComingIn, ErrorBox, Screen } from "../../components/ui";
import { STATUS, shortDate } from "../../status";
import { colors } from "../../theme";

export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const { user } = useAuth();
  const [active, setActive] = useState<DonationListItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useFocusEffect(
    useCallback(() => {
      api<{ items: DonationListItem[] }>("/donations/mine?filter=active&limit=3")
        .then((d) => {
          setActive(d.items);
          setError(null);
        })
        .catch((e) => setError(e.message));
    }, []),
  );

  const firstName = user?.full_name.split(" ")[0] ?? "there";

  return (
    <Screen title={`Hi, ${firstName}`} sub={user?.location_path.slice(-2).join(", ") || undefined}>
      <View style={{ backgroundColor: colors.primary, borderRadius: 18, padding: 18, gap: 10 }}>
        <Text style={{ color: "#fff", fontSize: 18, fontWeight: "800" }}>Have something to give?</Text>
        <Text style={{ color: "#D5ECE5" }}>Take a photo, choose a pickup time, and our rider collects it.</Text>
        <Pressable
          accessibilityRole="button"
          onPress={() => navigation.navigate("Donate")}
          style={{ backgroundColor: "#fff", borderRadius: 12, height: 48, alignItems: "center", justifyContent: "center" }}
        >
          <Text style={{ color: colors.primary, fontWeight: "800", fontSize: 16 }}>Donate now</Text>
        </Pressable>
      </View>

      <ErrorBox message={error} />

      {active.length ? (
        <View style={{ gap: 8 }}>
          <Text style={{ fontSize: 16, fontWeight: "800", color: colors.ink }}>Your active donations</Text>
          {active.map((d) => {
            const s = STATUS[d.status];
            return (
              <Pressable key={d.id} accessibilityRole="button" onPress={() => navigation.navigate("DonationDetail", { id: d.id })}>
                <Card>
                  <View style={{ flexDirection: "row", gap: 12, alignItems: "center" }}>
                    {d.photo_url ? <Image source={{ uri: d.photo_url }} style={{ width: 48, height: 48, borderRadius: 10 }} /> : null}
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontWeight: "700", color: colors.ink }} numberOfLines={1}>{d.title}</Text>
                      <Text style={{ fontSize: 12, color: colors.muted }}>{d.category.name} · {shortDate(d.created_at)}</Text>
                    </View>
                    <Text style={{ fontSize: 11, fontWeight: "800", color: s.fg, backgroundColor: s.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: "hidden" }}>
                      {s.label}
                    </Text>
                  </View>
                </Card>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      <Button label="What is needed where" variant="outline" onPress={() => navigation.navigate("Needs")} />
      <ComingIn phase={7} what="'Most needed now' seasonal card and emergency appeals." />
    </Screen>
  );
}
