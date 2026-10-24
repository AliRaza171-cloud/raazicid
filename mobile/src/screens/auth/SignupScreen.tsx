import { useState } from "react";
import { Text, View } from "react-native";
import { useAuth, type RegisterBody } from "../../auth";
import LocationPicker from "../../components/LocationPicker";
import { Button, Chips, ErrorBox, Field, Screen } from "../../components/ui";
import { colors } from "../../theme";

type Vehicle = "motorbike" | "rickshaw" | "pickup";

export default function SignupScreen() {
  const { register } = useAuth();
  const [role, setRole] = useState<"donor" | "rider">("donor");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [vehicle, setVehicle] = useState<Vehicle>("motorbike");
  const [vehicleNo, setVehicleNo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (name.trim().length < 2) return setError("Enter your full name");
    if (phone.replace(/\D/g, "").length < 11) return setError("Enter your mobile number, e.g. 0300 1234567");
    if (password.length < 8) return setError("Password must be at least 8 characters");
    if (!locationId) return setError("Choose your location");
    if (role === "rider" && vehicleNo.trim().length < 2) return setError("Enter your vehicle number");

    const body: RegisterBody = {
      role,
      full_name: name.trim(),
      phone,
      password,
      location_id: locationId,
      ...(email.trim() ? { email: email.trim() } : {}),
      ...(role === "rider" ? { rider: { vehicle_type: vehicle, vehicle_number: vehicleNo.trim() } } : {}),
    };
    setBusy(true);
    try {
      await register(body);
      // RootNavigator switches to the donor app, or to the rider "upload documents" screen
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen edges={["bottom"]}>
      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.ink2 }}>I want to</Text>
      <Chips
        options={[
          { value: "donor", label: "Donate items" },
          { value: "rider", label: "Deliver for RAAZICID" },
        ]}
        value={role}
        onChange={setRole}
      />
      <Field label="Full name" value={name} onChangeText={setName} placeholder="As on your CNIC" autoComplete="name" />
      <Field label="Mobile number" value={phone} onChangeText={setPhone} placeholder="0300 1234567" keyboardType="phone-pad" autoComplete="tel" />
      <Field label="Email (optional)" value={email} onChangeText={setEmail} placeholder="you@example.com" keyboardType="email-address" autoCapitalize="none" />
      <Field label="Password" value={password} onChangeText={setPassword} placeholder="At least 8 characters" secureTextEntry hint="At least 8 characters" />

      <View style={{ gap: 4 }}>
        <Text style={{ fontSize: 15, fontWeight: "700", color: colors.ink }}>Your location</Text>
        <Text style={{ fontSize: 13, color: colors.muted }}>Used for pickups and to show what is needed in your area.</Text>
      </View>
      <LocationPicker onChange={(id) => setLocationId(id)} />

      {role === "rider" ? (
        <View style={{ gap: 12, padding: 16, backgroundColor: "#fff", borderRadius: 16, borderWidth: 1, borderColor: colors.line }}>
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.ink }}>Rider details</Text>
          <Chips
            options={[
              { value: "motorbike", label: "Motorbike" },
              { value: "rickshaw", label: "Rickshaw" },
              { value: "pickup", label: "Pickup / loader" },
            ]}
            value={vehicle}
            onChange={setVehicle}
          />
          <Field label="Vehicle number" value={vehicleNo} onChangeText={setVehicleNo} placeholder="KHI-1234" autoCapitalize="characters" />
          <Text style={{ fontSize: 12, color: colors.muted }}>Next you will upload your CNIC, licence and vehicle registration for an admin to check.</Text>
        </View>
      ) : null}

      <ErrorBox message={error} />
      <Button label="Create account" onPress={submit} loading={busy} />
    </Screen>
  );
}
