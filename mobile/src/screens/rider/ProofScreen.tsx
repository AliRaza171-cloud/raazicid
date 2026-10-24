import { ComingIn, Screen } from "../../components/ui";

export default function ProofScreen() {
  return (
    <Screen title="Confirm delivery">
      <ComingIn phase={4} what="Proof photo, checklist and hand-out details." />
    </Screen>
  );
}
