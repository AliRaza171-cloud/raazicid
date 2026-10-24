import { useNavigation } from "@react-navigation/native";
import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { api, API_URL, type Category } from "../../api";
import { Button, Card, ComingIn, Screen } from "../../components/ui";
import { colors } from "../../theme";

/** Phase 1: proves the phone can reach the backend. Phase 3+ adds the real home screen. */
export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const [status, setStatus] = useState<"checking" | "ok" | "down">("checking");
  const [cats, setCats] = useState<Category[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ status: string }>("/health")
      .then(() => setStatus("ok"))
      .catch((e: Error) => {
        setStatus("down");
        setError(e.message);
      });
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  return (
    <Screen title="Hi there" sub="Phase 1 setup check">
      <Card>
        <Text style={{ fontWeight: "700", color: colors.ink }}>
          Backend: {status === "checking" ? "checking…" : status === "ok" ? "connected" : "not reachable"}
        </Text>
        <Text style={{ fontSize: 12, color: colors.muted }}>{API_URL}</Text>
        {error ? <Text style={{ fontSize: 12, color: colors.urgent }}>{error}</Text> : null}
        <Text style={{ color: colors.ink2 }}>{cats.length} of 12 categories loaded from the database</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
          {cats.map((c) => (
            <Text key={c.id} style={{ backgroundColor: colors.primarySoft, color: colors.primaryDark, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, fontSize: 12, fontWeight: "700" }}>
              {c.name}
            </Text>
          ))}
        </View>
      </Card>
      <Button label="What is needed where" variant="outline" onPress={() => navigation.navigate("Needs")} />
      <ComingIn phase={3} what="Greeting, 'Most needed now' seasonal card, emergency appeal, active donation and recent list." />
    </Screen>
  );
}
