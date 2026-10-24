import { ComingIn, Screen } from "../../components/ui";

export default function TrackingScreen() {
  return (
    <Screen title="Live tracking">
      <ComingIn phase={4} what="Map with the rider, journey timeline and proof photos." />
    </Screen>
  );
}
