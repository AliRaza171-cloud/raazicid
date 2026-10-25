import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import AppealForm from "../components/AppealForm";
import { PageHeader } from "../components/Layout";
import LocationSelect from "../components/LocationSelect";
import { api, type Category, type FinderAnswer, type FinderArea } from "../lib/api";
import { LEVELS, date } from "../lib/format";

const EXAMPLES = [
  "Where are blankets and winter clothes needed most this winter?",
  "Which districts have the worst food insecurity right now?",
  "Where are flood-affected families still waiting for help?",
  "Which areas need hygiene kits for women and children?",
];

const NEED_CHIP: Record<string, string> = { urgent: "lv3", high: "lv2", some: "lv1" };

export default function NeedFinder() {
  const [cats, setCats] = useState<Category[]>([]);
  const [question, setQuestion] = useState("");
  const [locationId, setLocationId] = useState<string | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [web, setWeb] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<FinderAnswer | null>(null);
  const [focus, setFocus] = useState<string | null>(null);     // a source id like S2 / D1
  const [appealFor, setAppealFor] = useState<FinderArea | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    api<Category[]>("/categories").then(setCats).catch(() => undefined);
  }, []);

  const ask = async (e?: FormEvent) => {
    e?.preventDefault();
    if (question.trim().length < 5) return setError("Write a question first");
    setBusy(true);
    setError(null);
    setFocus(null);
    setAppealFor(null);
    try {
      setRes(await api<FinderAnswer>("/admin/need-finder/ask", {
        method: "POST",
        body: JSON.stringify({ question: question.trim(), location_id: locationId, category_id: categoryId, web_search: web }),
      }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  /** "Lyari needs blankets [S1][D2]." with clickable citation chips */
  const cite = (text: string): ReactNode[] =>
    text.split(/(\[(?:S|D)\d+\])/g).map((part, i) => {
      const m = part.match(/^\[((?:S|D)\d+)\]$/);
      if (!m) return <span key={i}>{part}</span>;
      return (
        <button key={i} onClick={() => setFocus(m[1])} title="Show this source"
          style={{ border: 0, borderRadius: 6, padding: "0 5px", margin: "0 1px", fontSize: 11, fontWeight: 800, cursor: "pointer",
                   background: focus === m[1] ? "var(--green-700)" : "var(--green-50)", color: focus === m[1] ? "#fff" : "#0b5e50" }}>
          {m[1]}
        </button>
      );
    });

  const catIds = (names: string[]) => cats.filter((c) => names.some((n) => n.toLowerCase().includes(c.name.toLowerCase().split(" ")[0]) || c.name.toLowerCase().includes(n.toLowerCase()))).map((c) => c.id);

  return (
    <>
      <PageHeader title="Need finder" sub="Ask where help is needed. Answers come from the report library, our need levels and (if you switch it on) the web, and cite every source." />
      <main className="page">
        <form className="card" onSubmit={ask} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <textarea className="input" style={{ height: 76, paddingTop: 10 }} value={question} onChange={(e) => setQuestion(e.target.value)} aria-label="Question"
            placeholder="Where in Sindh are blankets needed most this winter?" maxLength={600} />
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {EXAMPLES.map((x) => (
              <button key={x} type="button" className="chip wait" style={{ border: 0, cursor: "pointer" }} onClick={() => setQuestion(x)}>{x}</button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
            <LocationSelect compact allLabel="All Pakistan" onChange={(id) => setLocationId(id)} />
            <select className="select" aria-label="Category" value={categoryId ?? ""} onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Any category</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <label style={{ display: "flex", gap: 6, alignItems: "center", margin: 0, fontWeight: 600 }} title="Claude also searches the web (about 1 cent per search)">
              <input type="checkbox" checked={web} onChange={(e) => setWeb(e.target.checked)} /> Also search the web
            </label>
            <button className="btn" type="submit" disabled={busy} style={{ marginLeft: "auto" }}>{busy ? (web ? "Searching the library and the web…" : "Searching the library…") : "Find needs"}</button>
          </div>
        </form>

        {error && <div className="flash bad" role="alert">{error}</div>}
        {flash && <div className="flash ok" role="status">{flash}</div>}

        {res && (
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "flex-start" }}>
            <div style={{ flex: "2 1 520px", display: "flex", flexDirection: "column", gap: 16 }}>
              <section className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  <h2 style={{ margin: 0, fontSize: 16, marginRight: "auto" }}>Answer</h2>
                  {res.ai && <span className={`chip ${res.confidence === "high" ? "ok" : res.confidence === "medium" ? "info" : "warn"}`}>Confidence: {res.confidence}</span>}
                  <span className="chip wait">{res.ai ? `Claude · ${res.sources.length} passages${res.used_web ? " · web" : ""}` : "Library only"}</span>
                </div>
                <p style={{ margin: 0, fontSize: 15, lineHeight: 1.55 }}>{cite(res.answer)}</p>
                {res.place && <span className="muted small">Place: {res.place}{res.category ? ` · ${res.category}` : ""}</span>}
              </section>

              {res.areas.length > 0 && (
                <section style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <h2 style={{ margin: 0, fontSize: 16 }}>Areas</h2>
                  {res.areas.map((a, i) => (
                    <div key={i} className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                        <span className={`chip ${NEED_CHIP[a.need]}`}>{a.need[0].toUpperCase() + a.need.slice(1)}</span>
                        <strong style={{ fontSize: 16 }}>{a.name}</strong>
                        <span className="muted small">{a.path.length ? a.path.join(" › ") : "Not in our places list"}</span>
                        {a.our_level !== null && <span className={`chip lv${a.our_level}`} title="Level from our own data (needs by area)" style={{ marginLeft: "auto" }}>Our data: {LEVELS[a.our_level].label}</span>}
                      </div>
                      {a.categories.length > 0 && <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>{a.categories.map((c) => <span key={c} className="chip wait">{c}</span>)}</div>}
                      <div>{cite(a.reason)}</div>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {a.location_id && <button className="btn small" onClick={() => setAppealFor(a)}>Send an appeal</button>}
                        <Link className="btn ghost small" to="/needs">Needs by area</Link>
                        <Link className="btn ghost small" to="/points">Add a distribution point</Link>
                      </div>
                      {appealFor === a && a.location_id && (
                        <AppealForm cats={cats}
                          defaults={{ title: `${a.categories[0] ?? "Help"} needed in ${a.name}`, message: a.reason.replace(/\s*\[(?:S|D)\d+\]/g, ""),
                                      locationId: a.location_id, locationPath: a.path, categoryIds: catIds(a.categories) }}
                          onCancel={() => setAppealFor(null)}
                          onSent={(ap) => { setAppealFor(null); setFlash(`Appeal sent to ${ap.reached} donors in ${ap.provinces.join(", ")}`); }} />
                      )}
                    </div>
                  ))}
                </section>
              )}
            </div>

            <aside style={{ flex: "1 1 340px", display: "flex", flexDirection: "column", gap: 12 }}>
              <section className="card" style={{ padding: 0 }}>
                <h2 style={{ margin: 0, fontSize: 16, padding: "14px 16px 6px" }}>Library passages</h2>
                {res.sources.length === 0 && <p className="muted small" style={{ padding: "0 16px 14px", margin: 0 }}>Nothing in the library matched. Upload reports in the Report library.</p>}
                {res.sources.map((s) => (
                  <div key={s.id} style={{ borderTop: "1px solid var(--line)", padding: "10px 16px", background: focus === s.id ? "var(--green-50)" : undefined }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <button onClick={() => setFocus(focus === s.id ? null : s.id)} className={`chip ${s.cited ? "solid" : "wait"}`} style={{ border: 0, cursor: "pointer" }}>{s.id}</button>
                      <strong style={{ fontSize: 14 }}>{s.title}</strong>
                    </div>
                    <div className="muted small">
                      {s.publisher}{s.date ? ` · ${date(s.date)}` : ""}{s.page ? ` · page ${s.page}` : ""} · found by {s.found_by.join(" + ") || "search"}
                      {s.places.length ? ` · ${s.places.join(", ")}` : ""}
                    </div>
                    {focus === s.id && <p style={{ fontSize: 13, whiteSpace: "pre-wrap", margin: "8px 0 0" }}>{s.text}</p>}
                    {focus === s.id && s.url && <a className="small" href={s.url} target="_blank" rel="noreferrer">Open the original</a>}
                  </div>
                ))}
              </section>

              {res.facts.length > 0 && (
                <section className="card" style={{ padding: 0 }}>
                  <h2 style={{ margin: 0, fontSize: 16, padding: "14px 16px 6px" }}>Our need levels</h2>
                  {res.facts.map((f) => (
                    <div key={f.id} style={{ borderTop: "1px solid var(--line)", padding: "8px 16px", background: focus === f.id ? "var(--green-50)" : undefined }}>
                      <span className="chip wait">{f.id}</span> <strong style={{ fontSize: 13 }}>{f.place}</strong> · {f.category}: {f.level}
                      {focus === f.id && <div className="muted small" style={{ marginTop: 4 }}>{f.why}</div>}
                    </div>
                  ))}
                </section>
              )}

              {res.web_results.length > 0 && (
                <section className="card" style={{ padding: 0 }}>
                  <h2 style={{ margin: 0, fontSize: 16, padding: "14px 16px 6px" }}>From the web</h2>
                  {res.web_results.map((w) => (
                    <div key={w.url} style={{ borderTop: "1px solid var(--line)", padding: "8px 16px" }}>
                      <a href={w.url} target="_blank" rel="noreferrer" style={{ fontWeight: 600, fontSize: 14 }}>{w.title}</a>
                      {w.snippet && <div className="muted small">“{w.snippet}”</div>}
                    </div>
                  ))}
                </section>
              )}
            </aside>
          </div>
        )}
      </main>
    </>
  );
}
