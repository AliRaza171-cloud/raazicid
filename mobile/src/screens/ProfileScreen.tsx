import { useState } from "react";
import { Text, View } from "react-native";
import { api, type User } from "../api";
import { useAuth } from "../auth";
import LocationPicker from "../components/LocationPicker";
import { Button, Card, ErrorBox, Field, Screen } from "../components/ui";
import { colors } from "../theme";

export default function ProfileScreen() {
  const { user, setUser, logout } = useAuth();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!user) return null;

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = { full_name: name.trim() };
      if (email.trim()) body.email = email.trim();
      if (locationId) body.location_id = locationId;
      setUser(await api<User>("/me", { method: "PATCH", body: JSON.stringify(body) }));
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen title="Profile" sub={user.role === "rider" ? `Rider · ${user.rider_status}` : "Donor"}>
      {!editing ? (
        <>
          <Card>
            <Row k="Name" v={user.full_name} />
            <Row k="Phone" v={user.phone} />
            <Row k="Email" v={user.email ?? "—"} />
            <Row k="Location" v={user.location_path.length ? user.location_path.join(" › ") : "Not set"} />
          </Card>
          <Button label="Edit profile" variant="outline" onPress={() => setEditing(true)} />
        </>
      ) : (
        <>
          <Field label="Full name" value={name} onChangeText={setName} />
          <Field label="Email" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" />
          <Text style={{ fontSize: 13, color: colors.muted }}>Current location: {user.location_path.join(" › ") || "not set"}. Choose a new one below, or leave it.</Text>
          <LocationPicker onChange={(id) => setLocationId(id)} />
          <ErrorBox message={error} />
          <Button label="Save" onPress={save} loading={busy} />
          <Button label="Cancel" variant="outline" onPress={() => setEditing(false)} />
        </>
      )}
      <Button label="Log out" variant="danger" onPress={logout} />
    </Screen>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12, paddingVertical: 6 }}>
      <Text style={{ color: colors.muted }}>{k}</Text>
      <Text style={{ color: colors.ink, fontWeight: "600", flexShrink: 1, textAlign: "right" }}>{v}</Text>
    </View>
  );
}
