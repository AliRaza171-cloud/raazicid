import { useNavigation } from "@react-navigation/native";
import { StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "../../auth";
import { Button } from "../../components/ui";
import { colors, radius, space } from "../../theme";

export default function LoginScreen() {
  const { signInDemo } = useAuth();
  const navigation = useNavigation<any>();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={s.hero}>
        <Text style={s.brand}>RAAZICID</Text>
        <Text style={s.tag}>Your extra things, delivered to the people who need them most.</Text>
      </View>
      <View style={s.form}>
        <Text style={s.h2}>Log in</Text>
        <TextInput style={s.input} placeholder="Phone or email" autoCapitalize="none" />
        <TextInput style={s.input} placeholder="Password" secureTextEntry />
        {/* Phase 2: real login. For now, demo buttons open each app. */}
        <Button label="Continue as donor (demo)" onPress={() => signInDemo("donor")} />
        <Button label="Continue as rider (demo)" variant="outline" onPress={() => signInDemo("rider")} />
        <Button label="New rider, not approved (demo)" variant="outline" onPress={() => signInDemo("rider", false)} />
        <Text style={s.link} onPress={() => navigation.navigate("Signup")}>Create an account</Text>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  hero: { backgroundColor: colors.primary, padding: space(7), paddingTop: space(12), gap: space(2) },
  brand: { color: "#fff", fontSize: 30, fontWeight: "800" },
  tag: { color: "#D5E8E3", fontSize: 15, lineHeight: 22 },
  form: { padding: space(6), gap: space(3) },
  h2: { fontSize: 22, fontWeight: "700", color: colors.ink },
  input: { height: 48, borderWidth: 1, borderColor: colors.line2, borderRadius: radius.sm + 2, paddingHorizontal: 14, backgroundColor: "#fff", fontSize: 15 },
  link: { color: colors.primary, fontWeight: "700", textAlign: "center", paddingVertical: space(3) },
});
