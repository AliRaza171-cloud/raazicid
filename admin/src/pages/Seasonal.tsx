import { ComingIn, PageHeader } from "../components/Layout";

export default function Seasonal() {
  return (
    <>
      <PageHeader title="Seasonal planner" sub="Which categories are needed most, month by month." />
      <main className="page">
        <ComingIn phase={7} what="12-month need grid by province, Hijri events and the rules editor." />
      </main>
    </>
  );
}
