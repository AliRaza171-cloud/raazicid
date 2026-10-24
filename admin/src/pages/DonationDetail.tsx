import { ComingIn, PageHeader } from "../components/Layout";

export default function DonationDetail() {
  return (
    <>
      <PageHeader title="Donation detail" sub="Review, choose a distribution point and assign a rider." />
      <main className="page">
        <ComingIn phase={3} what="Photos, AI category, urgency, suggested points and recommended riders (Phase 5)." />
      </main>
    </>
  );
}
