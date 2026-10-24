import { ComingIn, Screen } from "../../components/ui";

export default function DonateDetailsScreen() {
  return (
    <Screen title="Donation details">
      <ComingIn phase={3} what="Quantity, condition, food fields, pickup pin and time window." />
    </Screen>
  );
}
