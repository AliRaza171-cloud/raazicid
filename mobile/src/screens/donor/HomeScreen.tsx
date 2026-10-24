import { useNavigation } from "@react-navigation/native";
import { useEffect, useState } from "react";
import { Text, View } from "react-native";
import { api, API_URL, type Category } from "../../api";
import { useAuth } from "../../auth";
import { Button, Card, ComingIn, Screen } from "../../components/ui";
import { colors } from "../../theme";

export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const { user } = useAuth();
  const [status, setStatus] = useState<"checking" | "ok" | "down">("checking");
  const [cats, setCats] = useState<Category[]>([]);

  useEffect(() => {
    api<{ status: string }>("/health")
      .then(() => setStatus("ok"))
      .catch(() => setStatus("down"));
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const firstName = user?.full_name.split(" ")[0] ?? "there";

  return (
    <Screen title={`Hi, ${firstName}`} sub={user?.location_path.slice(-2).join(", ") || undefined}>
      <Card>
        <Text style={{ fontWeight: "700", color: colors.ink }}>
          Backend: {status === "checking" ? "checking…" : status === "ok" ? "connected" : "not reachable"}
        </Text>
        <Text style={{ fontSize: 12, color: colors.muted }}>{API_URL}</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
          {cats.map((c) => (
            <Text key={c.id} style={{ backgroundColor: colors.primarySoft, color: colors.primaryDark, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, fontSize: 12, fontWeight: "700" }}>
              {c.name}
            </Text>
          ))}
        </View>
      </Card>
      <Button label="What is needed where" variant="outline" onPress={() => navigation.navigate("Needs")} />
      <ComingIn phase={3} what="'Most needed now' seasonal card, emergency appeal, active donation and recent list." />
    </Screen>
  );
}
