import { ComingIn, PageHeader } from "../components/Layout";

export default function NeedFinder() {
  return (
    <>
      <PageHeader title="Need finder" sub="Ask where help is needed. Answers cite their sources." />
      <main className="page">
        <ComingIn phase={6} what="Location filters, question box, ranked areas, web search switch and 'From the web' results." />
      </main>
    </>
  );
}
