import { ComingIn, PageHeader } from "../components/Layout";

export default function NeedsMap() {
  return (
    <>
      <PageHeader title="Needs by area" sub="What each area needs across all 12 categories." />
      <main className="page">
        <ComingIn phase={6} what="Area × category grid, map view, province filters and the reasons panel." />
      </main>
    </>
  );
}
