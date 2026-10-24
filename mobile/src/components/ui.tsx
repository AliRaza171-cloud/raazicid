import type { ReactNode } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, radius, space } from "../theme";

export function Screen({ title, sub, children, edges = ["top"] }: { title?: string; sub?: string; children?: ReactNode; edges?: ("top" | "bottom")[] }) {
  return (
    <SafeAreaView style={s.safe} edges={edges}>
      <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
        {title ? <Text style={s.title}>{title}</Text> : null}
        {sub ? <Text style={s.sub}>{sub}</Text> : null}
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

export function Button({
  label,
  onPress,
  variant = "primary",
  loading = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  variant?: "primary" | "outline" | "danger";
  loading?: boolean;
  disabled?: boolean;
}) {
  const outline = variant !== "primary";
  const tint = variant === "danger" ? colors.urgent : colors.primary;
  const off = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off, busy: loading }}
      disabled={off}
      onPress={onPress}
      style={({ pressed }) => [
        s.btn,
        outline ? { backgroundColor: "#fff", borderWidth: 1.5, borderColor: tint } : { backgroundColor: colors.primary },
        (pressed || off) && { opacity: 0.7 },
      ]}
    >
      {loading ? <ActivityIndicator color={outline ? tint : "#fff"} /> : <Text style={[s.btnText, outline && { color: tint }]}>{label}</Text>}
    </Pressable>
  );
}

export function Field({ label, error, hint, style, ...input }: TextInputProps & { label: string; error?: string | null; hint?: string }) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput accessibilityLabel={label} placeholderTextColor="#8A928E" style={[s.input, error ? { borderColor: colors.urgent } : null, style]} {...input} />
      {error ? <Text style={s.error}>{error}</Text> : hint ? <Text style={s.hint}>{hint}</Text> : null}
    </View>
  );
}

export function Chips<T extends string>({ options, value, onChange }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(o.value)}
            style={[s.chip, on && { backgroundColor: colors.primarySoft, borderColor: colors.primary, borderWidth: 2 }]}
          >
            <Text style={[s.chipText, on && { color: colors.primaryDark }]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <View style={s.errorBox} accessibilityLiveRegion="polite">
      <Text style={{ color: colors.urgent, fontWeight: "600" }}>{message}</Text>
    </View>
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
  body: { padding: space(5), gap: space(4), paddingBottom: space(10) },
  title: { fontSize: 22, fontWeight: "800", color: colors.ink },
  sub: { fontSize: 14, color: colors.muted, marginTop: -space(2) },
  btn: { height: 52, borderRadius: radius.md, alignItems: "center", justifyContent: "center", paddingHorizontal: space(4) },
  btnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  label: { fontSize: 13, fontWeight: "600", color: colors.ink2 },
  input: { height: 48, borderWidth: 1, borderColor: colors.line2, borderRadius: 12, paddingHorizontal: 14, backgroundColor: "#fff", fontSize: 15, color: colors.ink },
  error: { fontSize: 12, color: colors.urgent },
  hint: { fontSize: 12, color: colors.muted },
  chip: { minHeight: 44, paddingHorizontal: 14, justifyContent: "center", borderRadius: 12, borderWidth: 1, borderColor: colors.line2, backgroundColor: "#fff" },
  chipText: { fontSize: 14, fontWeight: "600", color: colors.ink },
  errorBox: { padding: space(3), borderRadius: 12, backgroundColor: colors.urgentSoft },
  card: { backgroundColor: colors.card, borderRadius: radius.md, borderWidth: 1, borderColor: colors.line, padding: space(4), gap: space(2) },
  todo: { borderWidth: 2, borderStyle: "dashed", borderColor: colors.line2, borderRadius: radius.md, padding: space(5), backgroundColor: "#FAFBF9" },
  todoText: { color: colors.muted, fontSize: 14, lineHeight: 20 },
});
