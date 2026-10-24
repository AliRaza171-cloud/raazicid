import { ComingIn, Screen } from "../../components/ui";

export default function DonationsScreen() {
  return (
    <Screen title="My donations">
      <ComingIn phase={3} what="Active / completed / all tabs and donation cards." />
    </Screen>
  );
}
