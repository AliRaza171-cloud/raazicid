import { useAuth } from "../auth";
import { Button, ComingIn, Screen } from "../components/ui";

export default function ProfileScreen() {
  const { role, signOut } = useAuth();
  return (
    <Screen title="Profile" sub={role === "rider" ? "Rider account" : "Donor account"}>
      <ComingIn phase={2} what="Name, phone, location (province › city › region › area) and settings." />
      <Button label="Log out" variant="outline" onPress={signOut} />
    </Screen>
  );
}
