import { ComingIn, PageHeader } from "../components/Layout";

export default function Donations() {
  return (
    <>
      <PageHeader title="Donations" sub="Every donation, most urgent first." />
      <main className="page">
        <ComingIn phase={3} what="Status tabs, filters by category / province / city and the donations table." />
      </main>
    </>
  );
}
