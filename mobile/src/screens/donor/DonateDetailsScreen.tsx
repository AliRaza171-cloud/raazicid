import { CommonActions, useNavigation, useRoute } from "@react-navigation/native";
import * as Location from "expo-location";
import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { api, type Donation } from "../../api";
import { useAuth } from "../../auth";
import LocationPicker from "../../components/LocationPicker";
import { Button, Chips, ErrorBox, Field, Screen } from "../../components/ui";
import { colors } from "../../theme";

type Params = { photoUrls: string[]; categoryId: number; categoryName: string; categorySlug: string };
type Cond = "new" | "good" | "used";
type FoodType = "cooked" | "dry";
type Prepared = "lt1" | "1to2" | "2to4" | "gt4";

const PREPARED: { value: Prepared; label: string; minutesAgo: number }[] = [
  { value: "lt1", label: "Within the last hour", minutesAgo: 30 },
  { value: "1to2", label: "1–2 hours ago", minutesAgo: 90 },
  { value: "2to4", label: "2–4 hours ago", minutesAgo: 180 },
  { value: "gt4", label: "More than 4 hours ago", minutesAgo: 300 },
];

/** Pickup windows from now: today if there is time left, then tomorrow. */
function pickupWindows(now: Date): { value: string; label: string; from: Date; to: Date }[] {
  const at = (dayOffset: number, hour: number) => {
    const d = new Date(now);
    d.setDate(d.getDate() + dayOffset);
    d.setHours(hour, 0, 0, 0);
    return d;
  };
  const out = [];
  if (now.getHours() < 20) out.push({ value: "soon", label: "In the next 3 hours", from: now, to: new Date(now.getTime() + 3 * 3600000) });
  if (now.getHours() < 18) out.push({ value: "eve0", label: "This evening, 5–8 pm", from: now > at(0, 17) ? now : at(0, 17), to: at(0, 20) });
  out.push(
    { value: "morn1", label: "Tomorrow morning, 9 am–12 pm", from: at(1, 9), to: at(1, 12) },
    { value: "aft1", label: "Tomorrow afternoon, 12–5 pm", from: at(1, 12), to: at(1, 17) },
    { value: "eve1", label: "Tomorrow evening, 5–8 pm", from: at(1, 17), to: at(1, 20) },
  );
  return out;
}

