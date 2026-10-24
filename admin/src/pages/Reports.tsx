import { ComingIn, PageHeader } from "../components/Layout";

export default function Reports() {
  return (
    <>
      <PageHeader title="Report library" sub="Everything the RAG knows: auto-fetched and uploaded." />
      <main className="page">
        <ComingIn phase={6} what="Automatic sources, upload, reports table and location tag review." />
      </main>
    </>
  );
}
