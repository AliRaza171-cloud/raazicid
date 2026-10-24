import { ComingIn, Screen } from "../../components/ui";

export default function AlertsScreen() {
  return (
    <Screen title="Notifications">
      <ComingIn phase={4} what="Status updates, appeals and seasonal tips." />
    </Screen>
  );
}