/** Step 2 of 2: details, pickup place and time, then submit. */
export default function DonateDetailsScreen() {
  const navigation = useNavigation<any>();
  const { params } = useRoute<any>() as { params: Params };
  const { user } = useAuth();
  const foodCategory = params.categorySlug === "food";

  const [title, setTitle] = useState("");
  const [qty, setQty] = useState(1);
  const [condition, setCondition] = useState<Cond>("good");
  const [description, setDescription] = useState("");
  const [isFood, setIsFood] = useState(foodCategory);
  const [foodType, setFoodType] = useState<FoodType>("cooked");
  const [prepared, setPrepared] = useState<Prepared>("lt1");
  const [locationId, setLocationId] = useState<string | null>(user?.location_id ?? null);
  const [locationPath, setLocationPath] = useState<string[]>(user?.location_path ?? []);
  const [changeArea, setChangeArea] = useState(!user?.location_id);
  const [address, setAddress] = useState(user?.address ?? "");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const windows = useMemo(() => pickupWindows(new Date()), []);
  const [windowKey, setWindowKey] = useState(windows[0].value);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const locate = async () => {
    setError(null);
    setLocating(true);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) throw new Error("Location permission is needed so the rider can find you");
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
      if (!address.trim()) {
        const [place] = await Location.reverseGeocodeAsync({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }).catch(() => []);
        if (place) setAddress([place.name, place.street, place.district, place.city].filter(Boolean).join(", "));
      }
    } catch (e) {
      setError((e as Error).message || "Could not get your location. Turn on location and try again");
    } finally {
      setLocating(false);
    }
  };

  const submit = async () => {
    setError(null);
    if (title.trim().length < 2) return setError("Write a short title, e.g. \"10 blankets\"");
    if (!locationId) return setError("Choose your pickup area");
    if (address.trim().length < 5) return setError("Write the pickup address so the rider can find you");
    if (!coords) return setError("Tap \"Use my current location\" so the rider can find you");
    const w = windows.find((x) => x.value === windowKey)!;
    const minutesAgo = PREPARED.find((p) => p.value === prepared)!.minutesAgo;
    const body = {
      category_id: params.categoryId,
      title: title.trim(),
      quantity: qty,
      condition: isFood ? null : condition,
      description: description.trim() || null,
      is_food: isFood,
      food_type: isFood ? foodType : null,
      prepared_at: isFood && foodType === "cooked" ? new Date(Date.now() - minutesAgo * 60000).toISOString() : null,
      pickup: { address: address.trim(), lat: coords.lat, lng: coords.lng, location_id: locationId, from: w.from.toISOString(), to: w.to.toISOString() },
      photo_urls: params.photoUrls,
    };
    setBusy(true);
    try {
      const d = await api<Donation>("/donations", { method: "POST", body: JSON.stringify(body) });
      // Start the donor tabs fresh (clears step 1) and open the new donation
      navigation.dispatch(
        CommonActions.reset({ index: 1, routes: [{ name: "DonorTabs", params: { screen: "Donations" } }, { name: "DonationDetail", params: { id: d.id, justCreated: true } }] }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen sub="Step 2 of 2 · Details and pickup" edges={["bottom"]}>
      <View style={st.row}>
        <Text style={st.label}>Category</Text>
        <Text style={st.value}>{params.categoryName}</Text>
        <Pressable accessibilityRole="button" onPress={() => navigation.goBack()} hitSlop={8}>
          <Text style={st.link}>Change</Text>
        </Pressable>
      </View>

      <Field label="Title" value={title} onChangeText={setTitle} placeholder={foodCategory ? "e.g. Cooked rice, 40 plates" : "e.g. 10 blankets"} maxLength={160} />

      <View style={{ gap: 6 }}>
        <Text style={st.label}>How many?</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <Pressable accessibilityRole="button" accessibilityLabel="Less" onPress={() => setQty((q) => Math.max(1, q - 1))} style={st.step}>
            <Text style={st.stepText}>−</Text>
          </Pressable>
          <TextInput
            accessibilityLabel="Quantity"
            value={String(qty)}
            onChangeText={(t: string) => setQty(Math.max(1, Math.min(10000, parseInt(t.replace(/\D/g, ""), 10) || 1)))}
            keyboardType="number-pad"
            style={st.qty}
          />
          <Pressable accessibilityRole="button" accessibilityLabel="More" onPress={() => setQty((q) => Math.min(10000, q + 1))} style={st.step}>
            <Text style={st.stepText}>+</Text>
          </Pressable>
        </View>
      </View>

      <View style={[st.row, { justifyContent: "space-between" }]}>
        <View style={{ flex: 1 }}>
          <Text style={st.value}>Is this food?</Text>
          <Text style={st.hint}>Cooked food is picked up first</Text>
        </View>
        <Switch value={isFood} onValueChange={setIsFood} disabled={foodCategory} trackColor={{ true: colors.primary }} />
      </View>

      {isFood ? (
        <>
          <View style={{ gap: 6 }}>
            <Text style={st.label}>Type</Text>
            <Chips options={[{ value: "cooked", label: "Cooked" }, { value: "dry", label: "Dry / packed" }]} value={foodType} onChange={setFoodType} />
          </View>
          {foodType === "cooked" ? (
            <View style={{ gap: 6 }}>
              <Text style={st.label}>When was it cooked?</Text>
              <Chips options={PREPARED} value={prepared} onChange={setPrepared} />
            </View>
          ) : null}
        </>
      ) : (
        <View style={{ gap: 6 }}>
          <Text style={st.label}>Condition</Text>
          <Chips options={[{ value: "new", label: "New" }, { value: "good", label: "Good" }, { value: "used", label: "Used" }]} value={condition} onChange={setCondition} />
        </View>
      )}

      <Field label="Description (optional)" value={description} onChangeText={setDescription} placeholder="Size, packing, anything the rider should know" multiline style={[st.multi]} maxLength={1000} />

      <Text style={st.h}>Pickup</Text>
      {changeArea ? (
        <LocationPicker
          onChange={(id, path) => {
            setLocationId(id);
            setLocationPath(path);
          }}
        />
      ) : (
        <View style={st.row}>
          <Text style={st.label}>Area</Text>
          <Text style={st.value}>{locationPath.slice(-2).join(", ")}</Text>
          <Pressable accessibilityRole="button" onPress={() => setChangeArea(true)} hitSlop={8}>
            <Text style={st.link}>Change</Text>
          </Pressable>
        </View>
      )}
      <Field label="Pickup address" value={address} onChangeText={setAddress} placeholder="House, street, block" maxLength={500} />
      <Button
        label={locating ? "Getting your location…" : coords ? "Location saved ✓ (tap to update)" : "Use my current location"}
        variant="outline"
        onPress={locate}
        loading={locating}
      />
      <Text style={st.hint}>Stand where the rider should come. A map pin arrives in Phase 4.</Text>

      <View style={{ gap: 6 }}>
        <Text style={st.label}>When can we pick it up?</Text>
        <Chips options={windows.map((w) => ({ value: w.value, label: w.label }))} value={windowKey} onChange={setWindowKey} />
      </View>

      <ErrorBox message={error} />
      <Button label="Submit donation" onPress={submit} loading={busy} />
    </Screen>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 16, fontWeight: "800", color: colors.ink },
  label: { fontSize: 13, fontWeight: "600", color: colors.ink2 },
  value: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.ink },
  hint: { fontSize: 12, color: colors.muted },
  link: { color: colors.primary, fontWeight: "700" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, padding: 14, backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: colors.line },
  step: { width: 48, height: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.line2, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  stepText: { fontSize: 22, fontWeight: "700", color: colors.primary },
  qty: { width: 80, height: 48, borderWidth: 1, borderColor: colors.line2, borderRadius: 12, backgroundColor: "#fff", textAlign: "center", fontSize: 18, fontWeight: "700", color: colors.ink },
  multi: { height: 88, textAlignVertical: "top", paddingTop: 12 },
});
