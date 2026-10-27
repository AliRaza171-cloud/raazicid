import { useNavigation, useRoute } from "@react-navigation/native";
import * as Location from "expo-location";
import { useState } from "react";
import { Image, Pressable, StyleSheet, Switch, Text, View } from "react-native";
import { api } from "../../api";
import { Button, ErrorBox, Field, Screen } from "../../components/ui";
import { distanceKm } from "../../status";
import { colors } from "../../theme";
import { pickPhoto, uploadPhoto, type PickedPhoto } from "../../upload";

type Params = {
  jobId: string;
  kind: "pickup" | "deliver";
  title: string;
  quantity: number;
  placeName: string;
  target: { lat: number; lng: number };
  donationId?: string;
};

const FAR_KM = 1;

/** Camera photo + GPS as proof of pickup (at the donor) or delivery (handed to the NGO: the last step). */
export default function ProofScreen() {
  const navigation = useNavigation<any>();
  const { params } = useRoute<any>() as { params: Params };
  const pickup = params.kind === "pickup";
  const [photo, setPhoto] = useState<PickedPhoto | null>(null);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [takenAt, setTakenAt] = useState<Date | null>(null);
  const [allItems, setAllItems] = useState(false);
  const [received, setReceived] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const shoot = async () => {
    setError(null);
    try {
      const p = await pickPhoto("camera");   // camera only: proof must be taken on the spot
      if (!p) return;
      setPhoto(p);
      setTakenAt(new Date());
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) throw new Error("Location permission is needed for proof");
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const far = coords ? distanceKm(coords, params.target) : null;
  const ready = photo && coords && allItems && (pickup || received);

  const confirm = async () => {
    if (!photo || !coords) return;
    setBusy(true);
    setError(null);
    try {
      const url = await uploadPhoto(photo, "proof_photo");
      await api(`/rider/jobs/${params.jobId}/${pickup ? "pickup" : "deliver"}`, {
        method: "POST",
        body: JSON.stringify({ photo_url: url, lat: coords.lat, lng: coords.lng, note: note.trim() || null }),
      });
      if (pickup) {
        navigation.goBack();
      } else {
        setDone(true);   // delivered: the job is finished
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <Screen title="Delivered" sub={`${params.title} · ${params.placeName}`} edges={["bottom"]}>
        <View style={{ backgroundColor: colors.primarySoft, borderRadius: 14, padding: 14, gap: 6 }}>
          <Text style={{ fontWeight: "800", color: colors.primaryDark, fontSize: 16 }}>Thank you! The job is done.</Text>
          <Text style={{ color: colors.ink2 }}>{params.placeName} will give the items to people in need. The donor has been told.</Text>
        </View>
        <Button label="Back to my jobs" onPress={() => navigation.navigate("RiderTabs", { screen: "Jobs" })} />
      </Screen>
    );
  }

  return (
    <Screen title={pickup ? "Confirm pickup" : "Confirm delivery"} sub={`${params.title} · at ${params.placeName}`} edges={["bottom"]}>
      <Pressable accessibilityRole="button" accessibilityLabel={photo ? "Retake photo" : "Take photo"} onPress={shoot} style={st.shot}>
        {photo ? (
          <Image source={{ uri: photo.uri }} style={{ width: "100%", height: "100%", borderRadius: 14 }} />
        ) : (
          <Text style={{ color: colors.primary, fontWeight: "800", fontSize: 16 }}>Take photo</Text>
        )}
      </Pressable>
      <Text style={st.hint}>
        {photo
          ? `Photo taken ${takenAt?.toLocaleTimeString("en-PK", { hour: "numeric", minute: "2-digit" })}${coords ? " · location saved" : " · getting location…"} · tap to retake`
          : pickup
            ? "Show all the items with the donor's place in the background."
            : "Show the items with the NGO's office or sign in the background."}
      </Text>

      {far !== null && far > FAR_KM ? (
        <View style={st.warn}>
          <Text style={{ fontWeight: "800", color: colors.warn }}>You seem to be {far.toFixed(1)} km away</Text>
          <Text style={{ color: colors.ink2 }}>
            Take the photo at {params.placeName}. You can still continue, but RAAZICID will check it.
          </Text>
        </View>
      ) : null}

      <Check value={allItems} onChange={setAllItems} label={`All ${params.quantity} item${params.quantity === 1 ? "" : "s"} ${pickup ? "collected" : "handed over"}`} />
      {!pickup ? <Check value={received} onChange={setReceived} label="Someone at the NGO received them" /> : null}
      <Field label="Note (optional)" value={note} onChangeText={setNote} placeholder={pickup ? "e.g. 2 bags, 1 box" : "Received by (name at the NGO)…"} maxLength={300} />

      <ErrorBox message={error} />
      <Button label={pickup ? "Confirm pickup" : "Confirm delivery"} onPress={confirm} loading={busy} disabled={!ready} />
    </Screen>
  );
}

function Check({ value, onChange, label }: { value: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 12, backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: colors.line }}>
      <Text style={{ flex: 1, fontWeight: "600", color: colors.ink }}>{label}</Text>
      <Switch accessibilityLabel={label} value={value} onValueChange={onChange} trackColor={{ true: colors.primary }} />
    </View>
  );
}

const st = StyleSheet.create({
  shot: { height: 220, borderRadius: 14, borderWidth: 2, borderStyle: "dashed", borderColor: colors.primary, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  hint: { fontSize: 12, color: colors.muted, marginTop: -6 },
  warn: { padding: 12, borderRadius: 14, backgroundColor: colors.warnSoft, gap: 4 },
});
