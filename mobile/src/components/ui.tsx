import type { ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, radius, space } from "../theme";

export function Screen({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <SafeAreaView style={s.safe} edges={["top"]}>
      <ScrollView contentContainerStyle={s.body}>
        <Text style={s.title}>{title}</Text>
        {sub ? <Text style={s.sub}>{sub}</Text> : null}
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function Button({ label, onPress, variant = "primary" }: { label: string; onPress: () => void; variant?: "primary" | "outline" }) {
  const outline = variant === "outline";
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [s.btn, outline ? s.btnOutline : s.btnPrimary, pressed && { opacity: 0.85 }]}
    >
      <Text style={[s.btnText, outline && { color: colors.primary }]}>{label}</Text>
    </Pressable>
  );
}

export function Card({ children }: { children: ReactNode }) {
  return <View style={s.card}>{children}</View>;
}

/** Placeholder for screens built in later phases. */
export function ComingIn({ phase, what }: { phase: number; what: string }) {
  return (
    <View style={s.todo}>
      <Text style={s.todoText}>
        <Text style={{ fontWeight: "700", color: colors.ink }}>Built in Phase {phase}. </Text>
        {what} The finished look is on the design canvas.
      </Text>
    </View>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  body: { padding: space(5), gap: space(4) },
  title: { fontSize: 22, fontWeight: "800", color: colors.ink },
  sub: { fontSize: 14, color: colors.muted, marginTop: -space(2) },
  btn: { height: 52, borderRadius: radius.md, alignItems: "center", justifyContent: "center", paddingHorizontal: space(4) },
  btnPrimary: { backgroundColor: colors.primary },
  btnOutline: { backgroundColor: "#fff", borderWidth: 1.5, borderColor: colors.primary },
  btnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  card: { backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.line, padding: space(4), gap: space(2) },
  todo: { borderWidth: 2, borderStyle: "dashed", borderColor: colors.line2, borderRadius: radius.md, padding: space(5), backgroundColor: "#FAFBF9" },
  todoText: { color: colors.muted, fontSize: 14, lineHeight: 20 },
});
