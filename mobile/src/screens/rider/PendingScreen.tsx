import { ComingIn, Screen } from "../../components/ui";

export default function PendingScreen() {
  return (
    <Screen title="We are checking your documents">
      <ComingIn phase={2} what="Verification steps and re-upload." />
    </Screen>
  );
}
