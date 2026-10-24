import { ComingIn, PageHeader } from "../components/Layout";

export default function Flags() {
  return (
    <>
      <PageHeader title="Fraud flags" sub="Warnings raised by simple rules. You decide." />
      <main className="page">
        <ComingIn phase={8} what="Flag queue, evidence panel and dismiss / warn / suspend actions." />
      </main>
    </>
  );
}
