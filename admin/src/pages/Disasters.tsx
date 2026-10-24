import { ComingIn, PageHeader } from "../components/Layout";

export default function Disasters() {
  return (
    <>
      <PageHeader title="Disaster alerts" sub="Checked automatically from GDACS, ReliefWeb, NDMA / PDMA and web search." />
      <main className="page">
        <ComingIn phase={6} what="Alert list, unconfirmed web alerts, figures, what is needed and response actions." />
      </main>
    </>
  );
}
