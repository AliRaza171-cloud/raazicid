import { ComingIn, PageHeader } from "../components/Layout";

export default function Points() {
  return (
    <>
      <PageHeader title="Distribution points" sub="Places in needy areas where our team hands out donations." />
      <main className="page">
        <ComingIn phase={3} what="Points table, map and the add / edit form." />
      </main>
    </>
  );
}
