import { useCallback, useState } from "react";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import { useAuth } from "../../auth";
import { Card, ComingIn, Screen } from "../../components/ui";
import { colors, space } from "../../theme";

/** What an approved rider sees until pickup jobs arrive in Phase 4. */
export default function ApprovedScreen() {
  const { user, reloadUser } = useAuth();
  const [refreshing, setRefreshing] = useState(false);

  useFocusEffect(
    useCallback(() => {
      reloadUser().catch(() => undefined);
    }, [reloadUser]),
  );

  const refresh = async () => {
    setRefreshing(true);
    await reloadUser().catch(() => undefined);
    setRefreshing(false);
  };

  return (
    <Screen title={`Salaam, ${user?.full_name.split(" ")[0] ?? "rider"}`} sub="Your rider account">
      <ScrollView contentContainerStyle={{ gap: space(3), paddingBottom: space(6) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}>
        <View style={{ padding: space(4), borderRadius: 14, backgroundColor: colors.primarySoft, gap: 4 }}>
          <Text style={{ fontWeight: "800", fontSize: 16, color: colors.primaryDark }}>You are approved</Text>
          <Text style={{ color: colors.ink2 }}>
            An admin checked your CNIC, driving licence and vehicle papers. You will get pickup jobs here once they start.
          </Text>
        </View>
        <Card>
          <Text style={{ fontWeight: "700", color: colors.ink }}>Your details</Text>
          <Text style={{ color: colors.ink2 }}>Phone: {user?.phone}</Text>
          {user?.email ? <Text style={{ color: colors.ink2 }}>Email: {user.email}</Text> : null}
        </Card>
        <ComingIn phase={4} what="Pickup jobs, proof photos at pickup and at the NGO, and live tracking." />
      </ScrollView>
    </Screen>
  );
}
