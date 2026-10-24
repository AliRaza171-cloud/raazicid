import { useNavigation } from "@react-navigation/native";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "../../auth";
import { Button, ErrorBox, Field } from "../../components/ui";
import { colors, space } from "../../theme";

export default function LoginScreen() {
  const { login } = useAuth();
  const navigation = useNavigation<any>();
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!id.trim() || !password) return setError("Enter your phone or email and your password");
    setBusy(true);
    setError(null);
    try {
      await login(id.trim(), password);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView keyboardShouldPersistTaps="handled">
          <View style={s.hero}>
            <Text style={s.brand}>RAAZICID</Text>
            <Text style={s.tag}>Your extra things, delivered to the people who need them most.</Text>
          </View>
          <View style={s.form}>
            <Text style={s.h2}>Log in</Text>
            <Field label="Phone or email" value={id} onChangeText={setId} placeholder="0300 1234567" autoCapitalize="none" keyboardType="email-address" autoComplete="username" />
            <Field label="Password" value={password} onChangeText={setPassword} placeholder="Your password" secureTextEntry autoComplete="password" onSubmitEditing={submit} />
            <ErrorBox message={error} />
            <Button label="Log in" onPress={submit} loading={busy} />
            <Button label="Create an account" variant="outline" onPress={() => navigation.navigate("Signup")} />
            <Text style={s.note}>Donors and riders use this app. Admins sign in on the RAAZICID web app.</Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  hero: { backgroundColor: colors.primary, padding: space(7), paddingTop: space(12), gap: space(2) },
  brand: { color: "#fff", fontSize: 30, fontWeight: "800" },
  tag: { color: "#D5E8E3", fontSize: 15, lineHeight: 22 },
  form: { padding: space(6), gap: space(4) },
  h2: { fontSize: 22, fontWeight: "700", color: colors.ink },
  note: { fontSize: 12, color: colors.muted, textAlign: "center", lineHeight: 18 },
});
