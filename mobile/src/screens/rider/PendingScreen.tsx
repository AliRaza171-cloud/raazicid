import { useCallback, useEffect, useState } from "react";
import { Alert, Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, type DocType, type RiderDoc } from "../../api";
import { useAuth } from "../../auth";
import { Button, ErrorBox } from "../../components/ui";
import { colors, space } from "../../theme";
import { pickPhoto, uploadPhoto } from "../../upload";

const DOCS: { type: DocType; label: string }[] = [
  { type: "cnic_front", label: "CNIC front" },
  { type: "cnic_back", label: "CNIC back" },
  { type: "driving_licence", label: "Driving licence" },
  { type: "vehicle_registration", label: "Vehicle registration" },
];

/** Shown to riders until an admin approves them: upload documents, see the admin's note. */
export default function PendingScreen() {
  const { user, reloadUser, logout } = useAuth();
  const [docs, setDocs] = useState<RiderDoc[]>([]);
  const [busyType, setBusyType] = useState<DocType | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDocs(await api<RiderDoc[]>("/me/rider-documents"));
      await reloadUser();
    } catch (e) {
      setError((e as Error).message);
    }
  }, [reloadUser]);

  useEffect(() => {
    load();
  }, [load]);

  const upload = (type: DocType) => {
    Alert.alert("Add photo", "Take a clear photo of the whole document.", [
      { text: "Camera", onPress: () => doUpload(type, "camera") },
      { text: "Gallery", onPress: () => doUpload(type, "gallery") },
      { text: "Cancel", style: "cancel" },
    ]);
  };

  const doUpload = async (type: DocType, source: "camera" | "gallery") => {
    setError(null);
    try {
      const uri = await pickPhoto(source);
      if (!uri) return;
      setBusyType(type);
      const url = await uploadPhoto(uri, "rider_document");
      await api("/me/rider-documents", { method: "POST", body: JSON.stringify({ doc_type: type, file_url: url }) });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyType(null);
    }
  };

  const byType = (t: DocType) => docs.find((d) => d.doc_type === t);
  const done = DOCS.every((d) => byType(d.type));
  const status = user?.rider_status;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: space(6), gap: space(5) }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      >
        <Text style={s.h1}>
          {status === "rejected" ? "Your application was not approved" : status === "suspended" ? "Your account is suspended" : done ? "We are checking your documents" : "Upload your documents"}
        </Text>
        <Text style={s.p}>
          {status === "suspended"
            ? "Contact RAAZICID to find out more."
            : done
              ? "An admin reviews every rider before they can take jobs. Pull down to check for updates."
              : "Take clear photos of these 4 documents. An admin will check them, usually within 1–2 days."}
        </Text>

        {user?.rider_note ? (
          <View style={s.note}>
            <Text style={{ fontWeight: "800", color: colors.warn }}>Message from admin</Text>
            <Text style={{ color: colors.ink, marginTop: 4 }}>{user.rider_note}</Text>
          </View>
        ) : null}

        <View style={s.card}>
          {DOCS.map((d, i) => {
            const doc = byType(d.type);
            return (
              <Pressable
                key={d.type}
                accessibilityRole="button"
                accessibilityLabel={`${doc ? "Replace" : "Upload"} ${d.label}`}
                disabled={status === "suspended" || busyType !== null}
                onPress={() => upload(d.type)}
                style={[s.row, i < DOCS.length - 1 && { borderBottomWidth: 1, borderColor: colors.line }]}
              >
                {doc ? <Image source={{ uri: doc.file_url }} style={s.thumb} /> : <View style={[s.thumb, { backgroundColor: colors.line }]} />}
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 15, fontWeight: "700", color: colors.ink }}>{d.label}</Text>
                  <Text style={{ fontSize: 12, color: doc ? colors.primary : colors.muted }}>
                    {busyType === d.type ? "Uploading…" : doc ? "Uploaded · tap to replace" : "Tap to upload"}
                  </Text>
                </View>
              </Pressable>
            );
          })}
        </View>

        <ErrorBox message={error} />
        <Button label="Check my status" variant="outline" onPress={load} />
        <Button label="Log out" variant="danger" onPress={logout} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  h1: { fontSize: 24, fontWeight: "800", color: colors.ink, marginTop: space(6) },
  p: { fontSize: 15, lineHeight: 22, color: colors.ink2 },
  note: { padding: 14, borderRadius: 14, backgroundColor: colors.warnSoft },
  card: { backgroundColor: "#fff", borderRadius: 16, borderWidth: 1, borderColor: colors.line, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, minHeight: 72 },
  thumb: { width: 52, height: 40, borderRadius: 8 },
});
