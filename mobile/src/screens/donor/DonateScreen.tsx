import { useNavigation } from "@react-navigation/native";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, View } from "react-native";
import { api, type Category } from "../../api";
import { Button, ErrorBox, Screen } from "../../components/ui";
import { colors } from "../../theme";
import { pickPhoto, uploadPhoto, type PickedPhoto } from "../../upload";

const MAX_PHOTOS = 5;

type Photo = { key: string; uri: string; url: string | null; failed: boolean };
type Suggestion = { category_id: number; name: string; p: number; shared?: boolean };
type Ai = { state: "idle" | "thinking" | "done" | "off"; suggestions: Suggestion[] };

const AUTO_PICK = 0.6;   // pre-select the AI's first choice only when it is at least this sure…
const AUTO_GAP = 0.25;   // …and clearly ahead of the second choice (clothes vs winter wear look alike)

/** Step 1 of 2: photos and category. Photos upload as soon as they are picked. */
export default function DonateScreen() {
  const navigation = useNavigation<any>();
  const [cats, setCats] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ai, setAi] = useState<Ai>({ state: "idle", suggestions: [] });
  const touched = useRef(false);   // donor chose a category themselves: the AI must not override it
  const setTouched = (v: boolean) => {
    touched.current = v;
  };

  // Ask the classifier about the first uploaded photo (Phase 5). If it is not set up, just hide the card.
  const firstUrl = photos.find((p) => p.url)?.url ?? null;
  useEffect(() => {
    if (!firstUrl) {
      setAi({ state: "idle", suggestions: [] });
      return;
    }
    let alive = true;
    setAi({ state: "thinking", suggestions: [] });
    api<{ suggestions: Suggestion[] }>("/ai/classify", { method: "POST", body: JSON.stringify({ image_url: firstUrl }) })
      .then((r) => {
        if (!alive) return;
        setAi({ state: "done", suggestions: r.suggestions });
        // A grouped answer (e.g. blankets + winter support) could be either one: let the donor choose
        const [first, second] = r.suggestions;
        const clear = first && first.p >= AUTO_PICK && !first.shared && (!second || first.p - second.p >= AUTO_GAP);
        if (!touched.current && clear) setCategoryId(first.category_id);
      })
      .catch(() => alive && setAi({ state: "off", suggestions: [] }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstUrl]);

  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch((e) => setError(e.message));
  }, []);

  const addPhoto = () => {
    Alert.alert("Add photo", "Show the items clearly, in good light.", [
      { text: "Camera", onPress: () => pickAndUpload("camera") },
      { text: "Gallery", onPress: () => pickAndUpload("gallery") },
      { text: "Cancel", style: "cancel" },
    ]);
  };

  const pickAndUpload = async (source: "camera" | "gallery") => {
    setError(null);
    let picked: PickedPhoto | null;
    try {
      picked = await pickPhoto(source);
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    if (!picked) return;
    const photo = picked;
    const key = `${Date.now()}`;
    setPhotos((p) => [...p, { key, uri: photo.uri, url: null, failed: false }]);
    try {
      const url = await uploadPhoto(photo, "donation_photo");
      setPhotos((p) => p.map((x) => (x.key === key ? { ...x, url } : x)));
    } catch (e) {
      setPhotos((p) => p.map((x) => (x.key === key ? { ...x, failed: true } : x)));
      setError((e as Error).message);
    }
  };

  const remove = (key: string) => setPhotos((p) => p.filter((x) => x.key !== key));

  const uploading = photos.some((p) => !p.url && !p.failed);
  const ready = photos.filter((p) => p.url);
  const canContinue = ready.length > 0 && !uploading && categoryId !== null;

  const next = () => {
    const cat = cats.find((c) => c.id === categoryId)!;
    const top = ai.suggestions[0];
    const aiBlock = top
      ? { category_id: top.category_id, confidence: top.p, top3: ai.suggestions.map((x) => ({ category_id: x.category_id, p: x.p })) }
      : null;
    navigation.navigate("DonateDetails", {
      photoUrls: ready.map((p) => p.url), categoryId: cat.id, categoryName: cat.name, categorySlug: cat.slug, ai: aiBlock,
    });
  };

  return (
    <Screen title="New donation" sub="Step 1 of 2 · Photos and category">
      <Text style={st.h}>Photos</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
        {photos.map((p) => (
          <View key={p.key} style={st.photo}>
            <Image source={{ uri: p.uri }} style={{ width: "100%", height: "100%", borderRadius: 12, opacity: p.url ? 1 : 0.5 }} />
            {!p.url && !p.failed ? <ActivityIndicator style={StyleSheet.absoluteFill} color={colors.primary} /> : null}
            {p.failed ? <Text style={st.failed}>Failed</Text> : null}
            <Pressable accessibilityRole="button" accessibilityLabel="Remove photo" onPress={() => remove(p.key)} style={st.remove} hitSlop={8}>
              <Text style={{ color: "#fff", fontWeight: "800" }}>×</Text>
            </Pressable>
          </View>
        ))}
        {photos.length < MAX_PHOTOS ? (
          <Pressable accessibilityRole="button" accessibilityLabel="Add photo" onPress={addPhoto} style={[st.photo, st.add]}>
            <Text style={{ fontSize: 28, color: colors.primary }}>+</Text>
            <Text style={{ fontSize: 12, fontWeight: "700", color: colors.primary }}>Add photo</Text>
          </Pressable>
        ) : null}
      </View>
      <Text style={st.hint}>Up to {MAX_PHOTOS} photos. Our riders use them to know what to pick up.</Text>

      {ai.state === "thinking" ? (
        <View style={[st.aiCard, { flexDirection: "row", alignItems: "center", gap: 10 }]}>
          <ActivityIndicator color={colors.primary} />
          <Text style={{ color: colors.ink2 }}>Looking at your photo…</Text>
        </View>
      ) : ai.state === "done" && ai.suggestions.length ? (
        <View style={st.aiCard}>
          <Text style={{ fontWeight: "800", color: colors.ink }}>What is this?</Text>
          <Text style={{ fontSize: 12, color: colors.muted }}>
            {ai.suggestions[0]?.shared
              ? "Our AI thinks it is one of these similar categories. Tap the right one."
              : "Our AI looked at your photo. Tap the right one, or choose another below."}
          </Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {ai.suggestions.map((sg) => {
              const on = sg.category_id === categoryId;
              return (
                <Pressable
                  key={sg.category_id}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: on }}
                  accessibilityLabel={`${sg.name}, ${Math.round(sg.p * 100)} percent`}
                  onPress={() => {
                    setTouched(true);
                    setCategoryId(sg.category_id);
                  }}
                  style={[st.cat, on && { backgroundColor: colors.primarySoft, borderColor: colors.primary, borderWidth: 2 }]}
                >
                  <Text style={[st.catText, on && { color: colors.primaryDark }]}>
                    {sg.name} <Text style={{ color: colors.muted, fontWeight: "500" }}>{Math.round(sg.p * 100)}%</Text>
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ) : null}

      <Text style={st.h}>{ai.state === "done" ? "Not right? Choose a category" : "What are you donating?"}</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {cats.map((c) => {
          const on = c.id === categoryId;
          return (
            <Pressable
              key={c.id}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              onPress={() => {
                setTouched(true);
                setCategoryId(c.id);
              }}
              style={[st.cat, on && { backgroundColor: colors.primarySoft, borderColor: colors.primary, borderWidth: 2 }]}
            >
              <Text style={[st.catText, on && { color: colors.primaryDark }]}>{c.name}</Text>
            </Pressable>
          );
        })}
      </View>

      <ErrorBox message={error} />
      <Button label={uploading ? "Uploading photos…" : "Continue"} onPress={next} disabled={!canContinue} />
    </Screen>
  );
}

const st = StyleSheet.create({
  h: { fontSize: 16, fontWeight: "800", color: colors.ink },
  hint: { fontSize: 12, color: colors.muted, marginTop: -6 },
  photo: { width: 96, height: 96, borderRadius: 12, backgroundColor: colors.line },
  add: { borderWidth: 2, borderStyle: "dashed", borderColor: colors.primary, backgroundColor: "#fff", alignItems: "center", justifyContent: "center" },
  remove: { position: "absolute", top: 4, right: 4, width: 24, height: 24, borderRadius: 12, backgroundColor: "rgba(0,0,0,.6)", alignItems: "center", justifyContent: "center" },
  failed: { position: "absolute", bottom: 6, left: 6, color: "#fff", backgroundColor: colors.urgent, paddingHorizontal: 6, borderRadius: 6, fontSize: 11, fontWeight: "700" },
  aiCard: { padding: 14, borderRadius: 14, backgroundColor: "#fff", borderWidth: 1, borderColor: colors.primary, gap: 8 },
  cat: { minHeight: 44, paddingHorizontal: 14, justifyContent: "center", borderRadius: 12, borderWidth: 1, borderColor: colors.line2, backgroundColor: "#fff" },
  catText: { fontSize: 14, fontWeight: "600", color: colors.ink },
});
