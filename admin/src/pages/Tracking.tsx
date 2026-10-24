import { ComingIn, PageHeader } from "../components/Layout";

export default function Tracking() {
  return (
    <>
      <PageHeader title="Live tracking" sub="Riders on active jobs, updated every 15 seconds." />
      <main className="page">
        <ComingIn phase={4} what="Live map of riders and points, active job list, stalled-job reassignment." />
      </main>
    </>
  );
}
