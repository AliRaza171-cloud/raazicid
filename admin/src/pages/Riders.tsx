import { ComingIn, PageHeader } from "../components/Layout";

export default function Riders() {
  return (
    <>
      <PageHeader title="Riders" sub="Verification and management." />
      <main className="page">
        <ComingIn phase={2} what="Pending / active / suspended tabs, documents and approve / reject (AI review in Phase 5)." />
      </main>
    </>
  );
}
