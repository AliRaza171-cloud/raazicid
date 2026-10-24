import { useNavigation, useRoute } from "@react-navigation/native";
import { useState } from "react";
import { Image, Pressable, Text } from "react-native";
import { api } from "../../api";
import { Button, ErrorBox, Field, Screen } from "../../components/ui";
import { colors } from "../../theme";
import { pickPhoto, uploadPhoto, type PickedPhoto } from "../../upload";

type Params = { donationId: string; quantity: number; title: string; pointName?: string };

/** The last step: our team handed the items to families at the point. Can be done now or later from Jobs. */
export default function HandOutScreen() {
  const navigation = useNavigation<any>();
  const { params } = useRoute<any>() as { params: Params };
  const [qty, setQty] = useState(String(params.quantity));
  const [families, setFamilies] = useState("");
  const [photo, setPhoto] = useState<PickedPhoto | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shoot = async () => {
    setError(null);
    try {
      const p = await pickPhoto("camera");
      if (p) setPhoto(p);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const save = async () => {
    const q = parseInt(qty, 10);
    const f = families.trim() ? parseInt(families, 10) : null;
    if (!q || q < 1 || q > params.quantity) return setError(`Enter how many were handed out (1–${params.quantity})`);
    if (f !== null && (isNaN(f) || f < 0)) return setError("Families served must be a number");
    setBusy(true);
    setError(null);
    try {
      const url = photo ? await uploadPhoto(photo, "proof_photo") : null;
      await api(`/donations/${params.donationId}/hand-out`, {
        method: "POST",
        body: JSON.stringify({ quantity: q, families_served: f, photo_url: url, note: note.trim() || null }),
      });
      navigation.navigate("RiderTabs", { screen: "Jobs" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title="Record the hand-out" sub={`${params.title}${params.pointName ? ` · ${params.pointName}` : ""}`} edges={["bottom"]}>
      <Text style={{ color: colors.ink2 }}>
        Fill this in when the items are given to families. If that happens later, tap "Do it later" — the job stays on your Jobs list.
      </Text>
      <Field label={`How many were handed out? (of ${params.quantity})`} value={qty} onChangeText={(t: string) => setQty(t.replace(/\D/g, ""))} keyboardType="number-pad" />
      <Field label="How many families received them?" value={families} onChangeText={(t: string) => setFamilies(t.replace(/\D/g, ""))} keyboardType="number-pad" placeholder="e.g. 8" />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={photo ? "Retake hand-out photo" : "Take hand-out photo"}
        onPress={shoot}
        style={{ height: 160, borderRadius: 14, borderWidth: 2, borderStyle: "dashed", borderColor: colors.line2, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" }}
      >
        {photo ? (
          <Image source={{ uri: photo.uri }} style={{ width: "100%", height: "100%", borderRadius: 12 }} />
        ) : (
          <Text style={{ color: colors.primary, fontWeight: "700" }}>Add a photo (optional)</Text>
        )}
      </Pressable>
      <Text style={{ fontSize: 12, color: colors.muted, marginTop: -6 }}>For dignity, take the photo without showing faces clearly.</Text>
      <Field label="Note (optional)" value={note} onChangeText={setNote} placeholder="e.g. Given after Jumma prayers" maxLength={300} />
      <ErrorBox message={error} />
      <Button label="Save hand-out" onPress={save} loading={busy} />
      <Button label="Do it later" variant="outline" onPress={() => navigation.navigate("RiderTabs", { screen: "Jobs" })} />
    </Screen>
  );
}
