import { ComingIn, Screen } from "../../components/ui";

export default function SignupScreen() {
  return (
    <Screen title="Create account">
      <ComingIn phase={2} what="Donor / rider choice, name, phone, password, location dropdowns and rider documents." />
    </Screen>
  );
}
